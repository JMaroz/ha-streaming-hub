"""Main FastAPI entrypoint and API router for Streaming Hub."""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

import aiohttp

from .database import MediaDatabase
from .dns_resolver import DNS_DEFAULT
from .ha_client import HACoreClient
from .metadata import MetadataEnricher
from .models import Movie, ProviderSource, TvSeries
from .proxy import StreamProxy
from .sources.cb01_source import CB01Source
from .sources.detector import SourceDetector
from .sources.manager import SourceManager
from .sources.streamingcommunity_source import StreamingCommunitySource

_LOGGER = logging.getLogger("streaming_hub")

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
OPTIONS_FILE = Path("/data/options.json")


def load_options() -> dict[str, Any]:
    """Load add-on options from Supervisor /data/options.json or environment."""
    custom_sources_env = os.getenv("CUSTOM_SOURCES", "").strip()
    parsed_sources: list[Any] = []
    if custom_sources_env:
        try:
            parsed_sources = json.loads(custom_sources_env)
        except Exception:
            parsed_sources = [s.strip() for s in custom_sources_env.split(",") if s.strip()]

    options = {
        "log_level": os.getenv("LOG_LEVEL", "info"),
        "custom_dns": os.getenv("CUSTOM_DNS", DNS_DEFAULT),
        "tmdb_api_key": os.getenv("TMDB_API_KEY", ""),
        "stream_port": int(os.getenv("STREAM_PORT", "8099")),
        "custom_sources": parsed_sources,
    }

    if OPTIONS_FILE.exists():
        try:
            with open(OPTIONS_FILE, encoding="utf-8") as f:
                supervisor_opts = json.load(f)
                options.update(supervisor_opts)
        except Exception as err:
            _LOGGER.warning("Could not read /data/options.json: %s", err)

    # Normalize custom_sources: support list of dicts, list of strings, or legacy parameters
    raw_sources = options.get("custom_sources") or options.get("sources") or []
    normalized_sources: list[dict[str, Any]] = []
    for item in raw_sources:
        if isinstance(item, str) and item.strip():
            normalized_sources.append({"url": item.strip(), "type": "auto", "name": "", "enabled": True})
        elif isinstance(item, dict) and item.get("url"):
            normalized_sources.append({
                "url": str(item["url"]).strip(),
                "type": str(item.get("type", "auto")).strip(),
                "name": str(item.get("name", "")).strip(),
                "enabled": bool(item.get("enabled", True)),
            })

    # Backward compatibility with single URL env vars if explicitly set by user
    sc_env = os.getenv("STREAMINGCOMMUNITY_BASE_URL", "").strip()
    if sc_env and not any(s["url"] == sc_env for s in normalized_sources):
        normalized_sources.append({"url": sc_env, "type": "streamingcommunity", "name": "StreamingCommunity", "enabled": True})

    cb_env = os.getenv("CB01_BASE_URL", "").strip()
    if cb_env and not any(s["url"] == cb_env for s in normalized_sources):
        normalized_sources.append({"url": cb_env, "type": "cb01", "name": "CB01", "enabled": True})

    options["custom_sources"] = normalized_sources
    return options


CONFIG = load_options()

