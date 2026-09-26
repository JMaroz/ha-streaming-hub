"""Home Assistant Core API client via Supervisor Token."""

from __future__ import annotations

import asyncio
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
        self._cast_trackers: dict[str, asyncio.Task] = {}
        self._active_cast_sessions: dict[str, dict[str, Any]] = {}

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
                if not attrs.get("friendly_name") or friendly_name.startswith("media_player.") or "tpm191e" in friendly_name.lower():
                    if "tpm191e" in entity_id.lower():
                        friendly_name = "Philips Smart TV (TPM191E)"
                    elif friendly_name.startswith("media_player."):
                        friendly_name = friendly_name.replace("media_player.", "").replace("_", " ").title()

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
    ) -> tuple[bool, str]:
        """Send play_media command to specified Home Assistant entity with companion fallback."""
        if not self.is_available:
            _LOGGER.error("Cannot play media: SUPERVISOR_TOKEN not configured")
            return False, entity_id

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
                        return True, entity_id
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
                            return True, alt_player.entity_id
        except Exception as alt_err:
            _LOGGER.debug("Companion fallback cast error: %s", alt_err)

        return False, entity_id

    async def get_entity_state(self, entity_id: str) -> dict[str, Any] | None:
        """Fetch current state and attributes of a Home Assistant entity."""
        if not self.is_available:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/states/{entity_id}",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as err:
            _LOGGER.debug("Could not fetch state for %s: %s", entity_id, err)
        return None

    async def call_media_player_service(
        self,
        service: str,
        entity_id: str,
        extra_data: dict[str, Any] | None = None,
    ) -> bool:
        """Call a media_player service in Home Assistant Core."""
        if not self.is_available:
            return False
        payload = {"entity_id": entity_id}
        if extra_data:
            payload.update(extra_data)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/services/media_player/{service}",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    return resp.status in (200, 201)
        except Exception as err:
            _LOGGER.warning("Error calling media_player.%s on %s: %s", service, entity_id, err)
            return False

    async def seek_media(self, entity_id: str, position_seconds: float) -> bool:
        """Send media_seek command to Home Assistant entity."""
        return await self.call_media_player_service(
            "media_seek",
            entity_id,
            {"seek_position": float(position_seconds)},
        )

    def start_cast_tracker(
        self,
        entity_id: str,
        media_id: str,
        title: str,
        media_type: str,
        poster_url: str | None,
        season_number: int | None,
        episode_number: int | None,
        db: Any,
        seek_position: float = 0,
        profile_id: str = "default",
        trakt_client: Any | None = None,
        year: int | None = None,
        tmdb_id: int | None = None,
        imdb_id: str | None = None,
    ) -> None:
        """Start background task to sync watch progress while playing on Cast device."""
        if entity_id in self._cast_trackers:
            self._cast_trackers[entity_id].cancel()

        self._active_cast_sessions[entity_id] = {
            "entity_id": entity_id,
            "media_id": media_id,
            "title": title,
            "media_type": media_type,
            "poster_url": poster_url,
            "season_number": season_number,
            "episode_number": episode_number,
            "seek_position": seek_position,
            "profile_id": profile_id,
        }

        task = asyncio.create_task(
            self._track_cast_playback(
                entity_id,
                media_id,
                title,
                media_type,
                poster_url,
                season_number,
                episode_number,
                db,
                seek_position,
                profile_id,
                trakt_client,
                year,
                tmdb_id,
                imdb_id,
            )
        )
        self._cast_trackers[entity_id] = task

    async def _track_cast_playback(
        self,
        entity_id: str,
        media_id: str,
        title: str,
        media_type: str,
        poster_url: str | None,
        season_number: int | None,
        episode_number: int | None,
        db: Any,
        seek_position: float,
        profile_id: str = "default",
        trakt_client: Any | None = None,
        year: int | None = None,
        tmdb_id: int | None = None,
        imdb_id: str | None = None,
    ) -> None:
        """Poll entity state and sync watch progress with SQLite database and Trakt."""
        _LOGGER.info("Starting Cast watch progress tracker for %s on %s (profile: %s)", title, entity_id, profile_id)
        seek_done = seek_position <= 5
        idle_counter = 0
        has_started_playing = False
        trakt_started = False

        # Wait initial 4 seconds for Cast receiver launch
        await asyncio.sleep(4)

        try:
            while True:
                await asyncio.sleep(4)
                state_data = await self.get_entity_state(entity_id)
                if not state_data:
                    idle_counter += 1
                    if idle_counter > 10:
                        break
                    continue

                state = state_data.get("state", "idle").lower()
                attrs = state_data.get("attributes", {})

                # If we need to seek to a resumed position, wait until state is playing
                if not seek_done and state == "playing":
                    _LOGGER.info("Seeking %s to resumed position %s seconds", entity_id, seek_position)
                    await self.seek_media(entity_id, seek_position)
                    seek_done = True
                    has_started_playing = True
                    await asyncio.sleep(1)
                    continue

                if state in ("playing", "paused", "buffering"):
                    idle_counter = 0
                    if state == "playing":
                        has_started_playing = True
                    pos = attrs.get("media_position")
                    dur = attrs.get("media_duration")
                    if pos is not None and float(pos) > 0:
                        pos_float = float(pos)
                        dur_float = float(dur or 0)
                        await db.save_watch_progress(
                            media_id=media_id,
                            title=title,
                            media_type=media_type,
                            poster_url=poster_url,
                            season_number=season_number,
                            episode_number=episode_number,
                            progress_seconds=pos_float,
                            duration_seconds=dur_float,
                            profile_id=profile_id,
                        )

                        # Trakt scrobble integration
                        if trakt_client and trakt_client.is_authenticated:
                            percent = (pos_float / dur_float * 100) if dur_float > 0 else 0
                            if not trakt_started and state == "playing":
                                trakt_started = True
                                asyncio.create_task(
                                    trakt_client.scrobble_action(
                                        "start", media_type, title, year, tmdb_id, imdb_id, season_number, episode_number, percent
                                    )
                                )
                elif state in ("off", "idle", "standby"):
                    idle_counter += 1
                    max_idle = 3 if has_started_playing else 8
                    if idle_counter >= max_idle:
                        _LOGGER.info("Cast device %s is %s, stopping tracker.", entity_id, state)
                        if trakt_client and trakt_client.is_authenticated and trakt_started:
                            asyncio.create_task(
                                trakt_client.scrobble_action(
                                    "stop", media_type, title, year, tmdb_id, imdb_id, season_number, episode_number, 100.0
                                )
                            )
                        break

                else:
                    idle_counter += 1
                    if idle_counter >= 8:
                        break
        except asyncio.CancelledError:
            _LOGGER.debug("Cast tracker cancelled for %s", entity_id)
        except Exception as err:
            _LOGGER.warning("Error in Cast tracker for %s: %s", entity_id, err)
        finally:
            self._cast_trackers.pop(entity_id, None)
            self._active_cast_sessions.pop(entity_id, None)

    async def get_cast_status(self, entity_id: str | None = None) -> dict[str, Any]:
        """Return the current playback state and progress of the active Cast entity."""
        target_id = entity_id
        session_info: dict[str, Any] = {}

        if target_id and target_id in self._active_cast_sessions:
            session_info = self._active_cast_sessions[target_id]
        elif not target_id and self._active_cast_sessions:
            target_id, session_info = next(iter(self._active_cast_sessions.items()))

        if not target_id:
            return {"active": False}

        state_data = await self.get_entity_state(target_id)
        if not state_data:
            return {"active": False, "entity_id": target_id}

        state = state_data.get("state", "idle").lower()
        attrs = state_data.get("attributes", {})

        is_active = state in ("playing", "paused", "buffering")

        if not is_active and target_id not in self._cast_trackers:
            return {"active": False, "entity_id": target_id, "state": state}

        # Keep active if tracker is running during startup
        if target_id in self._cast_trackers and not is_active:
            is_active = True

        raw_device_name = attrs.get("friendly_name") or target_id
        if "tpm191e" in target_id.lower() or "tpm191e" in raw_device_name.lower():
            friendly_device_name = "Philips Smart TV (TPM191E)"
        elif raw_device_name.startswith("media_player."):
            friendly_device_name = raw_device_name.replace("media_player.", "").replace("_", " ").title()
        else:
            friendly_device_name = raw_device_name

        return {
            "active": is_active,
            "entity_id": target_id,
            "device_name": friendly_device_name,
            "state": state,
            "title": session_info.get("title") or attrs.get("media_title") or "In riproduzione",
            "media_id": session_info.get("media_id"),
            "media_type": session_info.get("media_type"),
            "poster_url": session_info.get("poster_url") or attrs.get("entity_picture"),
            "season_number": session_info.get("season_number"),
            "episode_number": session_info.get("episode_number"),
            "media_position": float(attrs.get("media_position") or 0.0),
            "media_position_updated_at": attrs.get("media_position_updated_at"),
            "media_duration": float(attrs.get("media_duration") or 0.0),
            "volume_level": float(attrs.get("volume_level") or 1.0),
            "is_volume_muted": bool(attrs.get("is_volume_muted", False)),
        }

    async def control_cast(self, entity_id: str, command: str, value: float | None = None) -> bool:
        """Execute playback command on Cast entity."""
        if not self.is_available:
            return False

        cmd = command.lower()
        if cmd == "play":
            return await self.call_media_player_service("media_play", entity_id)
        elif cmd == "pause":
            return await self.call_media_player_service("media_pause", entity_id)
        elif cmd == "play_pause":
            return await self.call_media_player_service("media_play_pause", entity_id)
        elif cmd == "stop":
            if entity_id in self._cast_trackers:
                self._cast_trackers[entity_id].cancel()
            self._active_cast_sessions.pop(entity_id, None)
            return await self.call_media_player_service("media_stop", entity_id)
        elif cmd == "seek":
            if value is not None:
                return await self.seek_media(entity_id, max(0.0, float(value)))
            return False
        elif cmd == "volume_set":
            if value is not None:
                vol = max(0.0, min(1.0, float(value)))
                return await self.call_media_player_service("volume_set", entity_id, {"volume_level": vol})
            return False
        elif cmd == "volume_mute":
            muted = bool(value) if value is not None else True
            return await self.call_media_player_service("volume_mute", entity_id, {"is_volume_muted": muted})

        return False
