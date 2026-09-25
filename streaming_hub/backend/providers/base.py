"""Abstract base class for streaming media providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging

import aiohttp

from ..models import ProviderSource, ResolvedMedia

_LOGGER = logging.getLogger(__name__)


class StreamingProvider(ABC):
    """Abstract interface for a media streaming provider."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider (e.g. 'streamingcommunity')."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable display name (e.g. 'StreamingCommunity')."""

    @abstractmethod
    async def can_handle(self, url: str) -> bool:
        """Return True if this provider can resolve the given URL."""

    @abstractmethod
    async def resolve(
        self,
        source: ProviderSource,
        session: aiohttp.ClientSession,
        prefer_fhd: bool = True,
    ) -> ResolvedMedia:
        """Resolve a source into a playable direct media stream."""
