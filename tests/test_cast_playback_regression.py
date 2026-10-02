"""Regression and reliability tests for Home Assistant Cast and media player playback."""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Self
from unittest.mock import AsyncMock, MagicMock, patch

if "aiohttp" not in sys.modules:
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        import types

        mock_aiohttp = types.ModuleType("aiohttp")
        mock_aiohttp.abc = types.ModuleType("aiohttp.abc")
        mock_aiohttp.abc.AbstractResolver = object

        class MockClientTimeout:
            def __init__(self, total: float = 0) -> None:
                self.total = total

        mock_aiohttp.ClientTimeout = MockClientTimeout
        mock_aiohttp.ClientSession = MagicMock
        sys.modules["aiohttp"] = mock_aiohttp
        sys.modules["aiohttp.abc"] = mock_aiohttp.abc

from streaming_hub.backend.ha_client import HACoreClient
from streaming_hub.backend.models import CastDeviceInfo


class TestCastPlaybackRegression:
    """Test suite ensuring 100% zero-regression reliability for Cast and media_player commands."""

    def setup_method(self, method=None) -> None:
        """Initialize HACoreClient with a test token."""
        self.client = HACoreClient(token="mock_supervisor_token", base_url="http://mock-supervisor/core/api")

    def test_availability_and_headers(self) -> None:
        """Test token presence and authentication headers."""
        assert self.client.is_available
        headers = self.client._get_headers()
        assert headers["Authorization"] == "Bearer mock_supervisor_token"
        assert headers["Content-Type"] == "application/json"

        unauthed = HACoreClient(token="")
        assert not unauthed.is_available

    def test_media_player_discovery_and_filtering(self) -> None:
        """Test that media players are discovered and non-streamable devices are discarded."""
        mock_states = [
            {
                "entity_id": "media_player.living_room_tv",
                "state": "on",
                "attributes": {
                    "friendly_name": "Living Room TV",
                    "supported_features": 512,  # FLAG_PLAY_MEDIA
                    "app_id": "com.google.android.youtube.tv",
                },
            },
            {
                "entity_id": "media_player.kitchen_nest_mini",
                "state": "idle",
                "attributes": {
                    "friendly_name": "Kitchen Nest Mini",
                    "supported_features": 512,
                    "device_class": "speaker",
                },
            },
            {
                "entity_id": "media_player.tpm191e_chassis",
                "state": "playing",
                "attributes": {
                    "friendly_name": "Philips Smart TV (TPM191E)",
                    "supported_features": 512,
                },
            },
            {
                "entity_id": "media_player.browser",
                "state": "idle",
                "attributes": {"supported_features": 512},
            },
            {
                "entity_id": "media_player.bedroom_tv_remote",
                "state": "on",
                "attributes": {
                    "friendly_name": "Bedroom TV Remote",
                    "supported_features": 128,  # Does not have FLAG_PLAY_MEDIA
                },
            },
            {
                "entity_id": "media_player.google_tv_2",
                "state": "on",
                "attributes": {
                    "friendly_name": "Master bedroom TV",
                    "supported_features": 512,
                    "device_class": "tv",
                },
            },
            {
                "entity_id": "media_player.google_tv",
                "state": "off",
                "attributes": {
                    "friendly_name": "Master bedroom TV",
                    "supported_features": 512,
                    "app_id": None,
                },
            },
        ]

        class MockResponse:
            def __init__(self, json_data: Any, status: int = 200) -> None:
                self._json = json_data
                self.status = status

            async def json(self) -> Any:
                return self._json

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: object) -> None:
                pass

        class MockClientSession:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def get(self, url: str, **kwargs: Any) -> MockResponse:
                return MockResponse(mock_states)

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: object) -> None:
                pass

        with patch("aiohttp.ClientSession", MockClientSession):
            players = asyncio.run(self.client.get_media_players())
            entity_ids = [p.entity_id for p in players]

            # Allowed stream targets
            assert "media_player.living_room_tv" in entity_ids
            assert "media_player.tpm191e_chassis" in entity_ids
            assert "media_player.google_tv" in entity_ids

            # Blocked / Filtered out / Deduplicated remotes
            assert "media_player.google_tv_2" not in entity_ids  # Deduplicated in favor of genuine Cast entity
            assert "media_player.kitchen_nest_mini" not in entity_ids  # Nest speaker
            assert "media_player.browser" not in entity_ids  # Browser target
            assert "media_player.bedroom_tv_remote" not in entity_ids  # No play_media feature

    def test_play_on_device_tier1_success(self) -> None:
        """Test play_on_device succeeds on Tier 1 (with extra metadata)."""
        captured_payloads: list[dict[str, Any]] = []

        class MockResponse:
            status = 200

            async def text(self) -> str:
                return "OK"

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: object) -> None:
                pass

        class MockSession:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def post(self, url: str, json: dict[str, Any], **kwargs: Any) -> MockResponse:
                captured_payloads.append(json)
                return MockResponse()

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: object) -> None:
                pass

        with patch("aiohttp.ClientSession", MockSession):
            success, entity = asyncio.run(
                self.client.play_on_device(
                    entity_id="media_player.living_room_tv",
                    media_url="http://192.168.1.10:8099/stream/tok123",
                    title="Inception",
                    poster_url="http://poster.jpg",
                )
            )

            assert success
            assert entity == "media_player.living_room_tv"
            assert len(captured_payloads) == 1
            payload = captured_payloads[0]
            assert payload["entity_id"] == "media_player.living_room_tv"
            assert payload["media_content_id"] == "http://192.168.1.10:8099/stream/tok123"
            assert payload["extra"]["title"] == "Inception"

    def test_play_on_device_fallback_tier2_when_extra_crashes(self) -> None:
        """Test fallback to Tier 2 (without extra dict) when target device returns HTTP 400/500."""
        calls: list[dict[str, Any]] = []

        class MockSession:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def post(self, url: str, json: dict[str, Any], **kwargs: Any) -> Any:
                calls.append(json)
                mock_resp = AsyncMock()
                # Fail first call (with extra), succeed on second call (without extra)
                if len(calls) == 1:
                    mock_resp.status = 500
                    mock_resp.text = AsyncMock(return_value="Extra metadata not supported by driver")
                else:
                    mock_resp.status = 200
                    mock_resp.text = AsyncMock(return_value="OK")

                mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
                mock_resp.__aexit__ = AsyncMock(return_value=None)
                return mock_resp

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: object) -> None:
                pass

        with patch("aiohttp.ClientSession", MockSession):
            success, entity = asyncio.run(
                self.client.play_on_device(
                    entity_id="media_player.strict_tv",
                    media_url="http://192.168.1.10:8099/stream/tok456",
                    title="Interstellar",
                )
            )

            assert success
            assert entity == "media_player.strict_tv"
            assert len(calls) == 2
            # Second call must not contain "extra"
            assert "extra" not in calls[1]

    def test_play_on_device_fallback_tier3_companion_device(self) -> None:
        """Test fallback to companion cast device when main TV chassis fails."""
        companion = CastDeviceInfo(
            entity_id="media_player.philips_cast",
            name="Philips Smart TV (TPM191E)",
            is_cast=True,
            state="idle",
        )

        with patch.object(self.client, "get_media_players", AsyncMock(return_value=[companion])):
            calls: list[str] = []

            class MockSession:
                def __init__(self, *args: Any, **kwargs: Any) -> None:
                    pass

                def post(self, url: str, json: dict[str, Any], **kwargs: Any) -> Any:
                    target = json.get("entity_id", "")
                    calls.append(target)
                    mock_resp = AsyncMock()
                    # Only succeed when sent to companion cast device
                    if target == "media_player.philips_cast":
                        mock_resp.status = 200
                    else:
                        mock_resp.status = 500

                    mock_resp.text = AsyncMock(return_value="")
                    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
                    mock_resp.__aexit__ = AsyncMock(return_value=None)
                    return mock_resp

                async def __aenter__(self) -> Self:
                    return self

                async def __aexit__(self, *args: object) -> None:
                    pass

            with patch("aiohttp.ClientSession", MockSession):
                success, entity = asyncio.run(
                    self.client.play_on_device(
                        entity_id="media_player.philips_tv",
                        media_url="http://192.168.1.10:8099/stream/tok789",
                        title="Dune 2",
                    )
                )

                assert success
                assert entity == "media_player.philips_cast"
                assert "media_player.philips_cast" in calls

    def test_remote_control_commands(self) -> None:
        """Test seek, play, pause, volume, and mute service routing."""
        executed_services: list[tuple[str, dict[str, Any]]] = []

        async def mock_call(service: str, entity_id: str, extra_data: dict[str, Any] | None = None) -> bool:
            executed_services.append((service, extra_data or {}))
            return True

        with patch.object(self.client, "call_media_player_service", side_effect=mock_call):
            res_seek = asyncio.run(self.client.seek_media("media_player.tv", 120.0))
            assert res_seek
            assert executed_services[-1] == ("media_seek", {"seek_position": 120.0})

            res_ctrl = asyncio.run(self.client.control_cast("media_player.tv", "pause"))
            assert res_ctrl
            assert executed_services[-1][0] == "media_pause"

            res_vol = asyncio.run(self.client.control_cast("media_player.tv", "volume", 0.75))
            assert res_vol
            assert executed_services[-1] == ("volume_set", {"volume_level": 0.75})

    def test_play_on_device_fallback_never_uses_url_mime(self) -> None:
        """Test that media_content_type='url' is never used as a playback fallback."""
        captured_mimes: list[str] = []

        class MockSession:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def post(self, url: str, json: dict[str, Any], **kwargs: Any) -> Any:
                mime = json.get("media_content_type", "")
                captured_mimes.append(mime)
                mock_resp = AsyncMock()
                mock_resp.status = 500
                mock_resp.text = AsyncMock(return_value="Unsupported media type")
                mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
                mock_resp.__aexit__ = AsyncMock(return_value=None)
                return mock_resp

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: object) -> None:
                pass

        with (
            patch("aiohttp.ClientSession", MockSession),
            patch.object(self.client, "get_media_players", AsyncMock(return_value=[])),
        ):
            success, _ = asyncio.run(
                self.client.play_on_device(
                    entity_id="media_player.strict_tv",
                    media_url="http://192.168.1.10:8099/stream/tok_test",
                    title="Test Title",
                )
            )

            assert not success
            # Ensure "url" was never attempted
            assert "url" not in captured_mimes
            # Genuine video formats must have been attempted
            assert any("video" in m or "mpegurl" in m.lower() for m in captured_mimes)

    def test_play_on_device_companion_fallback_for_google_tv_2(self) -> None:
        """Test that media_player.google_tv_2 falls back to companion media_player.google_tv."""
        companion = CastDeviceInfo(
            entity_id="media_player.google_tv",
            name="Master bedroom TV",
            is_cast=True,
            state="off",
        )

        with patch.object(self.client, "get_media_players", AsyncMock(return_value=[companion])):
            calls: list[str] = []

            class MockSession:
                def __init__(self, *args: Any, **kwargs: Any) -> None:
                    pass

                def post(self, url: str, json: dict[str, Any], **kwargs: Any) -> Any:
                    target = json.get("entity_id", "")
                    calls.append(target)
                    mock_resp = AsyncMock()
                    if target == "media_player.google_tv":
                        mock_resp.status = 200
                    else:
                        mock_resp.status = 500

                    mock_resp.text = AsyncMock(return_value="")
                    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
                    mock_resp.__aexit__ = AsyncMock(return_value=None)
                    return mock_resp

                async def __aenter__(self) -> Self:
                    return self

                async def __aexit__(self, *args: object) -> None:
                    pass

            with patch("aiohttp.ClientSession", MockSession):
                success, entity = asyncio.run(
                    self.client.play_on_device(
                        entity_id="media_player.google_tv_2",
                        media_url="http://192.168.1.10:8099/stream/tok_lioness",
                        title="Operazione speciale: Lioness",
                    )
                )

                assert success
                assert entity == "media_player.google_tv"
                assert "media_player.google_tv" in calls
