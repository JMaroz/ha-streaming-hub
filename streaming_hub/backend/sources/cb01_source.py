"""CB01 catalog and stream source adapter."""

from __future__ import annotations

import logging
from typing import Any

from ..cb01_client import CB01Client
from ..models import Movie, ProviderSource, ResolvedMedia, TvEpisode, TvSeason, TvSeries
from ..providers.maxstream import MaxstreamProvider
from ..providers.mixdrop import MixdropProvider
from .base import BaseSource

_LOGGER = logging.getLogger(__name__)


class CB01Source(BaseSource):
    """Source adapter for CB01."""

    def __init__(
        self,
        base_url: str,
        custom_dns: str = "cloudflare",
        enabled: bool = True,
        name: str | None = None,
    ) -> None:
        """Initialize CB01 source with user-specified base URL."""
        self._enabled = enabled
        self._base_url = base_url
        self._name = name or "CB01"
        self._client = (
            CB01Client(base_url=base_url, custom_dns=custom_dns)
            if enabled and base_url
            else None
        )
        self._maxstream = MaxstreamProvider()
        self._mixdrop = MixdropProvider()

    @property
    def source_id(self) -> str:
        """Source identifier."""
        return "cb01"

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        return self._name

    @property
    def icon(self) -> str:
        """Icon identifier."""
        return "mdi:filmstrip"

    @property
    def is_enabled(self) -> bool:
        """Check if source is enabled."""
        return self._enabled and self._client is not None

    async def get_latest_movies(self, page: int = 1) -> list[Movie]:
        """Fetch latest movies."""
        if not self.is_enabled:
            return []
        movies = await self._client.get_latest_movies(page=page)
        for m in movies:
            if self.source_id not in m.catalogs:
                m.catalogs.append(self.source_id)
        return movies

    async def get_latest_tv(self, page: int = 1) -> list[TvSeries]:
        """Fetch latest TV series."""
        if not self.is_enabled:
            return []
        series = await self._client.get_latest_tv(page=page)
        for s in series:
            if self.source_id not in s.catalogs:
                s.catalogs.append(self.source_id)
        return series

    async def search(self, query: str, media_type: str = "all") -> list[Movie | TvSeries]:
        """Search titles by keyword."""
        if not self.is_enabled:
            return []
        items = await self._client.search(query)
        filtered: list[Movie | TvSeries] = []
        for item in items:
            if self.source_id not in item.catalogs:
                item.catalogs.append(self.source_id)
            if media_type == "movie" and isinstance(item, Movie):
                filtered.append(item)
            elif media_type == "tv" and isinstance(item, TvSeries):
                filtered.append(item)
            elif media_type == "all":
                filtered.append(item)
        return filtered

    async def get_details(self, media_type: str, item_id: str) -> Movie | TvSeries:
        """Fetch complete title details."""
        if not self.is_enabled:
            raise ValueError("CB01 source is disabled")

        if media_type in ("tv", "series"):
            series = await self._client.get_tv_series(item_id)
            if self.source_id not in series.catalogs:
                series.catalogs.append(self.source_id)
            return series
        else:
            movie = await self._client.get_movie(item_id)
            if self.source_id not in movie.catalogs:
                movie.catalogs.append(self.source_id)
            return movie

    async def get_season(self, series_id: str, season_number: int) -> TvSeason:
        """Fetch season episodes."""
        if not self.is_enabled:
            raise ValueError("CB01 source is disabled")

        series = await self._client.get_tv_series(series_id)
        for s in series.seasons:
            if s.number == season_number:
                return s
        return TvSeason(number=season_number, episodes=[])

    async def resolve_stream(
        self,
        source: ProviderSource,
        prefer_fhd: bool = True,
    ) -> ResolvedMedia:
        """Resolve stream using provider sub-adapters (Maxstream, Mixdrop)."""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url_lower = source.page_url.lower()
            if await self._maxstream.can_handle(url_lower):
                return await self._maxstream.resolve(source, session, prefer_fhd=prefer_fhd)
            elif await self._mixdrop.can_handle(url_lower):
                return await self._mixdrop.resolve(source, session, prefer_fhd=prefer_fhd)
            raise ValueError(f"No suitable provider adapter found for {source.provider_name} ({source.page_url})")

    async def get_genres(self) -> list[str]:
        """Return available genres."""
        if not self.is_enabled:
            return []
        return await self._client.get_genres()

    async def get_by_genre(self, genre: str, media_type: str = "movie", page: int = 1) -> list[Movie | TvSeries]:
        """Fetch titles by genre."""
        if not self.is_enabled or media_type == "tv":
            return []
        items = await self._client.get_movies_by_genre(genre, page=page)
        for m in items:
            if self.source_id not in m.catalogs:
                m.catalogs.append(self.source_id)
        return items

    async def close(self) -> None:
        """Close client."""
        if self._client:
            await self._client.close()
