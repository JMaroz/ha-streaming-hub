"""Subtitle management, SRT to WebVTT conversion, and OpenSubtitles fallback provider."""

from __future__ import annotations

import logging
import re
import secrets
from typing import Any
import urllib.parse

import aiohttp

from .models import SubtitleTrack

_LOGGER = logging.getLogger(__name__)


def srt_to_vtt(srt_text: str) -> str:
    """Convert SubRip (.srt) subtitle text into standard WebVTT format.

    Replaces comma millisecond separators with dots and prepends the WEBVTT header.
    """
    if not srt_text:
        return "WEBVTT\n\n"

    # Normalize line breaks
    text = srt_text.replace("\r\n", "\n").replace("\r", "\n")

    # If already WebVTT, return directly
    if text.strip().startswith("WEBVTT"):
        return text

    # Pattern for SRT timestamps: 00:01:20,000 --> 00:01:23,500
    timestamp_pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}),(\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}),(\d{3})"
    )

    def _replace_ts(match: re.Match[str]) -> str:
        return f"{match.group(1)}.{match.group(2)} --> {match.group(3)}.{match.group(4)}"

    vtt_body = timestamp_pattern.sub(_replace_ts, text)
    return f"WEBVTT\n\n{vtt_body.strip()}\n"


class SubtitleManager:
    """Manager for storing, converting, and searching subtitle tracks."""

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize SubtitleManager."""
        self.api_key = api_key or ""
        self._vtt_cache: dict[str, str] = {}  # sub_id -> vtt_content
        self._tracks_cache: dict[str, list[SubtitleTrack]] = {}  # media_id -> list[SubtitleTrack]

    def register_vtt(
        self,
        vtt_content: str,
        language: str = "it",
        label: str = "Italiano",
        is_default: bool = False,
    ) -> SubtitleTrack:
        """Register a WebVTT content string and return a SubtitleTrack."""
        sub_id = secrets.token_hex(6)
        formatted_vtt = srt_to_vtt(vtt_content)
        self._vtt_cache[sub_id] = formatted_vtt

        return SubtitleTrack(
            id=sub_id,
            language=language,
            label=label,
            url=f"/api/subtitles/{sub_id}",
            format="vtt",
            is_default=is_default,
        )

    def get_vtt(self, sub_id: str) -> str | None:
        """Retrieve stored WebVTT text by subtitle ID."""
        return self._vtt_cache.get(sub_id)

    async def search_subtitles(
        self,
        imdb_id: str | None = None,
        tmdb_id: int | None = None,
        query: str | None = None,
        season_number: int | None = None,
        episode_number: int | None = None,
        languages: str = "it,en",
    ) -> list[SubtitleTrack]:
        """Search subtitles from OpenSubtitles REST API with fail-open fallback.

        Guarantees zero interruption: returns empty list if external service is down.
        """
        cache_key = f"{imdb_id}_{tmdb_id}_{query}_{season_number}_{episode_number}_{languages}"
        if cache_key in self._tracks_cache:
            return self._tracks_cache[cache_key]

        tracks: list[SubtitleTrack] = []
        if not imdb_id and not query:
            return tracks

        clean_imdb = None
        if imdb_id:
            clean_imdb = str(imdb_id).replace("tt", "").strip()

        params: dict[str, Any] = {"languages": languages}
        if clean_imdb and clean_imdb.isdigit():
            params["imdb_id"] = clean_imdb
        elif query:
            params["query"] = query

        if season_number is not None and season_number > 0:
            params["season_number"] = season_number
        if episode_number is not None and episode_number > 0:
            params["episode_number"] = episode_number

        headers = {
            "User-Agent": "StreamingHub-HA/2.2.0",
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Api-Key"] = self.api_key

        url = "https://api.opensubtitles.com/api/v1/subtitles"
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=2.5),
                ) as resp,
            ):
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("data", [])[:5]:
                        attrs = item.get("attributes", {})
                        lang = attrs.get("language", "it").lower()
                        files = attrs.get("files", [])
                        if not files:
                            continue
                        file_id = files[0].get("file_id")
                        label = "Italiano" if lang == "it" else "English"
                        if attrs.get("foreign_parts_only"):
                            label += " (Forzati)"

                        sub_id = secrets.token_hex(6)
                        proxy_url = f"/api/subtitles/download/{file_id}"
                        track = SubtitleTrack(
                            id=sub_id,
                            language=lang,
                            label=label,
                            url=proxy_url,
                            format="vtt",
                            is_default=(lang == "it"),
                            is_forced=bool(attrs.get("foreign_parts_only")),
                        )
                        tracks.append(track)
        except Exception as err:
            _LOGGER.debug("OpenSubtitles fail-open fallback: %s", err)

        self._tracks_cache[cache_key] = tracks
        return tracks
