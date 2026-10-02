"""Service for fetching intro and end-credits (outro) skip segments."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

SKIPDB_BASE_URL = "https://api.skipdb.tv/api/segments"


class SkipSegmentManager:
    """Manages retrieval and caching of skip segments (intro and outro) for TV shows."""

    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        self._session = session
        self._cache: dict[str, dict[str, Any]] = {}

    def _get_cache_key(self, imdb_id: str, season: int, episode: int, duration: float | None) -> str:
        dur_bucket = int(duration // 10) if duration and duration > 60 else 0
        return f"{imdb_id}_{season}_{episode}_{dur_bucket}"

    async def get_skip_segments(
        self,
        imdb_id: str | None,
        season_number: int,
        episode_number: int,
        duration: float | None = None,
    ) -> dict[str, Any]:
        """Fetch intro and outro skip markers from SkipDB with local in-memory caching."""
        empty_result: dict[str, Any] = {
            "has_segments": False,
            "intro": None,
            "outro": None,
            "source": "none",
        }

        if not imdb_id or season_number < 1 or episode_number < 1:
            return empty_result

        clean_imdb = str(imdb_id).strip()
        if not clean_imdb.startswith("tt"):
            clean_imdb = f"tt{clean_imdb}"

        cache_key = self._get_cache_key(clean_imdb, season_number, episode_number, duration)
        if cache_key in self._cache:
            return self._cache[cache_key]

        params: dict[str, Any] = {
            "imdb_id": clean_imdb,
            "season": season_number,
            "episode": episode_number,
        }
        if duration and duration > 60:
            params["duration"] = int(duration)

        headers = {
            "User-Agent": "StreamingHub/2.2 (+https://github.com/JMaroz/streaming-hub-ha)",
            "Accept": "application/json",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=4.0)
            if self._session and not self._session.closed:
                async with self._session.get(
                    SKIPDB_BASE_URL, params=params, headers=headers, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = self._parse_skipdb_response(data)
                        self._cache[cache_key] = result
                        return result
            else:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        SKIPDB_BASE_URL, params=params, headers=headers
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            result = self._parse_skipdb_response(data)
                            self._cache[cache_key] = result
                            return result
        except Exception as err:
            _LOGGER.debug(
                "SkipDB lookup failed for %s S%sE%s: %s",
                clean_imdb,
                season_number,
                episode_number,
                err,
            )

        return empty_result

    def _parse_skipdb_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize SkipDB response into seconds."""
        segments = data.get("segments") or {}
        intro_raw = segments.get("intro")
        outro_raw = segments.get("outro")

        intro: dict[str, float] | None = None
        if intro_raw and isinstance(intro_raw, dict):
            start_ms = intro_raw.get("start_ms")
            end_ms = intro_raw.get("end_ms")
            if start_ms is not None and end_ms is not None and end_ms > start_ms:
                intro = {
                    "start": round(float(start_ms) / 1000.0, 1),
                    "end": round(float(end_ms) / 1000.0, 1),
                }

        outro: dict[str, float] | None = None
        if outro_raw and isinstance(outro_raw, dict):
            start_ms = outro_raw.get("start_ms")
            end_ms = outro_raw.get("end_ms")
            if start_ms is not None:
                outro_end = round(float(end_ms) / 1000.0, 1) if end_ms is not None else 0.0
                outro = {
                    "start": round(float(start_ms) / 1000.0, 1),
                    "end": outro_end,
                }

        has_segments = bool(intro or outro)
        return {
            "has_segments": has_segments,
            "intro": intro,
            "outro": outro,
            "source": "skipdb" if has_segments else "none",
        }
