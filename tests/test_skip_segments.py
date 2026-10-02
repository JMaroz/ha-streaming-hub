"""Unit tests for SkipSegmentManager and SkipDB integration."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import unittest

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

from streaming_hub.backend.skip_segments import SkipSegmentManager


class TestSkipSegments(unittest.TestCase):
    """Test suite ensuring SkipDB intro and outro parsing, caching and failover."""

    def setUp(self) -> None:
        self.manager = SkipSegmentManager()

    def test_empty_imdb_returns_no_segments(self) -> None:
        """Test that missing or invalid IMDb returns empty segments immediately."""
        res = asyncio.run(self.manager.get_skip_segments(None, 1, 1))
        self.assertFalse(res["has_segments"])
        self.assertIsNone(res["intro"])
        self.assertIsNone(res["outro"])

    def test_parse_skipdb_response(self) -> None:
        """Test parsing valid SkipDB response with both intro and outro."""
        raw_data = {
            "imdb_id": "tt0903747",
            "season": 1,
            "episode": 1,
            "segments": {
                "intro": {"start_ms": 120500, "end_ms": 145200},
                "outro": {"start_ms": 3200000, "end_ms": 3350000},
            },
        }
        parsed = self.manager._parse_skipdb_response(raw_data)
        self.assertTrue(parsed["has_segments"])
        self.assertEqual(parsed["source"], "skipdb")
        self.assertIsNotNone(parsed["intro"])
        self.assertEqual(parsed["intro"]["start"], 120.5)
        self.assertEqual(parsed["intro"]["end"], 145.2)
        self.assertIsNotNone(parsed["outro"])
        self.assertEqual(parsed["outro"]["start"], 3200.0)
        self.assertEqual(parsed["outro"]["end"], 3350.0)

    def test_parse_skipdb_partial_outro_only(self) -> None:
        """Test parsing response where only outro is present."""
        raw_data = {
            "imdb_id": "tt12345",
            "season": 2,
            "episode": 3,
            "segments": {
                "intro": None,
                "outro": {"start_ms": 2850000, "end_ms": None},
            },
        }
        parsed = self.manager._parse_skipdb_response(raw_data)
        self.assertTrue(parsed["has_segments"])
        self.assertIsNone(parsed["intro"])
        self.assertIsNotNone(parsed["outro"])
        self.assertEqual(parsed["outro"]["start"], 2850.0)

    def test_caching_skip_segments(self) -> None:
        """Test that repeated lookups use internal cache."""
        self.manager._cache["tt0903747_1_1_0"] = {
            "has_segments": True,
            "intro": {"start": 50.0, "end": 75.0},
            "outro": {"start": 2500.0, "end": 2600.0},
            "source": "skipdb",
        }
        res = asyncio.run(self.manager.get_skip_segments("tt0903747", 1, 1))
        self.assertTrue(res["has_segments"])
        self.assertEqual(res["intro"]["start"], 50.0)


if __name__ == "__main__":
    unittest.main()
