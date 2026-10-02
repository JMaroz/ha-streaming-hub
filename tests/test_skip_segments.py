"""Unit tests for SkipSegmentManager and SkipDB integration."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock

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

from streaming_hub.backend.skip_segments import SkipSegmentManager


class TestSkipSegments:
    """Test suite ensuring SkipDB intro and outro parsing, caching and failover."""

    def setup_method(self, method=None) -> None:
        self.manager = SkipSegmentManager()

    def test_empty_imdb_returns_no_segments(self) -> None:
        """Test that missing or invalid IMDb returns empty segments immediately."""
        res = asyncio.run(self.manager.get_skip_segments(None, 1, 1))
        assert not res["has_segments"]
        assert res["intro"] is None
        assert res["outro"] is None

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
        assert parsed["has_segments"]
        assert parsed["source"] == "skipdb"
        assert parsed["intro"] is not None
        assert parsed["intro"]["start"] == 120.5
        assert parsed["intro"]["end"] == 145.2
        assert parsed["outro"] is not None
        assert parsed["outro"]["start"] == 3200.0
        assert parsed["outro"]["end"] == 3350.0

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
        assert parsed["has_segments"]
        assert parsed["intro"] is None
        assert parsed["outro"] is not None
        assert parsed["outro"]["start"] == 2850.0

    def test_caching_skip_segments(self) -> None:
        """Test that repeated lookups use internal cache."""
        self.manager._cache["tt0903747_1_1_0"] = {
            "has_segments": True,
            "intro": {"start": 50.0, "end": 75.0},
            "outro": {"start": 2500.0, "end": 2600.0},
            "source": "skipdb",
        }
        res = asyncio.run(self.manager.get_skip_segments("tt0903747", 1, 1))
        assert res["has_segments"]
        assert res["intro"]["start"] == 50.0
