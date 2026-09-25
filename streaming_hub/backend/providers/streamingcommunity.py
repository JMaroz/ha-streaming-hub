"""StreamingCommunity media streaming provider adapter."""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from ..models import ProviderSource, ResolvedMedia
from .base import StreamingProvider

_LOGGER = logging.getLogger(__name__)


class StreamingCommunityProvider(StreamingProvider):
    """Provider for StreamingCommunity video streams (HLS m3u8)."""

    def __init__(self, client=None) -> None:
        """Initialize provider with optional client reference."""
        self._client = client

    @property
    def provider_id(self) -> str:
        """Provider identifier."""
        return "streamingcommunity"

    @property
    def display_name(self) -> str:
        """Human-readable provider name."""
        return "StreamingCommunity"

    async def can_handle(self, url: str) -> bool:
        """Return True if this provider can resolve the given URL."""
        lower = url.lower()
        return "streamingcommunity" in lower or "vixcloud" in lower or "vixsrc" in lower

    async def resolve(
        self,
        source: ProviderSource,
        session: aiohttp.ClientSession,
        prefer_fhd: bool = True,
    ) -> ResolvedMedia:
        """Resolve StreamingCommunity watch URL to playable HLS stream."""
        if not self._client:
            from ..streamingcommunity import StreamingCommunityClient
            self._client = StreamingCommunityClient(session=session)

        m3u8_url, headers = await self._client.resolve_stream(source.page_url, prefer_fhd=prefer_fhd)
        if not m3u8_url:
            raise ValueError("Empty playlist URL returned for StreamingCommunity")

        return ResolvedMedia(
            url=m3u8_url,
            mime_type="application/vnd.apple.mpegurl",
            stream_format="hls",
            provider_id=self.provider_id,
            headers=headers,
        )
