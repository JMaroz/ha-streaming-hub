"""Home Assistant Core API client via Supervisor Token."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

import aiohttp

from .models import CastDeviceInfo

_LOGGER = logging.getLogger(__name__)

SUPERVISOR_URL = "http://supervisor/core/api"
FLAG_PLAY_MEDIA = 512  # MediaPlayerEntityFeature.PLAY_MEDIA


class HACoreClient:
    """Client for interacting with Home Assistant Core REST API."""

    def __init__(self, token: str | None = None, base_url: str = SUPERVISOR_URL) -> None:
        """Initialize Home Assistant Core client."""
        self.token = token or os.getenv("SUPERVISOR_TOKEN", "")
        self.base_url = base_url.rstrip("/")
        self._cached_host_ip: str | None = None

    @property
    def is_available(self) -> bool:
        """Check if supervisor token is available."""
        return bool(self.token)

    def _get_headers(self) -> dict[str, str]:
        """Get authentication headers."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def get_config(self) -> dict[str, Any] | None:
        """Fetch Home Assistant Core system configuration."""
        if not self.is_available:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/config",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as err:
            _LOGGER.debug("Could not fetch HA config: %s", err)
        return None

    async def get_host_ip_or_url(self, default_port: int = 8099) -> str:
        """Determine the host IP or address accessible by LAN cast devices."""
        if self._cached_host_ip:
            return self._cached_host_ip

        # Check explicit environment override
        env_host = os.getenv("HA_HOST_IP")
        if env_host:
            self._cached_host_ip = env_host
            return env_host

        # Query HA Core config for internal_url
        config = await self.get_config()
        if config:
            internal_url = config.get("internal_url")
            if internal_url:
                parsed = urlparse(internal_url)
                if parsed.hostname and parsed.hostname != "localhost":
                    self._cached_host_ip = parsed.hostname
                    return self._cached_host_ip

            external_url = config.get("external_url")
            if external_url:
                parsed = urlparse(external_url)
                if parsed.hostname and parsed.hostname != "localhost":
                    self._cached_host_ip = parsed.hostname
                    return self._cached_host_ip

        # Fallback to local machine IP
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            self._cached_host_ip = ip
            return ip
        except Exception:
            return "127.0.0.1"

    async def get_media_players(self) -> list[CastDeviceInfo]:
        """Fetch all media players supporting video/stream playback from Home Assistant."""
        if not self.is_available:
            _LOGGER.debug("Supervisor token not available, returning empty players list")
            return []

        players: list[CastDeviceInfo] = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/states",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=6),
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.warning("HA Core /states returned status %s", resp.status)
                        return []
                    states: list[dict[str, Any]] = await resp.json()

            for state in states:
                entity_id = state.get("entity_id", "")
                if not entity_id.startswith("media_player."):
                    continue

                attrs = state.get("attributes", {})
                current_state = state.get("state", "unknown")
                if current_state in ("unavailable", "unknown"):
                    continue

                # Skip browser players or TTS targets
                if entity_id in ("media_player.browser", "media_player.web_browser"):
                    continue

                features = attrs.get("supported_features", 0)
                # Must support PLAY_MEDIA
                if not (features & FLAG_PLAY_MEDIA):
                    continue

                device_class = attrs.get("device_class")
                # Filter out pure speakers if known
                if device_class in ("speaker",):
                    continue

                friendly_name = attrs.get("friendly_name") or entity_id
                name_lower = friendly_name.lower()
                id_lower = entity_id.lower()

                # Filter out obvious smart speakers without screens
                speaker_keywords = ("nest mini", "home mini", "nest audio", "echo dot", "echo pop")
                if any(spk in name_lower for spk in speaker_keywords):
                    continue

                # Determine if it is a Cast or TV device
                is_cast = (
                    "cast" in id_lower
                    or "chromecast" in id_lower
                    or "cast" in name_lower
                    or "tv" in id_lower
                    or "tv" in name_lower
                    or device_class in ("tv", "receiver")
                )

                players.append(
                    CastDeviceInfo(
                        entity_id=entity_id,
                        name=friendly_name,
                        is_cast=is_cast,
                        state=current_state,
                        device_class=device_class,
                    )
                )

            # Prioritize Cast and TV devices first
            players.sort(key=lambda p: (not p.is_cast, p.name))
        except Exception as err:
            _LOGGER.error("Failed to fetch media players from Home Assistant: %s", err)

        return players

    async def play_on_device(
        self,
        entity_id: str,
        media_url: str,
        title: str,
        poster_url: str | None = None,
        mime_type: str = "application/vnd.apple.mpegurl",
    ) -> bool:
        """Send play_media command to specified Home Assistant entity."""
        if not self.is_available:
            _LOGGER.error("Cannot play media: SUPERVISOR_TOKEN not configured")
            return False

        payload: dict[str, Any] = {
            "entity_id": entity_id,
            "media_content_id": media_url,
            "media_content_type": mime_type,
            "extra": {
                "title": title,
                "thumb": poster_url,
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/services/media_player/play_media",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    success = resp.status in (200, 201)
                    if not success:
                        body = await resp.text()
                        _LOGGER.warning("play_media returned status %s: %s", resp.status, body)
                    return success
        except Exception as err:
            _LOGGER.error("Error sending play_media to %s: %s", entity_id, err)
            return False
