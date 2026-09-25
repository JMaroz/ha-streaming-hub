"""HTML and metadata parser for CB01 catalog and movie pages."""

from __future__ import annotations

import contextlib
from datetime import datetime
import hashlib
import html
import json
import re
from typing import Any
from urllib.parse import urlparse

from .models import Movie, ProviderSource, TvEpisode, TvSeason, TvSeries


class CB01Parser:
    """Parser for CB01 HTML documents."""

    @staticmethod
    def extract_media_id_from_url(url: str) -> str:
        """Extract movie slug ID from a CB01 URL."""
        path = urlparse(url).path.strip("/")
        parts = path.split("/")
        return parts[-1] if parts else hashlib.md5(url.encode()).hexdigest()[:12]

    @staticmethod
    def clean_title(raw_title: str) -> tuple[str, int | None, str | None]:
        """Clean raw title string, extracting clean title, year, and quality flag."""
        cleaned = html.unescape(raw_title)
        # Remove site suffixes
        cleaned = re.sub(r"\s*-\s*FILM GRATIS.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*Streaming.*$", "", cleaned, flags=re.IGNORECASE)

        # Extract year
        year: int | None = None
        year_match = re.search(r"\((\d{4})\)", cleaned)
        if year_match:
            with contextlib.suppress(ValueError):
                year = int(year_match.group(1))
            cleaned = re.sub(r"\(\d{4}\)", "", cleaned)

        # Extract quality
        quality: str | None = None
        if re.search(r"\[HD\]", cleaned, flags=re.IGNORECASE):
            quality = "HD"
            cleaned = re.sub(r"\[HD\]", "", cleaned, flags=re.IGNORECASE)
        elif re.search(r"\[Sub-ITA\]", cleaned, flags=re.IGNORECASE):
            quality = "Sub-ITA"
            cleaned = re.sub(r"\[Sub-ITA\]", "", cleaned, flags=re.IGNORECASE)

        # Clean punctuation and extra spaces
        cleaned = re.sub(r"[–—−-]\s*$", "", cleaned).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned, year, quality

    @staticmethod
    def parse_metadata_line(raw_meta: str) -> tuple[list[str], int | None, str | None]:
        """Parse genre, duration, and country from metadata header line."""
        unescaped = html.unescape(raw_meta).replace("</span>", "").strip()
        parts = [p.strip() for p in re.split(r"[–—−-]", unescaped) if p.strip()]

        genres: list[str] = []
        duration: int | None = None
        country: str | None = None

        for part in parts:
            dur_match = re.search(r"DURATA\s+(\d+)", part, flags=re.IGNORECASE)
            if dur_match:
                with contextlib.suppress(ValueError):
                    duration = int(dur_match.group(1))
                continue

            if part.upper() in (
                "ITALIA",
                "USA",
                "FRANCIA",
                "REGNO UNITO",
                "SPAGNA",
                "GERMANIA",
                "CANADA",
                "GIAPPONE",
                "CINA",
            ):
                country = part.title()
            else:
                genres.append(part.title())

        return genres, duration, country

    @classmethod
    def is_tv_item(cls, title: str, url: str = "", genres: list[str] | None = None) -> bool:
        """Check if an item is a TV series rather than a movie."""
        if url and re.search(r"/(?:serie-?tv|serietv)/", url, re.IGNORECASE):
            return True
        if genres and any(g.lower() in ("serie tv", "serietv") for g in genres):
            return True
        return bool(re.search(r"\b(?:\d+x\d+|s\d+e\d+|stagion[ei]|episodi[oe]?)\b", title, re.IGNORECASE))

    @classmethod
    def parse_catalog_page(cls, html_text: str) -> list[Movie]:
        """Parse movie cards from a catalog, category, or search results page."""
        movies: list[Movie] = []

        card_pattern = re.compile(
            r'<div class="card mp-post horizontal">(.*?)</div>\s*</div>\s*</div>',
            re.DOTALL,
        )
        card_matches = card_pattern.findall(html_text)

        if not card_matches:
            card_matches = re.findall(
                r'<div class="[^"]*mp-post[^"]*">(.*?)</div>\s*</div>',
                html_text,
                re.DOTALL,
            )

        for card_html in card_matches:
            title_match = re.search(
                r'<h3 class="card-title"><a href="([^"]+)">\s*(.*?)\s*</a></h3>',
                card_html,
                re.DOTALL,
            )
            if not title_match:
                continue

            movie_url = title_match.group(1).strip()
            raw_title = title_match.group(2).strip()

            if "cambia-i-dns" in movie_url or "avviso" in movie_url.lower():
                continue

            media_id = cls.extract_media_id_from_url(movie_url)
            clean_title, year, _ = cls.clean_title(raw_title)

            img_match = re.search(
                r'<div class="card-image">.*?<img [^>]*src="([^"]+)"',
                card_html,
                re.DOTALL,
            )
            poster_url = img_match.group(1).strip() if img_match else None

            meta_match = re.search(r"<strong[^>]*>\s*(.*?)\s*</strong>", card_html)
            genres: list[str] = []
            duration: int | None = None
            if meta_match:
                genres, duration, _ = cls.parse_metadata_line(meta_match.group(1))

            desc_match = re.search(
                r"<strong[^>]*>.*?</strong>(?:</span>)?\s*<br />\s*(.*?)(?:<a |</div>)",
                card_html,
                re.DOTALL,
            )
            description = None
            if desc_match:
                clean_desc = re.sub(r"<[^>]+>", "", desc_match.group(1)).strip()
                description = html.unescape(clean_desc)

            movies.append(
                Movie(
                    id=media_id,
                    title=clean_title,
                    year=year,
                    poster_url=poster_url,
                    description=description,
                    genres=genres,
                    duration=duration,
                    cb01_url=movie_url,
                    catalogs=["cb01"],
                    sources=[],
                )
            )

        return movies

    @classmethod
    def parse_movie_page(cls, html_text: str, movie_url: str = "") -> Movie:
        """Parse complete details and sources from a movie page."""
        media_id = cls.extract_media_id_from_url(movie_url) if movie_url else ""

        json_ld_data: dict[str, Any] = {}
        json_ld_match = re.search(
            r'<script type="application/ld\+json" class="yoast-schema-graph">(.*?)</script>',
            html_text,
            re.DOTALL,
        )
        if json_ld_match:
            with contextlib.suppress(Exception):
                json_ld_data = json.loads(json_ld_match.group(1))

        raw_title = ""
        poster_url: str | None = None
        added_at: datetime | None = None
        updated_at: datetime | None = None
        genres: list[str] = []

        if json_ld_data and "@graph" in json_ld_data:
            for item in json_ld_data["@graph"]:
                if item.get("@type") in ("Article", "WebPage"):
                    raw_title = item.get("headline") or item.get("name") or raw_title
                    if item.get("datePublished"):
                        with contextlib.suppress(Exception):
                            added_at = datetime.fromisoformat(item["datePublished"])
                    if item.get("dateModified"):
                        with contextlib.suppress(Exception):
                            updated_at = datetime.fromisoformat(item["dateModified"])
                    if item.get("thumbnailUrl"):
                        poster_url = item["thumbnailUrl"]
                    if item.get("articleSection") and isinstance(item["articleSection"], list):
                        for sec in item["articleSection"]:
                            if not re.match(r"^\(?\d{4}\)?$", sec) and sec not in (
                                "Film",
                                "HD",
                                "Vetrina-news",
                            ):
                                clean_sec = re.sub(r"[\(\)]", "", sec).strip()
                                if clean_sec and clean_sec not in genres:
                                    genres.append(clean_sec)

        if not raw_title:
            title_tag = re.search(r"<title>(.*?)</title>", html_text)
            if title_tag:
                raw_title = title_tag.group(1)

        clean_title, year, _ = cls.clean_title(raw_title)

        if not poster_url:
            og_img = re.search(r'<meta property="og:image" content="([^"]+)"', html_text)
            if og_img:
                poster_url = og_img.group(1)

        duration: int | None = None
        meta_match = re.search(
            r'<div class="ignore-css">.*?<strong[^>]*>(.*?)</strong>',
            html_text,
            re.DOTALL,
        )
        if meta_match:
            body_genres, parsed_dur, _ = cls.parse_metadata_line(meta_match.group(1))
            if parsed_dur:
                duration = parsed_dur
            for g in body_genres:
                if g not in genres:
                    genres.append(g)

        desc_match = re.search(
            r'<div class="ignore-css">.*?<p>(?:<strong[^>]*>.*?</strong></p>\s*<p>)?(.*?)(?:<br\s*/?>\s*<a |</p>)',
            html_text,
            re.DOTALL,
        )
        description: str | None = None
        if desc_match:
            clean_desc = re.sub(r"<[^>]+>", "", desc_match.group(1)).strip()
            description = html.unescape(clean_desc)

        sources = cls.parse_sources(html_text, media_id)

        return Movie(
            id=media_id,
            title=clean_title,
            year=year,
            poster_url=poster_url,
            description=description,
            genres=genres,
            duration=duration,
            cb01_url=movie_url,
            catalogs=["cb01"],
            sources=sources,
            added_at=added_at,
            updated_at=updated_at,
        )

    @classmethod
    def parse_sources(cls, html_text: str, media_id: str) -> list[ProviderSource]:
        """Extract streaming sources from the cbtable."""
        sources: list[ProviderSource] = []

        table_match = re.search(
            r'<table class="cbtable"[^>]*>(.*?)</table>\s*</td>',
            html_text,
            re.DOTALL,
        )
        if not table_match:
            return sources

        table_content = table_match.group(1)
        sections = re.split(r"<u><strong>(Streaming.*?|Download.*?):?</strong></u>", table_content)

        for i in range(1, len(sections), 2):
            sec_name = sections[i].strip()
            sec_body = sections[i + 1]

            if not sec_name.lower().startswith("streaming"):
                continue

            quality = "HD" if "HD" in sec_name else "SD"

            link_matches = re.findall(r'<a href="([^"]+)"[^>]*>\s*([^<]+)\s*</a>', sec_body)
            for page_url, provider_raw in link_matches:
                provider_name = provider_raw.strip()
                provider_id = provider_name.lower().replace(" ", "_")

                url_hash = hashlib.md5(page_url.encode()).hexdigest()[:8]
                source_id = f"{media_id}_{provider_id}_{quality.lower()}_{url_hash}"

                sources.append(
                    ProviderSource(
                        id=source_id,
                        media_id=media_id,
                        provider_id=provider_id,
                        provider_name=provider_name,
                        page_url=page_url.strip(),
                        quality=quality,
                        language="ita",
                        available=True,
                    )
                )

        return sources

    @classmethod
    def parse_tv_series_page(cls, html_text: str, series_url: str = "") -> TvSeries:
        """Parse complete details and episodes from a TV series page."""
        series_id = cls.extract_media_id_from_url(series_url) if series_url else ""

        json_ld_data: dict[str, Any] = {}
        json_ld_match = re.search(
            r'<script type="application/ld\+json" class="yoast-schema-graph">(.*?)</script>',
            html_text,
            re.DOTALL,
        )
        if json_ld_match:
            with contextlib.suppress(Exception):
                json_ld_data = json.loads(json_ld_match.group(1))

        raw_title = ""
        poster_url: str | None = None
        added_at: datetime | None = None
        updated_at: datetime | None = None
        genres: list[str] = []

        if json_ld_data and "@graph" in json_ld_data:
            for item in json_ld_data["@graph"]:
                if item.get("@type") in ("Article", "WebPage"):
                    raw_title = item.get("headline") or item.get("name") or raw_title
                    if item.get("datePublished"):
                        with contextlib.suppress(Exception):
                            added_at = datetime.fromisoformat(item["datePublished"])
                    if item.get("dateModified"):
                        with contextlib.suppress(Exception):
                            updated_at = datetime.fromisoformat(item["dateModified"])
                    if item.get("thumbnailUrl"):
                        poster_url = item["thumbnailUrl"]
                    if item.get("articleSection") and isinstance(item["articleSection"], list):
                        for sec in item["articleSection"]:
                            if not re.match(r"^\(?\d{4}\)?$", sec) and sec not in (
                                "Film",
                                "HD",
                                "Vetrina-news",
                                "Serie TV",
                            ):
                                clean_sec = re.sub(r"[\(\)]", "", sec).strip()
                                if clean_sec and clean_sec not in genres:
                                    genres.append(clean_sec)

        if not raw_title:
            title_tag = re.search(r"<title>(.*?)</title>", html_text)
            if title_tag:
                raw_title = title_tag.group(1)

        clean_title, year, _ = cls.clean_title(raw_title)

        if not poster_url:
            og_img = re.search(r'<meta property="og:image" content="([^"]+)"', html_text)
            if og_img:
                poster_url = og_img.group(1)

        desc_match = re.search(
            r'<div class="ignore-css">.*?<p>(?:<strong[^>]*>.*?</strong></p>\s*<p>)?(.*?)(?:<br\s*/?>\s*<a |</p>)',
            html_text,
            re.DOTALL,
        )
        description: str | None = None
        if desc_match:
            clean_desc = re.sub(r"<[^>]+>", "", desc_match.group(1)).strip()
            description = html.unescape(clean_desc)

        seasons_dict: dict[int, list[TvEpisode]] = {}
        tags = re.findall(r"<p[^>]*>(.*?)</p>|<li[^>]*>(.*?)</li>", html_text, re.IGNORECASE | re.DOTALL)
        for t1, t2 in tags:
            content = t1 or t2
            p_text = html.unescape(re.sub(r"<[^>]+>", "", content))

            match = re.search(r"\b(\d{1,2})\s*[xX×]\s*(\d{1,3})\b", p_text)
            if match:
                season_num = int(match.group(1))
                ep_num = int(match.group(2))

                links = re.findall(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', content, re.IGNORECASE)
                valid_sources: list[ProviderSource] = []
                for url, name_html in links:
                    name = html.unescape(re.sub(r"<[^>]+>", "", name_html)).strip()
                    if name.lower() in (
                        "maxstream",
                        "mixdrop",
                        "mixdrop.",
                        "maxstream.",
                        "streamtape",
                        "doodstream",
                        "wstream",
                    ) or re.search(r"stayonline\.pro|uprot\.net", url):
                        if not name or len(name) > 20:
                            if "mixdrop" in name.lower() or "mixdrop" in url.lower():
                                name = "Mixdrop"
                            elif "maxstream" in name.lower() or "maxstream" in url.lower():
                                name = "Maxstream"
                            else:
                                name = "Unknown"

                        provider_id = name.lower().replace(" ", "_").replace(".", "")
                        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                        source_id = f"{series_id}_s{season_num}e{ep_num}_{provider_id}_hd_{url_hash}"

                        valid_sources.append(
                            ProviderSource(
                                id=source_id,
                                media_id=series_id,
                                provider_id=provider_id,
                                provider_name=name,
                                page_url=url.strip(),
                                quality="HD",
                                language="ita",
                                available=True,
                            )
                        )

                if not valid_sources:
                    continue

                if season_num not in seasons_dict:
                    seasons_dict[season_num] = []

                ep_id = f"{series_id}_s{season_num}e{ep_num}"
                seasons_dict[season_num].append(
                    TvEpisode(
                        id=ep_id,
                        media_id=series_id,
                        season_number=season_num,
                        episode_number=ep_num,
                        title=f"Episodio {ep_num}",
                        sources=valid_sources,
                    )
                )

        seasons_list: list[TvSeason] = []
        for s_num in sorted(seasons_dict.keys()):
            ep_dict = {}
            for ep in seasons_dict[s_num]:
                if ep.episode_number not in ep_dict:
                    ep_dict[ep.episode_number] = ep
                else:
                    ep_dict[ep.episode_number].sources.extend(ep.sources)

            seasons_list.append(
                TvSeason(number=s_num, episodes=sorted(ep_dict.values(), key=lambda e: e.episode_number))
            )

        return TvSeries(
            id=series_id,
            title=clean_title,
            year=year,
            poster_url=poster_url,
            description=description,
            genres=genres,
            cb01_url=series_url,
            catalogs=["cb01"],
            seasons=seasons_list,
            added_at=added_at,
            updated_at=updated_at,
        )
