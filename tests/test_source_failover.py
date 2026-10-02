"""Unit tests for multi-source auto-failover and stream resilience."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

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

import pytest

from streaming_hub.backend.models import ProviderSource, ResolvedMedia
from streaming_hub.backend.sources.manager import SourceManager


class TestSourceFailover:
    """Test suite ensuring transparent failover when primary source fails."""

    def setup_method(self, method=None) -> None:
        """Initialize SourceManager with mock sources."""
        self.manager = SourceManager()

    def test_failover_to_secondary_source_on_primary_failure(self) -> None:
        """Test that failure on primary source transparently attempts alternate source."""
        primary_source = ProviderSource(
            id="src_1",
            media_id="media_123",
            provider_id="failing_provider",
            provider_name="Failing Provider",
            page_url="https://fail.example.com/watch",
        )
        backup_source = ProviderSource(
            id="src_2",
            media_id="media_123",
            provider_id="healthy_provider",
            provider_name="Healthy Provider",
            page_url="https://healthy.example.com/watch",
        )

        mock_failing_adapter = MagicMock()
        mock_failing_adapter.source_id = "failing_provider"
        mock_failing_adapter.display_name = "Failing Provider"
        mock_failing_adapter.icon = ""
        mock_failing_adapter.is_enabled = True
        mock_failing_adapter.supported_types = ["movie", "tv"]
        mock_failing_adapter.resolve_stream = AsyncMock(side_effect=Exception("Stream link expired (403)"))

        mock_healthy_adapter = MagicMock()
        mock_healthy_adapter.source_id = "healthy_provider"
        mock_healthy_adapter.display_name = "Healthy Provider"
        mock_healthy_adapter.icon = ""
        mock_healthy_adapter.is_enabled = True
        mock_healthy_adapter.supported_types = ["movie", "tv"]
        resolved_ok = ResolvedMedia(url="https://cdn.healthy.com/master.m3u8", title="Success")
        mock_healthy_adapter.resolve_stream = AsyncMock(return_value=resolved_ok)

        self.manager.register_source(mock_failing_adapter)
        self.manager.register_source(mock_healthy_adapter)

        result = asyncio.run(
            self.manager.resolve_stream_with_fallback(
                primary_source,
                alternate_sources=[backup_source],
            )
        )

        assert result is not None
        assert result.url == "https://cdn.healthy.com/master.m3u8"
        mock_failing_adapter.resolve_stream.assert_called_once()
        mock_healthy_adapter.resolve_stream.assert_called_once()

    def test_all_sources_fail_raises_value_error(self) -> None:
        """Test that if all sources fail, a descriptive ValueError is raised."""
        bad_source = ProviderSource(
            id="src_bad",
            media_id="m",
            provider_id="bad",
            provider_name="Bad",
            page_url="https://bad.com",
        )
        mock_bad = MagicMock()
        mock_bad.source_id = "bad"
        mock_bad.display_name = "Bad"
        mock_bad.icon = ""
        mock_bad.is_enabled = True
        mock_bad.supported_types = ["movie"]
        mock_bad.resolve_stream = AsyncMock(side_effect=Exception("Dead stream"))

        self.manager.register_source(mock_bad)

        with pytest.raises(ValueError):
            asyncio.run(self.manager.resolve_stream_with_fallback(bad_source))
