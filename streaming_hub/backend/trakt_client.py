"""Trakt.tv API v2 client for playback scrobbling, device authentication, and cloud sync."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

TRAKT_API_URL = "https://api.trakt.tv"
USER_AGENT = "HomeAssistant-StreamingHub/1.2.3"


class TraktClient:
    """Client for Trakt.tv API v2."""

    def __init__(
        self,
        client_id: str,
        access_token: str = "",
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize Trakt.tv client."""
        self.client_id = client_id.strip()
        self.access_token = access_token.strip()
        self._session = session
        self._own_session = False

    @property
    def is_configured(self) -> bool:
        """Check if Trakt client_id is present."""
        return bool(self.client_id)

    @property
    def is_authenticated(self) -> bool:
        """Check if user access_token is present."""
        return bool(self.client_id and self.access_token)

    def _get_headers(self) -> dict[str, str]:
        """Generate mandatory Trakt v2 API headers."""
        headers = {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": self.client_id,
            "User-Agent": USER_AGENT,
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    async def _get_session(self) -> aiohttp.ClientSession:
        """Ensure active aiohttp ClientSession."""
        if self._session and not self._session.closed:
            return self._session
        self._session = aiohttp.ClientSession()
        self._own_session = True
        return self._session

    async def close(self) -> None:
        """Close internally managed session."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    # --- Device OAuth Flow ---
    async def generate_device_code(self) -> dict[str, Any] | None:
        """Request a device code and verification URL for linking account."""
        if not self.client_id:
            return None
        session = await self._get_session()
        url = f"{TRAKT_API_URL}/oauth/device/code"
        payload = {"client_id": self.client_id}
        try:
            async with session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    return await resp.json()
                _LOGGER.warning("Trakt device code request failed with status %s", resp.status)
        except Exception as err:
            _LOGGER.debug("Trakt device code exception: %s", err)
        return None

    async def poll_device_token(self, device_code: str, client_secret: str = "") -> dict[str, Any] | None:
        """Poll for token once user has verified the code on https://trakt.tv/activate."""
        if not self.client_id:
            return None
        session = await self._get_session()
        url = f"{TRAKT_API_URL}/oauth/device/token"
        payload = {
            "code": device_code,
            "client_id": self.client_id,
            "client_secret": client_secret,
        }
        try:
            async with session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as err:
            _LOGGER.debug("Trakt device token poll exception: %s", err)
        return None

    # --- Scrobbling API ---
    def _build_media_payload(
        self,
        media_type: str,
        title: str,
        year: int | None = None,
        tmdb_id: int | None = None,
        imdb_id: str | None = None,
        season_number: int | None = None,
        episode_number: int | None = None,
        progress_percent: float = 0,
    ) -> dict[str, Any]:
        """Construct scrobble JSON payload."""
        ids: dict[str, Any] = {}
        if tmdb_id:
            ids["tmdb"] = tmdb_id
        if imdb_id:
            ids["imdb"] = imdb_id

        # Clamp progress between 0 and 100
        progress = max(0.0, min(100.0, round(progress_percent, 2)))

        if media_type == "movie":
            movie_obj: dict[str, Any] = {"title": title}
            if year:
                movie_obj["year"] = year
            if ids:
                movie_obj["ids"] = ids
            return {"movie": movie_obj, "progress": progress}

        # TV Episode
        episode_obj: dict[str, Any] = {
            "season": season_number or 1,
            "number": episode_number or 1,
        }
        show_obj: dict[str, Any] = {"title": title}
        if year:
            show_obj["year"] = year
        if ids:
            show_obj["ids"] = ids

        return {
            "show": show_obj,
            "episode": episode_obj,
            "progress": progress,
        }

    async def scrobble_action(
        self,
        action: str,  # "start", "pause", "stop"
        media_type: str,
        title: str,
        year: int | None = None,
        tmdb_id: int | None = None,
        imdb_id: str | None = None,
        season_number: int | None = None,
        episode_number: int | None = None,
        progress_percent: float = 0,
    ) -> bool:
        """Send a scrobble action (start, pause, or stop) to Trakt."""
        if not self.is_authenticated:
            return False

        url = f"{TRAKT_API_URL}/scrobble/{action}"
        payload = self._build_media_payload(
            media_type=media_type,
            title=title,
            year=year,
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            season_number=season_number,
            episode_number=episode_number,
            progress_percent=progress_percent,
        )

        session = await self._get_session()
        try:
            async with session.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=6),
            ) as resp:
                if resp.status in (200, 201):
                    _LOGGER.info("Trakt scrobble '%s' succeeded for '%s' (%.1f%%)", action, title, progress_percent)
                    return True
                _LOGGER.debug("Trakt scrobble '%s' returned status %s for '%s'", action, resp.status, title)
        except Exception as err:
            _LOGGER.debug("Trakt scrobble failed for '%s': %s", title, err)
        return False

    async def get_watchlist(self) -> list[dict[str, Any]]:
        """Fetch user watchlist (movies and shows)."""
        if not self.is_authenticated:
            return []
        url = f"{TRAKT_API_URL}/sync/watchlist"
        session = await self._get_session()
        try:
            async with session.get(url, headers=self._get_headers(), timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as err:
            _LOGGER.debug("Trakt get_watchlist failed: %s", err)
        return []

    async def sync_favorite(
        self,
        media_type: str,
        title: str,
        tmdb_id: int | None = None,
        imdb_id: str | None = None,
        is_favorite: bool = True,
    ) -> bool:
        """Add or remove an item from Trakt favorites/watchlist."""
        if not self.is_authenticated:
            return False
        endpoint = "watchlist" if is_favorite else "watchlist/remove"
        url = f"{TRAKT_API_URL}/sync/{endpoint}"

        ids: dict[str, Any] = {}
        if tmdb_id:
            ids["tmdb"] = tmdb_id
        if imdb_id:
            ids["imdb"] = imdb_id

        item = {"title": title}
        if ids:
            item["ids"] = ids

        payload_key = "movies" if media_type == "movie" else "shows"
        payload = {payload_key: [item]}

        session = await self._get_session()
        try:
            async with session.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=6),
            ) as resp:
                return resp.status in (200, 201)
        except Exception as err:
            _LOGGER.debug("Trakt sync favorite failed: %s", err)
            return False
