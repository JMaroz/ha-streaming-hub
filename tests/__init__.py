"""Unit test package for Streaming Hub with fallback stubs for local test execution."""

from __future__ import annotations

import sys
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
