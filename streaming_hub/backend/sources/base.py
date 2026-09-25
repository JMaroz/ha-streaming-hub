"""Abstract base class for all Streaming Hub catalog and streaming sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any

from ..models import Movie, ProviderSource, ResolvedMedia, TvEpisode, TvSeason, TvSeries

_LOGGER = logging.getLogger(__name__)


class BaseSource(ABC):
    """Abstract base class defining the contract for any catalog source.

    Every supported or future website/provider (StreamingCommunity, CB01, etc.)
    implements this interface, transforming site-specific structures into the
    unified Streaming Hub data models.
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique machine identifier for this source (e.g., 'streamingcommunity', 'cb01')."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable display name (e.g., 'StreamingCommunity', 'CB01')."""

    @property
    def icon(self) -> str:
        """Material design icon identifier or emoji for UI display."""
        return "mdi:movie-open"

    @property
    def supported_types(self) -> list[str]:
        """List of media types supported by this source ('movie', 'tv')."""
        return ["movie", "tv"]

    @property
    @abstractmethod
    def is_enabled(self) -> bool:
        """Return True if this source is enabled in configuration."""

    @abstractmethod
    async def get_latest_movies(self, page: int = 1) -> list[Movie]:
        """Fetch the most recent movies transformed into the common Movie model."""

    @abstractmethod
    async def get_latest_tv(self, page: int = 1) -> list[TvSeries]:
        """Fetch the most recent TV series transformed into the common TvSeries model."""

    @abstractmethod
    async def search(self, query: str, media_type: str = "all") -> list[Movie | TvSeries]:
        """Search titles by keyword transformed into common models."""

    @abstractmethod
    async def get_details(self, media_type: str, item_id: str) -> Movie | TvSeries:
        """Fetch complete details, synopsis, backdrop, and sources for a single title."""

    @abstractmethod
    async def get_season(self, series_id: str, season_number: int) -> TvSeason:
        """Fetch episodes and sources for a specific TV series season."""

    @abstractmethod
    async def resolve_stream(
        self,
        source: ProviderSource,
        prefer_fhd: bool = True,
    ) -> ResolvedMedia:
        """Resolve a ProviderSource into a direct playable HLS stream with necessary headers."""

    async def get_genres(self) -> list[str]:
        """Return the list of available genres for this source."""
        return []

    async def get_by_genre(self, genre: str, media_type: str = "movie", page: int = 1) -> list[Movie | TvSeries]:
        """Fetch titles matching a specific genre."""
        return []

    async def close(self) -> None:
        """Clean up underlying network sessions and resources."""
        pass
