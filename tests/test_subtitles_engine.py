"""Unit tests for SubtitleManager and SRT-to-VTT conversion."""

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

from streaming_hub.backend.subtitles import SubtitleManager, srt_to_vtt


class TestSubtitlesEngine:
    """Test suite ensuring subtitle parsing, conversion, and fail-open resilience."""

    def test_srt_to_vtt_conversion(self) -> None:
        """Test conversion of standard SubRip (.srt) to WebVTT (.vtt)."""
        srt_content = """1
00:01:20,000 --> 00:01:23,500
Ciao, questo è un test.

2
00:01:24,100 --> 00:01:27,800
Seconda linea di sottotitoli.
"""
        vtt = srt_to_vtt(srt_content)
        assert vtt.startswith("WEBVTT")
        assert "00:01:20.000 --> 00:01:23.500" in vtt
        assert "00:01:24.100 --> 00:01:27.800" in vtt
        assert "00:01:20,000" not in vtt

    def test_already_vtt_unmodified(self) -> None:
        """Test that text already starting with WEBVTT is preserved."""
        original_vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello world\n"
        result = srt_to_vtt(original_vtt)
        assert result.strip() == original_vtt.strip()

    def test_subtitle_manager_register_and_get(self) -> None:
        """Test registering VTT text and retrieving it via subtitle ID."""
        manager = SubtitleManager()
        raw_srt = "1\n00:00:10,000 --> 00:00:15,000\nTest di sottotitolo\n"
        track = manager.register_vtt(raw_srt, language="it", label="Italiano", is_default=True)

        assert track.language == "it"
        assert track.label == "Italiano"
        assert track.is_default
        assert track.url.startswith("/api/subtitles/")

        retrieved = manager.get_vtt(track.id)
        assert retrieved is not None
        assert retrieved.startswith("WEBVTT")
        assert "00:00:10.000 --> 00:00:15.000" in retrieved

    def test_search_subtitles_fail_open_on_error(self) -> None:
        """Test that search_subtitles handles connection failure without raising exceptions."""
        manager = SubtitleManager()
        # Non-mocked aiohttp in sandbox will fail connection or return empty gracefully
        tracks = asyncio.run(manager.search_subtitles(imdb_id="tt1375666", query="Inception"))
        assert isinstance(tracks, list)