# Logging setup
log_level_name = str(CONFIG.get("log_level", "info")).upper()
numeric_level = getattr(logging, log_level_name, logging.INFO)
logging.basicConfig(
    level=numeric_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Global components
ha_client = HACoreClient()
stream_proxy = StreamProxy()
metadata_enricher = MetadataEnricher(tmdb_api_key=CONFIG.get("tmdb_api_key"))
db = MediaDatabase()

# Initialize Source Manager
source_manager = SourceManager()


async def init_sources(sources_list: list[dict[str, Any]], custom_dns: str) -> None:
    """Initialize and register configured user sources with auto-discrimination."""
    async with aiohttp.ClientSession() as session:
        for idx, src_conf in enumerate(sources_list):
            url = src_conf.get("url", "").strip()
            if not url:
                continue
            is_enabled = src_conf.get("enabled", True)
            user_type = src_conf.get("type", "auto")
            custom_name = src_conf.get("name") or ""

            detected_type = await SourceDetector.detect(url, user_specified_type=user_type, session=session)
            _LOGGER.info("Configuring source #%d: %s -> detected type: %s", idx + 1, url, detected_type)

            if detected_type == "streamingcommunity":
                source_manager.register_source(
                    StreamingCommunitySource(
                        base_url=url,
                        custom_dns=custom_dns,
                        enabled=is_enabled,
                        name=custom_name or "StreamingCommunity",
                    )
                )
            elif detected_type == "cb01":
                source_manager.register_source(
                    CB01Source(
                        base_url=url,
                        custom_dns=custom_dns,
                        enabled=is_enabled,
                        name=custom_name or "CB01",
                    )
                )
            else:
                _LOGGER.warning("Source #%d (%s) could not be mapped to any known streaming engine.", idx + 1, url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    _LOGGER.info("Starting Streaming Hub Engine...")
    await db.init()
    custom_dns = CONFIG.get("custom_dns", DNS_DEFAULT)
    custom_sources = CONFIG.get("custom_sources", [])

    if custom_sources:
        await init_sources(custom_sources, custom_dns)
    else:
        _LOGGER.warning("No user sources configured. Please configure sources in Add-on settings.")

    _LOGGER.info(
        "Sources active: %s | DNS=%s | Stream Port=%s",
        [s["name"] for s in source_manager.list_sources() if s["enabled"]],
        custom_dns,
        CONFIG.get("stream_port"),
    )
    yield
    _LOGGER.info("Shutting down Streaming Hub...")
    await source_manager.close_all()
    await metadata_enricher.close()
    await stream_proxy.close()


app = FastAPI(
    title="Streaming Hub",
    description="Home Assistant App for media streaming, HLS proxying, and Cast control",
    version="1.1.2",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request Models
class ResolveRequest(BaseModel):
    page_url: str
    provider_id: str | None = None
    media_id: str | None = None
    quality: str | None = None
    prefer_fhd: bool = True


class CastRequest(BaseModel):
    entity_id: str
    page_url: str
    title: str
    poster_url: str | None = None
    provider_id: str | None = None
    media_id: str | None = None
    quality: str | None = None


class TestSourceRequest(BaseModel):
    url: str
    type: str = "auto"


class ProgressRequest(BaseModel):
    media_id: str
    title: str
    media_type: str = "movie"
    poster_url: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    progress_seconds: float = 0
    duration_seconds: float = 0


class FavoriteRequest(BaseModel):
    title_id: str
    media_type: str = "movie"
    title: str
    poster_url: str | None = None


# Helpers
def get_ingress_path(request: Request) -> str:
    """Extract Ingress base path from header or query string."""
    ingress_hdr = request.headers.get("x-ingress-path") or request.headers.get("X-Ingress-Path")
    if ingress_hdr:
        return ingress_hdr.rstrip("/")
    return ""


# API Endpoints
@app.get("/api/status")
async def get_status(request: Request) -> dict[str, Any]:
    """Retrieve system, source, and supervisor status."""
    ingress_path = get_ingress_path(request)
    ha_host = await ha_client.get_host_ip_or_url()

    return {
        "status": "online",
        "app_name": "Streaming Hub",
        "version": "1.1.2",
        "ingress_path": ingress_path,
        "ha_host_ip": ha_host,
        "stream_port": CONFIG.get("stream_port", 8099),
        "supervisor_connected": ha_client.is_available,
        "sources": source_manager.list_sources(),
        "dns_mode": CONFIG.get("custom_dns"),
        "active_stream_sessions": len(stream_proxy._sessions),
    }


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    """Retrieve current settings, configured sources, and active engines."""
    return {
        "custom_dns": CONFIG.get("custom_dns", DNS_DEFAULT),
        "configured_sources": CONFIG.get("custom_sources", []),
        "active_sources": source_manager.list_sources(),
    }


@app.post("/api/settings/sources/test")
async def test_source_url(req: TestSourceRequest) -> dict[str, Any]:
    """Test a source URL and detect its streaming provider type."""
    clean_url = req.url.strip()
    if not clean_url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    detected = await SourceDetector.detect(clean_url, user_specified_type=req.type)
    return {
        "url": clean_url,
        "specified_type": req.type,
        "detected_type": detected,
        "supported": detected in ("streamingcommunity", "cb01"),
    }


@app.get("/api/sources")
async def get_sources() -> list[dict[str, Any]]:
    """Retrieve list of all registered catalog and streaming sources."""
    return source_manager.list_sources()


@app.get("/api/players")
async def get_players() -> list[dict[str, Any]]:
    """Retrieve all available media players from Home Assistant Core."""
    players = await ha_client.get_media_players()
    return [
        {
            "entity_id": p.entity_id,
            "name": p.name,
            "is_cast": p.is_cast,
            "state": p.state,
            "device_class": p.device_class,
        }
        for p in players
    ]


@app.get("/api/catalog/latest")
async def get_latest(
    type: str = Query("all", regex="^(all|movie|tv)$"),
    source: str = Query("all"),
    page: int = Query(1, ge=1),
) -> dict[str, Any]:
    """Retrieve latest titles across enabled sources with cross-catalog unification."""
    items = await source_manager.get_latest(media_type=type, source_filter=source, page=page)
    results = [item.to_dict() for item in items]
    return {"page": page, "source": source, "results": results}


@app.get("/api/catalog/search")
async def search_catalog(
    q: str = Query(..., min_length=1),
    type: str = Query("all", regex="^(all|movie|tv)$"),
    source: str = Query("all"),
) -> dict[str, Any]:
    """Search catalog by title across enabled sources."""
    query = q.strip()
    items = await source_manager.search(query, media_type=type, source_filter=source)
    results = [item.to_dict() for item in items]
    return {"query": query, "source": source, "count": len(results), "results": results}


@app.get("/api/catalog/genres")
async def get_genres() -> list[str]:
    """Return available unique genres across all sources."""
    return await source_manager.get_all_genres()


@app.get("/api/catalog/genre/{genre}")
async def get_by_genre(
    genre: str,
    type: str = Query("movie", regex="^(movie|tv)$"),
    source: str = Query("all"),
    page: int = Query(1, ge=1),
) -> dict[str, Any]:
    """Browse catalog by genre across sources."""
    items = await source_manager.get_by_genre(genre, media_type=type, source_filter=source, page=page)
    results = [item.to_dict() for item in items]
    return {"genre": genre, "page": page, "source": source, "results": results}


@app.get("/api/catalog/title/{media_type}/{title_id}")
async def get_title_details(media_type: str, title_id: str) -> dict[str, Any]:
    """Fetch complete details, enriched metadata, and sources for a title with SQLite caching."""
    # Check SQLite cache first for instant response
    cached = await db.get_title(title_id)
    if cached:
        return cached

    try:
        item = await source_manager.get_details(media_type, title_id)
    except Exception as err:
        _LOGGER.error("Error fetching title %s: %s", title_id, err)
        raise HTTPException(status_code=404, detail=f"Titolo non trovato: {err}")

    # Enrich with TMDb or Cinemeta
    if isinstance(item, Movie):
        await metadata_enricher.enrich_movie(item)
    elif isinstance(item, TvSeries):
        await metadata_enricher.enrich_tv_series(item)
        # Cache any pre-loaded seasons/episodes
        for s in item.seasons:
            if s.episodes:
                await db.save_season(item.id, s)

    # Persist in SQLite
    await db.save_title(item)
    return item.to_dict()


@app.get("/api/catalog/seasons/{series_id}/{season_number}")
async def get_season_episodes(series_id: str, season_number: int) -> dict[str, Any]:
    """Retrieve episodes for a specific TV series season with SQLite caching."""
    # Check SQLite cache first
    cached_season = await db.get_season(series_id, season_number)
    if cached_season and cached_season.episodes:
        return cached_season.to_dict()

    try:
        season = await source_manager.get_season(series_id, season_number)
        if season and season.episodes:
            await db.save_season(series_id, season)
        return season.to_dict()
    except Exception as err:
        _LOGGER.error("Error fetching season %s for %s: %s", season_number, series_id, err)
        raise HTTPException(status_code=404, detail=f"Stagione non trovata: {err}")


@app.post("/api/history")
async def save_progress(req: ProgressRequest) -> dict[str, Any]:
    """Save or update video watch progress in SQLite database."""
    await db.save_watch_progress(
        media_id=req.media_id,
        title=req.title,
        media_type=req.media_type,
        poster_url=req.poster_url,
        season_number=req.season_number,
        episode_number=req.episode_number,
        progress_seconds=req.progress_seconds,
        duration_seconds=req.duration_seconds,
    )
    return {"status": "ok"}


@app.get("/api/history")
async def get_history(limit: int = Query(30, ge=1, le=100)) -> list[dict[str, Any]]:
    """Retrieve user watch history from SQLite database."""
    return await db.get_watch_history(limit=limit)


@app.post("/api/favorites/toggle")
async def toggle_favorite(req: FavoriteRequest) -> dict[str, Any]:
    """Toggle a title as user favorite in SQLite database."""
    is_fav = await db.toggle_favorite(
        title_id=req.title_id,
        media_type=req.media_type,
        title=req.title,
        poster_url=req.poster_url,
    )
    return {"status": "ok", "favorite": is_fav}


@app.get("/api/favorites")
async def get_favorites() -> list[dict[str, Any]]:
    """Retrieve all user favorites from SQLite database."""
    return await db.get_favorites()


@app.post("/api/resolve")
async def resolve_media_source(req: ResolveRequest, request: Request) -> dict[str, Any]:
    """Resolve a streaming source to a proxied HLS playback URL."""
    source = ProviderSource(
        id=f"req_{secrets_token()}",
        media_id=req.media_id or "media",
        provider_id=req.provider_id or "source",
        provider_name=req.provider_id or "Provider",
        page_url=req.page_url,
        quality=req.quality,
    )

    try:
        resolved = await source_manager.resolve_stream(
            source,
            prefer_fhd=req.prefer_fhd,
        )
    except Exception as err:
        _LOGGER.error("Failed to resolve source %s: %s", req.page_url, err)
        raise HTTPException(status_code=400, detail=f"Risoluzione stream fallita: {err}")

    token = stream_proxy.register_stream(resolved)
    ingress_path = get_ingress_path(request)
    ha_host = await ha_client.get_host_ip_or_url()
    stream_port = CONFIG.get("stream_port", 8099)

    # Local player URL (through Ingress if available, else relative)
    local_stream_url = f"{ingress_path}/stream/{token}" if ingress_path else f"/stream/{token}"

    # LAN Cast URL (direct host IP without Ingress session authentication)
    lan_stream_url = f"http://{ha_host}:{stream_port}/stream/{token}"

    return {
        "token": token,
        "mime_type": resolved.mime_type,
        "stream_format": resolved.stream_format,
        "local_stream_url": local_stream_url,
        "lan_stream_url": lan_stream_url,
        "headers": resolved.headers,
    }


@app.post("/api/cast")
async def cast_to_device(req: CastRequest) -> dict[str, Any]:
    """Resolve stream and cast directly to Home Assistant media_player device."""
    source = ProviderSource(
        id=f"cast_{secrets_token()}",
        media_id=req.media_id or "media",
        provider_id=req.provider_id or "source",
        provider_name=req.provider_id or "Provider",
        page_url=req.page_url,
        quality=req.quality,
    )

    try:
        resolved = await source_manager.resolve_stream(
            source,
            prefer_fhd=True,
        )
    except Exception as err:
        _LOGGER.error("Failed to resolve stream for casting: %s", err)
        raise HTTPException(status_code=400, detail=f"Risoluzione stream fallita: {err}")

    token = stream_proxy.register_stream(resolved)
    ha_host = await ha_client.get_host_ip_or_url()
    stream_port = CONFIG.get("stream_port", 8099)

    lan_stream_url = f"http://{ha_host}:{stream_port}/stream/{token}"
    _LOGGER.info("Sending Cast command to %s with stream: %s", req.entity_id, lan_stream_url)

    success = await ha_client.play_on_device(
        entity_id=req.entity_id,
        media_url=lan_stream_url,
        title=req.title,
        poster_url=req.poster_url,
        mime_type=resolved.mime_type or "application/vnd.apple.mpegurl",
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Home Assistant non è riuscito ad avviare la riproduzione su {req.entity_id}",
        )

    return {
        "success": True,
        "entity_id": req.entity_id,
        "stream_url": lan_stream_url,
        "token": token,
    }


# Proxy stream endpoints
@app.api_route("/stream/{token}", methods=["GET", "HEAD"])
async def get_stream(token: str, request: Request, url: str | None = None) -> Response:
    """Stream or sub-playlist proxy supporting GET and HEAD."""
    ingress_path = get_ingress_path(request)
    headers_dict = dict(request.headers)
    return await stream_proxy.get_stream_response(
        token=token,
        target_url=url,
        root_path=ingress_path,
        headers_override=headers_dict,
        method=request.method,
    )


@app.api_route("/segment/{token}", methods=["GET", "HEAD"])
async def get_segment(token: str, url: str = Query(...), request: Request = None) -> Response:
    """HLS segment proxy forwarding injected headers supporting GET and HEAD."""
    ingress_path = get_ingress_path(request) if request else ""
    headers_dict = dict(request.headers) if request else {}
    return await stream_proxy.get_segment_response(
        token=token,
        segment_url=url,
        headers_override=headers_dict,
        root_path=ingress_path,
        method=request.method if request else "GET",
    )


def secrets_token() -> str:
    """Generate a quick unique token ID."""
    import secrets
    return secrets.token_hex(4)


# Frontend static files & SPA fallback
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        """Serve SPA index.html."""
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/{full_path:path}")
    async def catch_all(full_path: str):
        """Fallback to index.html or requested static file."""
        target = FRONTEND_DIR / full_path
        if target.exists() and target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(FRONTEND_DIR / "index.html"))


def run():
    """Run uvicorn server."""
    port = CONFIG.get("stream_port", 8099)
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run()
