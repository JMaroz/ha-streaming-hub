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
from .models import Movie, Profile, ProviderSource, TvSeries
from .proxy import StreamProxy
from .sources.cb01_source import CB01Source
from .sources.detector import SourceDetector
from .sources.manager import SourceManager
from .sources.streamingcommunity_source import StreamingCommunitySource
from .trakt_client import TraktClient
from .utils import CatalogMerger

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
        "profiles": [],
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

    # Normalize profiles
    raw_profiles = options.get("profiles") or []
    normalized_profiles: list[Profile] = []
    if isinstance(raw_profiles, list):
        for p in raw_profiles:
            if isinstance(p, dict) and p.get("name"):
                pid = str(p.get("id") or p.get("name", "")).lower().replace(" ", "_")
                # Inherit global tmdb_api_key if personal is empty
                p_tmdb = str(p.get("tmdb_api_key", "")).strip() or str(options.get("tmdb_api_key", "")).strip()
                normalized_profiles.append(
                    Profile(
                        id=pid,
                        name=str(p["name"]).strip(),
                        avatar=str(p.get("avatar") or "avatar_1"),
                        rating_filter=str(p.get("rating_filter") or "ALL"),
                        tmdb_api_key=p_tmdb,
                        trakt_client_id=str(p.get("trakt_client_id") or "").strip(),
                        trakt_access_token=str(p.get("trakt_access_token") or "").strip(),
                        pin=str(p["pin"]).strip() if p.get("pin") else None,
                    )
                )

    if not normalized_profiles:
        # Default single profile fallback
        normalized_profiles.append(
            Profile(
                id="default",
                name="Principale",
                avatar="avatar_1",
                rating_filter="ALL",
                tmdb_api_key=str(options.get("tmdb_api_key", "")).strip(),
            )
        )

    options["profiles"] = normalized_profiles
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
    version="1.2.3",
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
    media_type: str = "movie"
    season_number: int | None = None
    episode_number: int | None = None
    seek_seconds: float = 0
    profile_id: str = "default"
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None


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
    profile_id: str = "default"
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None


class FavoriteRequest(BaseModel):
    title_id: str
    media_type: str = "movie"
    title: str
    poster_url: str | None = None
    profile_id: str = "default"
    tmdb_id: int | None = None
    imdb_id: str | None = None


class TraktScrobbleRequest(BaseModel):
    action: str  # "start", "pause", "stop"
    media_type: str
    title: str
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    progress_percent: float = 0
    profile_id: str = "default"


class TraktDeviceCodeRequest(BaseModel):
    profile_id: str = "default"


class TraktPollTokenRequest(BaseModel):
    profile_id: str = "default"
    device_code: str


# Helpers
def get_ingress_path(request: Request) -> str:
    """Extract Ingress base path from header or query string."""
    ingress_hdr = request.headers.get("x-ingress-path") or request.headers.get("X-Ingress-Path")
    if ingress_hdr:
        return ingress_hdr.rstrip("/")
    return ""


def get_profile_by_id(profile_id: str) -> Profile:
    """Find profile by id or fallback to first/default profile."""
    profiles: list[Profile] = CONFIG.get("profiles", [])
    for p in profiles:
        if p.id == profile_id:
            return p
    return profiles[0] if profiles else Profile(id="default", name="Principale")


def get_profile_trakt_client(profile: Profile) -> TraktClient | None:
    """Instantiate a TraktClient for profile if client_id is set."""
    if not profile.trakt_client_id:
        return None
    return TraktClient(client_id=profile.trakt_client_id, access_token=profile.trakt_access_token)


# Rating Hierarchy: T (0) -> 6+ (6) -> 14+ (14) -> 18+ (18) -> ALL (99)
RATING_MAP: dict[str, int] = {
    "T": 0, "0": 0, "G": 0, "TV-Y": 0, "TV-G": 0, "PEGI 3": 0, "PEGI 0": 0,
    "6+": 6, "6": 6, "PG": 6, "TV-Y7": 6, "TV-PG": 6, "PEGI 7": 6, "PEGI 6": 6,
    "14+": 14, "14": 14, "VM14": 14, "12+": 12, "12": 12, "PG-13": 13, "TV-14": 14,
    "16+": 16, "16": 16, "PEGI 12": 12, "PEGI 14": 14, "PEGI 16": 16,
    "18+": 18, "18": 18, "VM18": 18, "R": 17, "NC-17": 18, "TV-MA": 18, "PEGI 18": 18,
    "ALL": 99,
}

