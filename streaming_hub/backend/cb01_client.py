"""Async HTTP client for CB01 catalog and metadata."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote_plus, urljoin

import aiohttp

from .dns_resolver import DNS_DEFAULT, DoHResolver
from .models import Movie, TvSeries
from .parser import CB01Parser

_LOGGER = logging.getLogger(__name__)

GENRES_LIST = [
    "Animazione",
    "Avventura",
    "Azione",
    "Biografico",
    "Comico",
    "Commedia",
    "Documentario",
    "Drammatico",
    "Fantascienza",
    "Fantasy",
    "Giallo",
    "Guerra",
    "Horror",
    "Musicale",
    "Poliziesco",
    "Sentimentale",
    "Storico",
    "Thriller",
    "Western",
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class CB01Client:
    """Asynchronous client for interacting with CB01."""

    def __init__(
        self,
        base_url: str,
        custom_dns: str = DNS_DEFAULT,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the CB01 client with user-specified base URL."""
        self.base_url = (base_url or "").rstrip("/") + "/"
        self.custom_dns = custom_dns
        self._session = session
        self._own_session = False
        self._resolver: DoHResolver | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or initialize the aiohttp ClientSession."""
        if self._session and not self._session.closed:
            return self._session

        self._resolver = DoHResolver(mode=self.custom_dns)
        connector = aiohttp.TCPConnector(resolver=self._resolver, ssl=False)
        self._session = aiohttp.ClientSession(
            connector=connector,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        self._own_session = True
        return self._session

    async def _request(self, url: str) -> str:
        """Fetch HTML content from a URL with timeout, error handling, and mirror fallback."""
        session = await self._get_session()
        try:
            async with asyncio.timeout(6):
                async with session.get(url, allow_redirects=True) as resp:
                    if resp.status == 200:
                        if str(resp.url).rstrip("/") == self.base_url.rstrip("/") and url.rstrip(
                            "/"
                        ) != self.base_url.rstrip("/"):
                            raise ValueError(f"URL {url} redirected to homepage")
                        return await resp.text()
                    _LOGGER.debug("CB01 returned status %s for %s", resp.status, url)
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            _LOGGER.debug("CB01 request failed for %s: %s", url, err)

        if url.startswith(self.base_url):
            path_part = url[len(self.base_url) :]
            candidate_mirrors = [m for m in CB01_MIRRORS_LIST if m.rstrip("/") != self.base_url.rstrip("/")]
            for mirror in candidate_mirrors:
                mirror_url = urljoin(mirror, path_part)
                try:
                    _LOGGER.debug("Trying alternate CB01 mirror: %s", mirror_url)
                    async with asyncio.timeout(4):
                        async with session.get(mirror_url, allow_redirects=True) as resp:
                            if resp.status == 200:
                                text = await resp.text()
                                _LOGGER.info("Switched active CB01 mirror from %s to %s", self.base_url, mirror)
                                self.base_url = mirror.rstrip("/") + "/"
                                return text
                except (TimeoutError, aiohttp.ClientError):
                    continue

        raise ValueError(f"Could not connect to CB01 or any mirror for {url}")

    async def get_latest_movies(self, page: int = 1) -> list[Movie]:
        """Fetch the most recent movies."""
        movies = await self.get_catalog_page(page)
        return [m for m in movies if not CB01Parser.is_tv_item(m.title, m.cb01_url, m.genres)]

    async def get_catalog_page(self, page: int = 1) -> list[Movie]:
        """Fetch a specific page from the catalog."""
        url = self.base_url if page <= 1 else urljoin(self.base_url, f"page/{page}/")
        html_text = await self._request(url)
        movies = CB01Parser.parse_catalog_page(html_text)
        return [m for m in movies if not CB01Parser.is_tv_item(m.title, m.cb01_url, m.genres)]

    async def search(self, query: str) -> list[Movie | TvSeries]:
        """Search movies and TV series."""
        encoded_query = quote_plus(query.strip())
        url = urljoin(self.base_url, f"?s={encoded_query}")
        html_text = await self._request(url)
        parsed = CB01Parser.parse_catalog_page(html_text)
        results: list[Movie | TvSeries] = []
        for item in parsed:
            if CB01Parser.is_tv_item(item.title, item.cb01_url, item.genres):
                results.append(
                    TvSeries(
                        id=item.id,
                        title=item.title,
                        year=item.year,
                        poster_url=item.poster_url,
                        description=item.description,
                        genres=item.genres,
                        cb01_url=item.cb01_url,
                        catalogs=["cb01"],
                        seasons=[],
                    )
                )
            else:
                results.append(item)
        return results

    async def get_movie(self, media_id_or_url: str) -> Movie:
        """Fetch complete movie details and sources."""
        if media_id_or_url.startswith(("http://", "https://")):
            url = media_id_or_url
        else:
            url = urljoin(self.base_url, f"{media_id_or_url}/")

        html_text = await self._request(url)
        return CB01Parser.parse_movie_page(html_text, movie_url=url)

    async def get_latest_tv(self, page: int = 1) -> list[TvSeries]:
        """Fetch the most recent TV series."""
        path = "category/serie-tv/"
        if page > 1:
            path += f"page/{page}/"
        url = urljoin(self.base_url, path)

        html_text = await self._request(url)
        movies = CB01Parser.parse_catalog_page(html_text)
        return [
            TvSeries(
                id=m.id,
                title=m.title,
                year=m.year,
                poster_url=m.poster_url,
                description=m.description,
                genres=m.genres,
                cb01_url=m.cb01_url,
                catalogs=["cb01"],
                seasons=[],
            )
            for m in movies
        ]

    get_latest_tv_series = get_latest_tv

    async def get_tv_series(self, media_id_or_url: str) -> TvSeries:
        """Fetch complete TV series details and episodes."""
        if media_id_or_url.startswith(("http://", "https://")):
            url = media_id_or_url
        else:
            url = urljoin(self.base_url, f"{media_id_or_url}/")

        html_text = await self._request(url)
        return CB01Parser.parse_tv_series_page(html_text, series_url=url)

    async def get_genres(self) -> list[str]:
        """Return the list of available genres."""
        return list(GENRES_LIST)

    async def close(self) -> None:
        """Close client and underlying connections."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()
        if self._resolver:
            await self._resolver.close()
