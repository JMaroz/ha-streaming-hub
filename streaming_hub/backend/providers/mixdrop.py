"""Mixdrop streaming provider adapter."""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urljoin, urlparse

import aiohttp

from ..models import ProviderSource, ResolvedMedia
from .base import StreamingProvider

_LOGGER = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class MixdropProvider(StreamingProvider):
    """Provider for Mixdrop video streams."""

    @property
    def provider_id(self) -> str:
        """Provider ID."""
        return "mixdrop"

    @property
    def display_name(self) -> str:
        """Display Name."""
        return "Mixdrop"

    async def can_handle(self, url: str) -> bool:
        """Check if this provider handles the URL."""
        lower = url.lower()
        return "mixdrop" in lower or "stayonline.pro" in lower

    async def resolve(
        self,
        source: ProviderSource,
        session: aiohttp.ClientSession,
        prefer_fhd: bool = True,
    ) -> ResolvedMedia:
        """Resolve Mixdrop source to a playable stream URL."""
        parsed_origin = urlparse(source.page_url)
        referer = f"{parsed_origin.scheme}://{parsed_origin.netloc}/" if parsed_origin.netloc else source.page_url
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": referer,
        }

        target_url = source.page_url
        if "stayonline.pro" in target_url:
            async with session.get(target_url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                target_url = str(resp.url)
                html_text = await resp.text()
                redirect_match = re.search(r'window\.location\s*=\s*["\'](https?://[^"\']+)["\']', html_text)
                if redirect_match:
                    target_url = redirect_match.group(1)
        else:
            async with session.get(target_url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    raise ValueError(f"Mixdrop returned status {resp.status}")
                html_text = await resp.text()

        stream_url = self._extract_stream_url(html_text, target_url)
        if not stream_url:
            raise ValueError("Could not extract playable media from Mixdrop")

        mime_type = "application/x-mpegURL" if ".m3u8" in stream_url else "video/mp4"
        stream_format = "hls" if ".m3u8" in stream_url else "mp4"

        return ResolvedMedia(
            url=stream_url,
            mime_type=mime_type,
            stream_format=stream_format,
            provider_id=self.provider_id,
            headers={"User-Agent": USER_AGENT, "Referer": target_url},
        )

    def _extract_stream_url(self, html_text: str, base_url: str) -> str | None:
        """Extract media URL from page HTML or embedded script."""
        patterns = [
            r'wurl\s*=\s*["\'](https?://[^"\']+)["\']',
            r'MDCore\.wurl\s*=\s*["\'](https?://[^"\']+)["\']',
            r'<source[^>]*src=["\'](https?://[^"\']+\.(?:m3u8|mp4)[^"\']*)["\']',
            r'["\'](https?://[^"\']+\.(?:m3u8|mp4)[^"\']*)["\']',
        ]
        for pat in patterns:
            match = re.search(pat, html_text, re.IGNORECASE)
            if match:
                url = match.group(1)
                if url.startswith("//"):
                    url = "https:" + url
                return urljoin(base_url, url)

        return None