def get_profile_max_rating(profile: Profile) -> int:
    """Parse profile rating filter into maximum numerical age limit."""
    filter_val = str(profile.rating_filter or "ALL").upper().strip()
    if filter_val in ("ALL", "", "NONE"):
        return 99
    if filter_val in RATING_MAP:
        return RATING_MAP[filter_val]
    # Check digits like '7', '12', '14', '18'
    digits = "".join(ch for ch in filter_val if ch.isdigit())
    if digits:
        val = int(digits)
        return 0 if val <= 3 else val
    return 99

# Content classification definitions
ADULT_KEYWORDS = {
    "erotico", "erotica", "erotismo", "adulti", "adult", "pornografico",
    "porno", "softcore", "hardcore", "hentai", "sexy", "red light",
    "vm18", "18+", "xxx", "erotic"
}

KIDS_RESTRICTED_KEYWORDS = {
    "horror", "splatter", "gore", "crime", "thriller", "giallo",
    "poliziesco", "guerra", "war", "psicologico", "mistero", "violenza"
}

UNSAFE_TITLE_KEYWORDS = {
    "resident evil", "unabomber", "kill", "killer", "assassin", "blood",
    "dead", "death", "zombie", "horror", "morte", "sangue", "massacro",
    "omicidio", "delitto", "erotico", "sesso", "sex", "alien", "predator",
    "nightmare", "saw", "demon", "diavolo", "satana", "evil", "terror"
}

FAMILY_FRIENDLY_KEYWORDS = {
    "animazione", "animation", "famiglia", "family", "kids", "bambini",
    "ragazzi", "children", "avventura", "adventure", "musica", "music",
    "commedia", "comedy", "documentario", "documentary", "fantasy", "fiaba"
}


def is_title_allowed_for_profile(title_item: Movie | TvSeries | dict[str, Any], profile: Profile) -> bool:
    """Determine if a title passes the profile's content classification filter."""
    max_allowed = get_profile_max_rating(profile)
    if max_allowed >= 99:
        return True

    # Extract title, certification, and genres
    if isinstance(title_item, dict):
        title = str(title_item.get("title") or "").lower()
        cert = str(title_item.get("certification") or "").upper().strip()
        genres = [str(g).lower() for g in title_item.get("genres") or []]
        desc = str(title_item.get("description") or "").lower()
    else:
        title = str(getattr(title_item, "title", "") or "").lower()
        cert = str(getattr(title_item, "certification", "") or "").upper().strip()
        genres = [str(g).lower() for g in getattr(title_item, "genres", []) or []]
        desc = str(getattr(title_item, "description", "") or "").lower()

    combined_text = f"{title} {' '.join(genres)} {desc[:200]}"

    # For any profile under 18: strictly block adult / erotic content
    if max_allowed < 18:
        if any(ak in combined_text for ak in ADULT_KEYWORDS):
            return False

    # Check explicit certification if available
    if cert:
        score = RATING_MAP.get(cert)
        if score is None:
            clean_digits = "".join(ch for ch in cert if ch.isdigit())
            score = int(clean_digits) if clean_digits else None
        if score is not None:
            return score <= max_allowed

    # Fallback heuristic when certification is not explicitly tagged
    if max_allowed <= 6:
        # Kids / Children profile (T or 6+ / PEGI 3 / PEGI 7)
        if any(rk in combined_text for rk in KIDS_RESTRICTED_KEYWORDS):
            return False
        if any(uk in title for uk in UNSAFE_TITLE_KEYWORDS):
            return False

        # If profile is 'T' (0) - strict family / kids content only
        if max_allowed == 0:
            if genres and not any(fk in " ".join(genres) for fk in FAMILY_FRIENDLY_KEYWORDS):
                return False

    elif max_allowed <= 14:
        # Teen profile (12+ / 14+ / PEGI 12 / PEGI 14)
        if any(w in combined_text for w in ("splatter", "gore", "extreme horror", "hardcore")):
            return False
        if any(uk in title for uk in ("erotico", "porno", "sesso", "xxx")):
            return False

    return True



