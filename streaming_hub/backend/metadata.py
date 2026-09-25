"""Metadata enrichment service using TMDb API with free public Cinemeta/TVmaze fallback."""

from __future__ import annotations

import contextlib
import logging
import re
from typing import Any
from urllib.parse import quote_plus

import aiohttp

from .models import Movie, TvSeries

_LOGGER = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
TMDB_BACKDROP_BASE = "https://image.tmdb.org/t/p/w1280"
CINEMETA_BASE_URL = "https://v3-cinemeta.strem.io/meta"
USER_AGENT = "Mozilla/5.0 (HomeAssistant/StreamingHub; it-IT)"


class MetadataEnricher:
    """Enriches Movie and TvSeries models with plot, cast, director, high-res posters, and ratings."""

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        tmdb_api_key: str | None = None,
    ) -> None:
        """Initialize the metadata enricher."""
        self._session = session
        self._own_session = False
        raw_key = (tmdb_api_key or "").strip().strip("\"'")
        if raw_key.lower().startswith("bearer "):
            raw_key = raw_key[7:].strip()
        self.tmdb_api_key = raw_key
        self._cache: dict[str, dict[str, Any]] = {}

    def _is_bearer_token(self) -> bool:
        """Determine if the TMDb key is a v4 Read Access Token."""
        return self.tmdb_api_key.startswith("eyJ") or len(self.tmdb_api_key) > 40 or "." in self.tmdb_api_key

    def _get_tmdb_auth(self) -> tuple[dict[str, str], dict[str, Any]]:
        """Return (headers, params) tuple for TMDb authentication."""
        if not self.tmdb_api_key:
            return {}, {}
        if self._is_bearer_token():
            return {"Authorization": f"Bearer {self.tmdb_api_key}"}, {}
        return {}, {"api_key": self.tmdb_api_key}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Ensure an active aiohttp session."""
        if self._session and not self._session.closed:
            return self._session
        self._session = aiohttp.ClientSession(headers={"User-Agent": USER_AGENT})
        self._own_session = True
        return self._session

    @staticmethod
    def _clean_title(title: str) -> str:
        """Strip quality and noise from title for cleaner metadata search."""
        t = re.sub(r"\[.*?\]", "", title)
        t = re.sub(r"\(.*?\)", "", t)
        t = re.sub(r"\b(4k|fhd|hd|sd|streaming|ita|subita)\b", "", t, flags=re.IGNORECASE)
        return " ".join(t.split())

    async def _get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Fetch JSON helper from given URL."""
        session = await self._get_session()
        req_headers = {"User-Agent": USER_AGENT}
        if headers:
            req_headers.update(headers)
        try:
            async with session.get(
                url, params=params, headers=req_headers, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as err:
            _LOGGER.debug("Request failed for %s: %s", url, err)
        return None

    async def close(self) -> None:
        """Close session if internally owned."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    async def _search_cinemeta_imdb_id(self, media_type: str, title: str) -> str | None:
        """Search Cinemeta by title to resolve an IMDb ID."""
        clean = self._clean_title(title)
        query = quote_plus(clean)
        url = f"{CINEMETA_BASE_URL}/catalog/{media_type}/top/search={query}.json"
        try:
            data = await self._get_json(url)
            if data and isinstance(data, dict):
                metas = data.get("metas", [])
                if metas and isinstance(metas[0], dict) and metas[0].get("id"):
                    return metas[0]["id"]
        except Exception as err:
            _LOGGER.debug("Cinemeta title search failed for %s: %s", title, err)
        return None

    async def enrich_movie(self, movie: Movie) -> Movie:
        """Enrich movie details using TMDb or free fallback."""
        cache_key = f"movie:{movie.id}"
        if cache_key in self._cache:
            self._apply_movie_metadata(movie, self._cache[cache_key])
            return movie

        metadata: dict[str, Any] | None = None
        if self.tmdb_api_key:
            metadata = await self._fetch_tmdb_movie(movie)

        if not metadata and not movie.imdb_id:
            movie.imdb_id = await self._search_cinemeta_imdb_id("movie", movie.title)

        if not metadata and movie.imdb_id:
            metadata = await self._fetch_cinemeta("movie", movie.imdb_id)

        if metadata:
            self._cache[cache_key] = metadata
            self._apply_movie_metadata(movie, metadata)

        return movie

    async def enrich_tv_series(self, series: TvSeries) -> TvSeries:
        """Enrich TV series details using TMDb or free fallback."""
        cache_key = f"tv:{series.id}"
        if cache_key in self._cache:
            self._apply_tv_metadata(series, self._cache[cache_key])
            return series

        metadata: dict[str, Any] | None = None
        if self.tmdb_api_key:
            metadata = await self._fetch_tmdb_tv(series)

        if not metadata and not series.imdb_id:
            series.imdb_id = await self._search_cinemeta_imdb_id("series", series.title)

        if not metadata and series.imdb_id:
            metadata = await self._fetch_cinemeta("series", series.imdb_id)

        if not metadata:
            metadata = await self._fetch_tvmaze(series.title)

        if metadata:
            self._cache[cache_key] = metadata
            self._apply_tv_metadata(series, metadata)

        return series

    async def _fetch_tmdb_movie(self, movie: Movie) -> dict[str, Any] | None:
        """Fetch movie metadata from TMDb."""
        auth_headers, auth_params = self._get_tmdb_auth()
        try:
            tmdb_id = movie.tmdb_id
            if not tmdb_id:
                clean_title = self._clean_title(movie.title)
                search_url = f"{TMDB_BASE_URL}/search/movie"
                params: dict[str, Any] = {"query": clean_title, "language": "it-IT", **auth_params}
                if movie.year:
                    params["year"] = str(movie.year)
                data = await self._get_json(search_url, params=params, headers=auth_headers)
                if data and data.get("results"):
                    tmdb_id = data["results"][0].get("id")

            if not tmdb_id:
                return None

            detail_url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
            params = {"language": "it-IT", "append_to_response": "credits", **auth_params}
            return await self._get_json(detail_url, params=params, headers=auth_headers)
        except Exception as err:
            _LOGGER.debug("TMDb fetch movie failed for %s: %s", movie.title, err)
            return None

    async def _fetch_tmdb_tv(self, series: TvSeries) -> dict[str, Any] | None:
        """Fetch TV series metadata from TMDb."""
        auth_headers, auth_params = self._get_tmdb_auth()
        try:
            tmdb_id = series.tmdb_id
            if not tmdb_id:
                clean_title = self._clean_title(series.title)
                search_url = f"{TMDB_BASE_URL}/search/tv"
                params: dict[str, Any] = {"query": clean_title, "language": "it-IT", **auth_params}
                if series.year:
                    params["first_air_date_year"] = str(series.year)
                data = await self._get_json(search_url, params=params, headers=auth_headers)
                if data and data.get("results"):
                    tmdb_id = data["results"][0].get("id")

            if not tmdb_id:
                return None

            detail_url = f"{TMDB_BASE_URL}/tv/{tmdb_id}"
            params = {"language": "it-IT", "append_to_response": "credits", **auth_params}
            return await self._get_json(detail_url, params=params, headers=auth_headers)
        except Exception as err:
            _LOGGER.debug("TMDb fetch TV series failed for %s: %s", series.title, err)
            return None

    async def _fetch_cinemeta(self, media_type: str, imdb_id: str) -> dict[str, Any] | None:
        """Fetch metadata from Cinemeta using IMDb ID."""
        url = f"{CINEMETA_BASE_URL}/{media_type}/{imdb_id}.json"
        data = await self._get_json(url)
        if data and isinstance(data, dict):
            return data.get("meta")
        return None

    async def _fetch_tvmaze(self, title: str) -> dict[str, Any] | None:
        """Fetch TV show metadata from TVmaze API."""
        clean_title = self._clean_title(title)
        url = f"https://api.tvmaze.com/singlesearch/shows?q={quote_plus(clean_title)}"
        data = await self._get_json(url)
        if data and isinstance(data, dict):
            genres = data.get("genres", [])
            rating_obj = data.get("rating", {})
            rating = rating_obj.get("average") if isinstance(rating_obj, dict) else None
            summary = data.get("summary")
            if summary:
                summary = re.sub(r"<[^>]+>", "", summary).strip()
            image = data.get("image", {})
            poster = image.get("original") or image.get("medium") if isinstance(image, dict) else None
            return {
                "name": data.get("name"),
                "overview": summary,
                "poster_url": poster,
                "genres": genres,
                "vote_average": rating,
            }
        return None

    def _apply_movie_metadata(self, movie: Movie, meta: dict[str, Any]) -> None:
        """Apply enriched metadata to Movie object."""
        if meta.get("id"):
            with contextlib.suppress(Exception):
                movie.tmdb_id = int(meta["id"])
        if meta.get("imdb_id"):
            movie.imdb_id = str(meta["imdb_id"])

        if meta.get("overview"):
            movie.description = meta["overview"]

        if meta.get("poster_path"):
            movie.poster_url = f"{TMDB_IMAGE_BASE}{meta['poster_path']}"
        elif meta.get("poster") and not movie.poster_url:
            movie.poster_url = meta["poster"]
        elif meta.get("poster_url") and not movie.poster_url:
            movie.poster_url = meta["poster_url"]

        if meta.get("backdrop_path"):
            movie.backdrop_url = f"{TMDB_BACKDROP_BASE}{meta['backdrop_path']}"
        elif meta.get("background") and not movie.backdrop_url:
            movie.backdrop_url = meta["background"]

        if meta.get("vote_average"):
            with contextlib.suppress(Exception):
                movie.rating = round(float(meta["vote_average"]), 1)
        elif meta.get("imdbRating") and not movie.rating:
            with contextlib.suppress(Exception):
                movie.rating = round(float(meta["imdbRating"]), 1)

        if meta.get("runtime") and not movie.duration:
            movie.duration = int(meta["runtime"])

        if meta.get("genres"):
            genres = []
            for g in meta["genres"]:
                if isinstance(g, dict) and "name" in g:
                    genres.append(g["name"])
                elif isinstance(g, str):
                    genres.append(g)
            if genres:
                movie.genres = genres

        if meta.get("credits"):
            credits = meta["credits"]
            cast = [c["name"] for c in credits.get("cast", [])[:5] if "name" in c]
            if cast:
                movie.cast = cast
            crew = credits.get("crew", [])
            for cr in crew:
                if cr.get("job") == "Director":
                    movie.director = cr.get("name")
                    break

    def _apply_tv_metadata(self, series: TvSeries, meta: dict[str, Any]) -> None:
        """Apply enriched metadata to TvSeries object."""
        if meta.get("id"):
            with contextlib.suppress(Exception):
                series.tmdb_id = int(meta["id"])
        if meta.get("imdb_id"):
            series.imdb_id = str(meta["imdb_id"])

        if meta.get("overview"):
            series.description = meta["overview"]

        if meta.get("poster_path"):
            series.poster_url = f"{TMDB_IMAGE_BASE}{meta['poster_path']}"
        elif meta.get("poster") and not series.poster_url:
            series.poster_url = meta["poster"]
        elif meta.get("poster_url") and not series.poster_url:
            series.poster_url = meta["poster_url"]

        if meta.get("backdrop_path"):
            series.backdrop_url = f"{TMDB_BACKDROP_BASE}{meta['backdrop_path']}"
        elif meta.get("background") and not series.backdrop_url:
            series.backdrop_url = meta["background"]

        if meta.get("vote_average"):
            with contextlib.suppress(Exception):
                series.rating = round(float(meta["vote_average"]), 1)
        elif meta.get("imdbRating") and not series.rating:
            with contextlib.suppress(Exception):
                series.rating = round(float(meta["imdbRating"]), 1)

        if meta.get("genres"):
            genres = []
            for g in meta["genres"]:
                if isinstance(g, dict) and "name" in g:
                    genres.append(g["name"])
                elif isinstance(g, str):
                    genres.append(g)
            if genres:
                series.genres = genres

    async def enrich_tv_season(self, series_tmdb_id: int | None, season: Any) -> Any:
        """Enrich TV season episodes with TMDb episode titles, overviews, and screenshots."""
        if not self.tmdb_api_key or not series_tmdb_id:
            return season

        auth_headers, auth_params = self._get_tmdb_auth()
        season_url = f"{TMDB_BASE_URL}/tv/{series_tmdb_id}/season/{season.number}"
        params = {"language": "it-IT", **auth_params}
        try:
            data = await self._get_json(season_url, params=params, headers=auth_headers)
            if not data or "episodes" not in data:
                return season

            tmdb_eps = {e["episode_number"]: e for e in data["episodes"] if "episode_number" in e}
            for ep in season.episodes:
                t_ep = tmdb_eps.get(ep.episode_number)
                if not t_ep:
                    continue
                ep_name = (t_ep.get("name") or "").strip()
                if ep_name:
                    if not ep.title or ep.title.lower().startswith("episodio"):
                        ep.title = f"Episodio {ep.episode_number}: {ep_name}"
                    else:
                        ep.title = f"{ep.title} - {ep_name}"
                if t_ep.get("overview") and not ep.description:
                    ep.description = t_ep["overview"]
                if t_ep.get("still_path") and not ep.poster_url:
                    ep.poster_url = f"{TMDB_IMAGE_BASE}{t_ep['still_path']}"
        except Exception as err:
            _LOGGER.debug("TMDb enrich season %s failed: %s", season.number, err)

        return season
