"""Regression tests for StreamProxy, HLS playlist rewriting, and token management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import sys
import unittest
from unittest.mock import MagicMock

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

if "fastapi" not in sys.modules:
    try:
        import fastapi
    except ImportError:
        mock_fastapi = MagicMock()

        class MockHTTPException(Exception):
            def __init__(self, status_code: int, detail: str = "") -> None:
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        mock_fastapi.HTTPException = MockHTTPException
        sys.modules["fastapi"] = mock_fastapi
        mock_fastapi_resp = MagicMock()
        mock_fastapi_resp.Response = MagicMock()
        mock_fastapi_resp.StreamingResponse = MagicMock()
        sys.modules["fastapi.responses"] = mock_fastapi_resp

from streaming_hub.backend.models import ResolvedMedia
from streaming_hub.backend.proxy import StreamProxy


class TestProxyStreamRegression(unittest.TestCase):
    """Test suite ensuring M3U8 rewriting, header safety, and session lifecycle remain 100% reliable."""

    def setUp(self) -> None:
        """Initialize StreamProxy."""
        self.proxy = StreamProxy(ttl_seconds=3600)

    def test_register_and_retrieve_stream(self) -> None:
        """Test stream registration and token session retrieval."""
        resolved = ResolvedMedia(
            url="https://cdn.example.com/live/master.m3u8",
            mime_type="application/vnd.apple.mpegurl",
            headers={"Referer": "https://source.example.com", "Origin": "https://source.example.com"},
        )

        token = self.proxy.register_stream(resolved)
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 10)

        session = self.proxy.get_stream(token)
        self.assertIsNotNone(session)
        self.assertEqual(session.url, "https://cdn.example.com/live/master.m3u8")
        self.assertEqual(session.headers["Referer"], "https://source.example.com")
        self.assertEqual(session.headers["Origin"], "https://source.example.com")

    def test_session_expiration_cleanup(self) -> None:
        """Test that expired sessions return None and are purged."""
        resolved = ResolvedMedia(url="https://cdn.example.com/stream.m3u8")
        token = self.proxy.register_stream(resolved)

        session = self.proxy.get_stream(token)
        self.assertIsNotNone(session)

        # Force session expiration
        session.expires_at = datetime.now(UTC) - timedelta(seconds=10)
        self.assertIsNone(self.proxy.get_stream(token))

    def test_rewrite_m3u8_master_playlist(self) -> None:
        """Test master playlist URI rewriting to proxy stream endpoints."""
        master_m3u8 = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=1400000,RESOLUTION=1280x720
720p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2800000,RESOLUTION=1920x1080
1080p.m3u8
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Italian",DEFAULT=YES,URI="audio_ita.m3u8"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="Italian",DEFAULT=NO,URI="sub_ita.m3u8"
"""
        token = "test_token_abc"
        base_url = "https://stream.server.org/hls/"
        rewritten = self.proxy.rewrite_m3u8(master_m3u8, base_url, token, root_path="/ingress")

        lines = rewritten.splitlines()

        # Check resolution streams are rewritten to /ingress/stream/test_token_abc?url=...
        self.assertIn("/ingress/stream/test_token_abc?url=https%3A%2F%2Fstream.server.org%2Fhls%2F720p.m3u8", lines)
        self.assertIn("/ingress/stream/test_token_abc?url=https%3A%2F%2Fstream.server.org%2Fhls%2F1080p.m3u8", lines)

        # Check audio and subtitle media tags are also rewritten to stream endpoints
        self.assertTrue(any('URI="/ingress/stream/test_token_abc?url=https%3A%2F%2Fstream.server.org%2Fhls%2Faudio_ita.m3u8"' in line for line in lines))
        self.assertTrue(any('URI="/ingress/stream/test_token_abc?url=https%3A%2F%2Fstream.server.org%2Fhls%2Fsub_ita.m3u8"' in line for line in lines))

    def test_rewrite_m3u8_media_playlist_segments(self) -> None:
        """Test media playlist segments rewriting to proxy segment endpoints."""
        media_m3u8 = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXTINF:10.0,
seg-001.ts
#EXTINF:9.5,
seg-002.ts
#EXT-X-ENDLIST
"""
        token = "test_token_xyz"
        base_url = "https://stream.server.org/hls/1080p/"
        rewritten = self.proxy.rewrite_m3u8(media_m3u8, base_url, token, root_path="")

        lines = rewritten.splitlines()
        self.assertIn("/segment/test_token_xyz?url=https%3A%2F%2Fstream.server.org%2Fhls%2F1080p%2Fseg-001.ts", lines)
        self.assertIn("/segment/test_token_xyz?url=https%3A%2F%2Fstream.server.org%2Fhls%2F1080p%2Fseg-002.ts", lines)


if __name__ == "__main__":
    unittest.main()