# API Endpoints
@app.get("/api/status")
async def get_status(request: Request) -> dict[str, Any]:
    """Retrieve system, source, and supervisor status."""
    ingress_path = get_ingress_path(request)
    ha_host = await ha_client.get_host_ip_or_url()

    return {
        "status": "online",
        "app_name": "Streaming Hub",
        "version": "1.2.3",
        "ingress_path": ingress_path,
        "ha_host_ip": ha_host,
        "stream_port": CONFIG.get("stream_port", 8099),
        "supervisor_connected": ha_client.is_available,
        "sources": source_manager.list_sources(),
        "dns_mode": CONFIG.get("custom_dns"),
        "tmdb_configured": bool(metadata_enricher.tmdb_api_key),
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


@app.get("/api/profiles")
async def get_profiles() -> list[dict[str, Any]]:
    """Retrieve configured family profiles (without exposing private secrets)."""
    profiles: list[Profile] = CONFIG.get("profiles", [])
    return [p.to_dict(include_secrets=False) for p in profiles]


@app.post("/api/trakt/auth/device-code")
async def get_trakt_device_code(req: TraktDeviceCodeRequest) -> dict[str, Any]:
    """Request a device code and verification URL from Trakt."""
    profile = get_profile_by_id(req.profile_id)
    if not profile.trakt_client_id:
        raise HTTPException(status_code=400, detail="Trakt Client ID non configurato per questo profilo.")
    trakt = TraktClient(client_id=profile.trakt_client_id)
    res = await trakt.generate_device_code()
    if not res:
        raise HTTPException(status_code=502, detail="Impossibile contattare l'API di Trakt.tv.")
    return res


@app.post("/api/trakt/auth/token")
async def poll_trakt_token(req: TraktPollTokenRequest) -> dict[str, Any]:
    """Poll for Trakt access token once user verifies device code."""
    profile = get_profile_by_id(req.profile_id)
    if not profile.trakt_client_id:
        raise HTTPException(status_code=400, detail="Trakt Client ID non configurato.")
    trakt = TraktClient(client_id=profile.trakt_client_id)
    token_res = await trakt.poll_device_token(req.device_code)
    if not token_res or "access_token" not in token_res:
        raise HTTPException(status_code=400, detail="Token non ancora autorizzato o errore di autenticazione.")
    profile.trakt_access_token = token_res["access_token"]
    return {"status": "ok", "access_token": token_res["access_token"]}


@app.post("/api/trakt/scrobble")
async def trakt_scrobble(req: TraktScrobbleRequest) -> dict[str, Any]:
    """Send playback scrobble event to Trakt for active profile."""
    profile = get_profile_by_id(req.profile_id)
    trakt = get_profile_trakt_client(profile)
    if not trakt or not trakt.is_authenticated:
        return {"status": "ignored", "reason": "trakt_not_authenticated"}

    success = await trakt.scrobble_action(
        action=req.action,
        media_type=req.media_type,
        title=req.title,
        year=req.year,
        tmdb_id=req.tmdb_id,
        imdb_id=req.imdb_id,
        season_number=req.season_number,
        episode_number=req.episode_number,
        progress_percent=req.progress_percent,
    )
    return {"status": "ok", "scrobbled": success}


@app.get("/api/catalog/latest")
async def get_latest(
    type: str = Query("all", pattern="^(all|movie|tv)$"),
    source: str = Query("all"),
    page: int = Query(1, ge=1),
    profile_id: str = Query("default"),
) -> dict[str, Any]:
    """Retrieve latest titles across enabled sources with rating filter for active profile."""
    profile = get_profile_by_id(profile_id)
    max_rating = get_profile_max_rating(profile)

    # For kids profiles (<= 6, e.g. T, 6+, PEGI 3, PEGI 7), generic unfiltered feed from scrapers
    # contains adult/horror movies without genre tags. Instead, directly fetch certified family channels!
    if max_rating <= 6:
        items = []
        if type in ("all", "movie"):
            anim_m = await source_manager.get_by_genre("Animazione", media_type="movie", source_filter=source, page=page)
            fam_m = await source_manager.get_by_genre("Famiglia", media_type="movie", source_filter=source, page=page)
            items.extend(CatalogMerger.merge_movie_lists(anim_m, fam_m))
        if type in ("all", "tv"):
            anim_tv = await source_manager.get_by_genre("Animazione", media_type="tv", source_filter=source, page=page)
            kids_tv = await source_manager.get_by_genre("Kids", media_type="tv", source_filter=source, page=page)
            items.extend(CatalogMerger.merge_tv_lists(anim_tv, kids_tv))
        if type == "all":
            movies = [it for it in items if isinstance(it, Movie)]
            series = [it for it in items if isinstance(it, TvSeries)]
            interleaved = []
            for i in range(max(len(movies), len(series))):
                if i < len(movies):
                    interleaved.append(movies[i])
                if i < len(series):
                    interleaved.append(series[i])
            items = interleaved
    else:
        items = await source_manager.get_latest(media_type=type, source_filter=source, page=page)

    # 1. Hydrate titles with SQLite-cached certification, genres, and hosting URLs
    await db.enrich_items_with_cached_metadata(items)

    filtered = [item for item in items if is_title_allowed_for_profile(item, profile)]

    # 2. If rating filtering reduced the page below 15 items on an active profile, top up from next upstream page
    if len(filtered) < 15 and max_rating < 99 and page < 10:
        try:
            extra_items = await source_manager.get_latest(media_type=type, source_filter=source, page=page + 1)
            if extra_items:
                await db.enrich_items_with_cached_metadata(extra_items)
                extra_filtered = [it for it in extra_items if is_title_allowed_for_profile(it, profile)]
                filtered.extend(extra_filtered)
        except Exception:
            pass

    results = [item.to_dict() for item in filtered]
    from_idx = (page - 1) * 30 + 1 if results else 0
    to_idx = from_idx + len(results) - 1 if results else 0

    return {
        "page": page,
        "source": source,
        "profile_id": profile.id,
        "count": len(results),
        "from": from_idx,
        "to": to_idx,
        "results": results,
    }


@app.get("/api/catalog/search")
async def search_catalog(
    q: str = Query(..., min_length=1),
    type: str = Query("all", pattern="^(all|movie|tv)$"),
    source: str = Query("all"),
    profile_id: str = Query("default"),
) -> dict[str, Any]:
    """Search catalog by title across enabled sources filtered for active profile."""
    profile = get_profile_by_id(profile_id)
    query = q.strip()
    items = await source_manager.search(query, media_type=type, source_filter=source)
    await db.enrich_items_with_cached_metadata(items)
    filtered = [item for item in items if is_title_allowed_for_profile(item, profile)]
    results = [item.to_dict() for item in filtered]
    return {"query": query, "source": source, "profile_id": profile.id, "count": len(results), "results": results}


@app.get("/api/catalog/genres")
async def get_genres() -> list[str]:
    """Return available unique genres across all sources."""
    return await source_manager.get_all_genres()


@app.get("/api/catalog/genre/{genre}")
async def get_by_genre(
    genre: str,
    type: str = Query("movie", pattern="^(movie|tv)$"),
    source: str = Query("all"),
    page: int = Query(1, ge=1),
    profile_id: str = Query("default"),
) -> dict[str, Any]:
    """Browse catalog by genre across sources with cached database fallback/merge."""
    profile = get_profile_by_id(profile_id)
    live_items = await source_manager.get_by_genre(genre, media_type=type, source_filter=source, page=page)
    db_items = await db.get_titles_by_genre(genre, media_type=type, limit=30)
    if type == "tv":
        merged = CatalogMerger.merge_tv_lists(live_items, db_items)
    else:
        merged = CatalogMerger.merge_movie_lists(live_items, db_items)

    await db.enrich_items_with_cached_metadata(merged)
    filtered = [item for item in merged if is_title_allowed_for_profile(item, profile)]
    results = [item.to_dict() for item in filtered]
    from_idx = (page - 1) * 30 + 1 if results else 0
    to_idx = from_idx + len(results) - 1 if results else 0

    return {
        "genre": genre,
        "page": page,
        "source": source,
        "profile_id": profile.id,
        "count": len(results),
        "from": from_idx,
        "to": to_idx,
        "results": results,
    }


@app.get("/api/catalog/title/{media_type}/{title_id}")
async def get_title_details(media_type: str, title_id: str, profile_id: str = Query("default")) -> dict[str, Any]:
    """Fetch complete details, enriched metadata, and sources for a title with SQLite caching."""
    profile = get_profile_by_id(profile_id)
    # Check SQLite cache first for instant response
    cached = await db.get_title(title_id)
    if cached:
        # Check favorite status for this profile
        cached["is_favorite"] = await db.is_favorite(title_id, profile_id=profile.id)
        return cached

    try:
        item = await source_manager.get_details(media_type, title_id)
    except Exception as err:
        _LOGGER.error("Error fetching title %s: %s", title_id, err)
        raise HTTPException(status_code=404, detail=f"Titolo non trovato: {err}")

    # Enrich with TMDb or Cinemeta using profile's personal TMDb key if configured
    tmdb_key = profile.tmdb_api_key or CONFIG.get("tmdb_api_key")
    if isinstance(item, Movie):
        await metadata_enricher.enrich_movie(item, api_key=tmdb_key)
    elif isinstance(item, TvSeries):
        await metadata_enricher.enrich_tv_series(item, api_key=tmdb_key)
        # Cache any pre-loaded seasons/episodes
        for s in item.seasons:
            if s.episodes:
                await db.save_season(item.id, s)

    # Persist in SQLite
    await db.save_title(item)
    data = item.to_dict()
    data["is_favorite"] = await db.is_favorite(title_id, profile_id=profile.id)
    return data


@app.get("/api/catalog/seasons/{series_id}/{season_number}")
async def get_season_episodes(series_id: str, season_number: int, profile_id: str = Query("default")) -> dict[str, Any]:
    """Retrieve episodes for a specific TV series season with SQLite caching."""
    profile = get_profile_by_id(profile_id)
    # Check SQLite cache first
    cached_season = await db.get_season(series_id, season_number)
    if cached_season and cached_season.episodes:
        return cached_season.to_dict()

    try:
        season = await source_manager.get_season(series_id, season_number)
        if season and season.episodes:
            # Enrich season episodes with TMDb if tmdb_id is available
            title_data = await db.get_title(series_id)
            tmdb_id = title_data.get("tmdb_id") if title_data else None
            if tmdb_id:
                await metadata_enricher.enrich_tv_season(tmdb_id, season)
            await db.save_season(series_id, season)
        return season.to_dict()
    except Exception as err:
        _LOGGER.error("Error fetching season %s for %s: %s", season_number, series_id, err)
        raise HTTPException(status_code=404, detail=f"Stagione non trovata: {err}")


@app.post("/api/history")
async def save_progress(req: ProgressRequest) -> dict[str, Any]:
    """Save or update video watch progress in SQLite database scoped by profile."""
    await db.save_watch_progress(
        media_id=req.media_id,
        title=req.title,
        media_type=req.media_type,
        poster_url=req.poster_url,
        season_number=req.season_number,
        episode_number=req.episode_number,
        progress_seconds=req.progress_seconds,
        duration_seconds=req.duration_seconds,
        profile_id=req.profile_id,
    )

    # If Trakt is connected for profile, scrobble progress
    profile = get_profile_by_id(req.profile_id)
    trakt = get_profile_trakt_client(profile)
    if trakt and trakt.is_authenticated and req.duration_seconds > 0:
        percent = (req.progress_seconds / req.duration_seconds) * 100
        action = "stop" if percent >= 80 else "pause"
        asyncio.create_task(
            trakt.scrobble_action(
                action=action,
                media_type=req.media_type,
                title=req.title,
                year=req.year,
                tmdb_id=req.tmdb_id,
                imdb_id=req.imdb_id,
                season_number=req.season_number,
                episode_number=req.episode_number,
                progress_percent=percent,
            )
        )

    return {"status": "ok"}


@app.get("/api/history")
async def get_history(
    limit: int = Query(30, ge=1, le=100),
    profile_id: str = Query("default"),
) -> list[dict[str, Any]]:
    """Retrieve user watch history from SQLite database for active profile."""
    return await db.get_watch_history(profile_id=profile_id, limit=limit)


@app.get("/api/history/continue")
async def get_continue_watching(
    limit: int = Query(20, ge=1, le=50),
    profile_id: str = Query("default"),
) -> list[dict[str, Any]]:
    """Retrieve curated continue watching list for active profile."""
    return await db.get_continue_watching(profile_id=profile_id, limit=limit)


@app.get("/api/history/watched")
async def get_watched_list(
    limit: int = Query(30, ge=1, le=100),
    profile_id: str = Query("default"),
) -> list[dict[str, Any]]:
    """Retrieve watched / completed titles for active profile."""
    return await db.get_watched_history(profile_id=profile_id, limit=limit)


@app.delete("/api/history/{media_id}")
async def delete_history_item(
    media_id: str,
    profile_id: str = Query("default"),
) -> dict[str, Any]:
    """Remove a media title from watch history for active profile."""
    await db.delete_watch_history(media_id, profile_id=profile_id)
    return {"status": "ok", "deleted": media_id}


@app.get("/api/history/progress/{media_id}")
async def get_media_progress(
    media_id: str,
    profile_id: str = Query("default"),
) -> dict[str, Any]:
    """Get latest watch progress for a title and active profile."""
    progress = await db.get_media_progress(media_id, profile_id=profile_id)
    return {"status": "ok", "progress": progress}


@app.post("/api/favorites/toggle")
async def toggle_favorite(req: FavoriteRequest) -> dict[str, Any]:
    """Toggle a title as user favorite in SQLite database for active profile."""
    is_fav = await db.toggle_favorite(
        title_id=req.title_id,
        media_type=req.media_type,
        title=req.title,
        poster_url=req.poster_url,
        profile_id=req.profile_id,
    )

    # Sync to Trakt watchlist if authenticated
    profile = get_profile_by_id(req.profile_id)
    trakt = get_profile_trakt_client(profile)
    if trakt and trakt.is_authenticated:
        asyncio.create_task(
            trakt.sync_favorite(
                media_type=req.media_type,
                title=req.title,
                tmdb_id=req.tmdb_id,
                imdb_id=req.imdb_id,
                is_favorite=is_fav,
            )
        )

    return {"status": "ok", "favorite": is_fav}


@app.get("/api/favorites")
async def get_favorites(profile_id: str = Query("default")) -> list[dict[str, Any]]:
    """Retrieve all user favorites from SQLite database for active profile."""
    return await db.get_favorites(profile_id=profile_id)



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

    success, actual_entity = await ha_client.play_on_device(
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

    # Start active tracker to sync watch progress from Home Assistant Cast entity
    cast_profile = get_profile_by_id(req.profile_id)
    cast_trakt = get_profile_trakt_client(cast_profile)

    ha_client.start_cast_tracker(
        entity_id=actual_entity,
        media_id=req.media_id or "media",
        title=req.title,
        media_type=req.media_type,
        poster_url=req.poster_url,
        season_number=req.season_number,
        episode_number=req.episode_number,
        db=db,
        seek_position=req.seek_seconds,
        profile_id=req.profile_id,
        trakt_client=cast_trakt,
        year=req.year,
        tmdb_id=req.tmdb_id,
        imdb_id=req.imdb_id,
    )


    return {
        "success": True,
        "entity_id": actual_entity,
        "stream_url": lan_stream_url,
        "token": token,
    }


class CastControlRequest(BaseModel):
    entity_id: str
    command: str
    value: float | None = None


@app.get("/api/cast/status")
async def get_cast_status(entity_id: str | None = None) -> dict[str, Any]:
    """Get active cast playback status and progress."""
    return await ha_client.get_cast_status(entity_id)


@app.post("/api/cast/control")
async def control_cast(req: CastControlRequest) -> dict[str, Any]:
    """Control cast playback (play, pause, stop, seek, volume)."""
    success = await ha_client.control_cast(req.entity_id, req.command, req.value)
    return {"success": success}


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
