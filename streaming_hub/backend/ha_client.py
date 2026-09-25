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

                # Determine if it is a genuine video/stream receiver
                is_stream_capable = (
                    "cast" in id_lower
                    or "chromecast" in id_lower
                    or "google" in id_lower
                    or "tpm" in id_lower
                    or "shield" in id_lower
                    or "mibox" in id_lower
                    or "firetv" in id_lower
                    or "appletv" in id_lower
                    or "apple_tv" in id_lower
                    or "kodi" in id_lower
                    or "roku" in id_lower
                    or "app_id" in attrs
                    or "media_content_type" in attrs
                    or attrs.get("app_name") is not None
                )

                # Strictly discard non-streaming TV remote controls (e.g. philips_tv, ambilight controls)
                if not is_stream_capable:
                    _LOGGER.debug("Skipping TV remote control entity: %s (%s)", entity_id, friendly_name)
                    continue

                players.append(
                    CastDeviceInfo(
                        entity_id=entity_id,
                        name=friendly_name,
                        is_cast=True,
                        state=current_state,
                        device_class=device_class,
                    )
                )

            # Deduplicate by friendly name (e.g. if multiple entities map to the same screen)
            unique_players: dict[str, CastDeviceInfo] = {}
            for p in players:
                if p.name in unique_players:
                    # Prefer explicit Cast / TPM chassis entity
                    if any(k in p.entity_id.lower() for k in ("tpm", "cast", "chromecast")):
                        unique_players[p.name] = p
                else:
                    unique_players[p.name] = p

            final_players = list(unique_players.values())
            final_players.sort(key=lambda p: p.name)
            return final_players
        except Exception as err:
            _LOGGER.error("Failed to fetch media players from Home Assistant: %s", err)

        return []

    async def play_on_device(
        self,
        entity_id: str,
        media_url: str,
        title: str,
        poster_url: str | None = None,
        mime_type: str = "application/vnd.apple.mpegurl",
    ) -> bool:
        """Send play_media command to specified Home Assistant entity with companion fallback."""
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

        # Timeout 25s to allow standby TVs to turn on and launch Cast receiver
        success = False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/services/media_player/play_media",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=25),
                ) as resp:
                    success = resp.status in (200, 201)
                    if not success:
                        body = await resp.text()
                        _LOGGER.warning("play_media on %s returned status %s: %s", entity_id, resp.status, body)
                    else:
                        return True
        except Exception as err:
            _LOGGER.error("Error sending play_media to %s: %s", entity_id, err)

        # Smart fallback: if the chosen entity failed (e.g. TV control entity returned 500),
        # automatically try companion Cast entity (e.g. tpm191e)
        try:
            companion_players = await self.get_media_players()
            clean_target = entity_id.replace("media_player.", "").split("_")[0]
            alt_player = next(
                (
                    p for p in companion_players
                    if p.is_cast and p.entity_id != entity_id and (
                        clean_target in p.entity_id.lower()
                        or "tpm" in p.entity_id.lower()
                        or "cast" in p.entity_id.lower()
                    )
                ),
                None,
            )
            if alt_player:
                _LOGGER.info("Attempting automatic fallback cast to companion device %s (%s)...", alt_player.entity_id, alt_player.name)
                alt_payload = dict(payload)
                alt_payload["entity_id"] = alt_player.entity_id
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/services/media_player/play_media",
                        headers=self._get_headers(),
                        json=alt_payload,
                        timeout=aiohttp.ClientTimeout(total=25),
                    ) as resp:
                        if resp.status in (200, 201):
                            _LOGGER.info("Automatic fallback cast to %s succeeded!", alt_player.entity_id)
                            return True
        except Exception as alt_err:
            _LOGGER.debug("Companion fallback cast error: %s", alt_err)

        return False
