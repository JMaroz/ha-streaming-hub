"""Regression and reliability tests for Home Assistant Cast and media player playback."""

from __future__ import annotations

import asyncio
import sys
from typing import Any
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

if "aiohttp" not in sys.modules:
    try:
        import aiohttp
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


class TestCastPlaybackRegression(unittest.TestCase):
    """Test suite ensuring 100% zero-regression reliability for Cast and media_player commands."""

    def setUp(self) -> None:
        """Initialize HACoreClient with a test token."""
        self.client = HACoreClient(token="mock_supervisor_token", base_url="http://mock-supervisor/core/api")

    def test_availability_and_headers(self) -> None:
        """Test token presence and authentication headers."""
        self.assertTrue(self.client.is_available)
        headers = self.client._get_headers()
        self.assertEqual(headers["Authorization"], "Bearer mock_supervisor_token")
        self.assertEqual(headers["Content-Type"], "application/json")

        unauthed = HACoreClient(token="")
        self.assertFalse(unauthed.is_available)

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
        ]

        class MockResponse:
            def __init__(self, json_data: Any, status: int = 200) -> None:
                self._json = json_data
                self.status = status

            async def json(self) -> Any:
                return self._json

            async def __aenter__(self) -> MockResponse:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        class MockClientSession:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def get(self, url: str, **kwargs: Any) -> MockResponse:
                return MockResponse(mock_states)

            async def __aenter__(self) -> MockClientSession:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        with patch("aiohttp.ClientSession", MockClientSession):
            players = asyncio.run(self.client.get_media_players())
            entity_ids = [p.entity_id for p in players]

            # Allowed stream targets
            self.assertIn("media_player.living_room_tv", entity_ids)
            self.assertIn("media_player.tpm191e_chassis", entity_ids)

            # Blocked / Filtered out
            self.assertNotIn("media_player.kitchen_nest_mini", entity_ids)  # Nest speaker
            self.assertNotIn("media_player.browser", entity_ids)  # Browser target
            self.assertNotIn("media_player.bedroom_tv_remote", entity_ids)  # No play_media feature

    def test_play_on_device_tier1_success(self) -> None:
        """Test play_on_device succeeds on Tier 1 (with extra metadata)."""
        captured_payloads: list[dict[str, Any]] = []

        class MockResponse:
            status = 200

            async def text(self) -> str:
                return "OK"

            async def __aenter__(self) -> MockResponse:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        class MockSession:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def post(self, url: str, json: dict[str, Any], **kwargs: Any) -> MockResponse:
                captured_payloads.append(json)
                return MockResponse()

            async def __aenter__(self) -> MockSession:
                return self

            async def __aexit__(self, *args: Any) -> None:
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

            self.assertTrue(success)
            self.assertEqual(entity, "media_player.living_room_tv")
            self.assertEqual(len(captured_payloads), 1)
            payload = captured_payloads[0]
            self.assertEqual(payload["entity_id"], "media_player.living_room_tv")
            self.assertEqual(payload["media_content_id"], "http://192.168.1.10:8099/stream/tok123")
            self.assertEqual(payload["extra"]["title"], "Inception")

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

            async def __aenter__(self) -> MockSession:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        with patch("aiohttp.ClientSession", MockSession):
            success, entity = asyncio.run(
                self.client.play_on_device(
                    entity_id="media_player.strict_tv",
                    media_url="http://192.168.1.10:8099/stream/tok456",
                    title="Interstellar",
                )
            )

            self.assertTrue(success)
            self.assertEqual(entity, "media_player.strict_tv")
            self.assertEqual(len(calls), 2)
            # Second call must not contain "extra"
            self.assertNotIn("extra", calls[1])

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

                async def __aenter__(self) -> MockSession:
                    return self

                async def __aexit__(self, *args: Any) -> None:
                    pass

            with patch("aiohttp.ClientSession", MockSession):
                success, entity = asyncio.run(
                    self.client.play_on_device(
                        entity_id="media_player.philips_tv",
                        media_url="http://192.168.1.10:8099/stream/tok789",
                        title="Dune 2",
                    )
                )

                self.assertTrue(success)
                self.assertEqual(entity, "media_player.philips_cast")
                self.assertIn("media_player.philips_cast", calls)

    def test_remote_control_commands(self) -> None:
        """Test seek, play, pause, volume, and mute service routing."""
        executed_services: list[tuple[str, dict[str, Any]]] = []

        async def mock_call(service: str, entity_id: str, extra_data: dict[str, Any] | None = None) -> bool:
            executed_services.append((service, extra_data or {}))
            return True

        with patch.object(self.client, "call_media_player_service", side_effect=mock_call):
            res_seek = asyncio.run(self.client.seek_media("media_player.tv", 120.0))
            self.assertTrue(res_seek)
            self.assertEqual(executed_services[-1], ("media_seek", {"seek_position": 120.0}))

            res_ctrl = asyncio.run(self.client.control_cast("media_player.tv", "pause"))
            self.assertTrue(res_ctrl)
            self.assertEqual(executed_services[-1][0], "media_pause")

            res_vol = asyncio.run(self.client.control_cast("media_player.tv", "volume", 0.75))
            self.assertTrue(res_vol)
            self.assertEqual(executed_services[-1], ("volume_set", {"volume_level": 0.75}))


if __name__ == "__main__":
    unittest.main()
