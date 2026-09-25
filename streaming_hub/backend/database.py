"""SQLite Persistence Database for Streaming Hub.

Stores titles, posters, descriptions, TV seasons/episodes,
watch history, and user favorites persistently in /data/streaming_hub.db.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any

from .models import Movie, ProviderSource, TvEpisode, TvSeason, TvSeries

_LOGGER = logging.getLogger(__name__)

# Determine database path: /data for Home Assistant Add-on persistence, ./data for local dev
HA_DATA_DIR = Path("/data")
LOCAL_DATA_DIR = Path("./data")


def get_db_path() -> Path:
    """Return the SQLite database path depending on environment."""
    if HA_DATA_DIR.exists() and HA_DATA_DIR.is_dir():
        return HA_DATA_DIR / "streaming_hub.db"
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return LOCAL_DATA_DIR / "streaming_hub.db"


class MediaDatabase:
    """Persistent SQLite database manager."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize database manager."""
        self._db_path = db_path or get_db_path()
        self._lock = asyncio.Lock()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a configured SQLite connection."""
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    async def init(self) -> None:
        """Initialize tables and indexes."""
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        """Synchronously create tables."""
        _LOGGER.info("Initializing persistent SQLite database at %s", self._db_path)
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS titles (
                    id TEXT PRIMARY KEY,
                    media_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    original_title TEXT,
                    year INTEGER,
                    poster_url TEXT,
                    backdrop_url TEXT,
                    description TEXT,
                    genres TEXT,
                    duration INTEGER,
                    rating REAL,
                    cast_list TEXT,
                    director TEXT,
                    streamingcommunity_url TEXT,
                    cb01_url TEXT,
                    tmdb_id INTEGER,
                    imdb_id TEXT,
                    catalogs TEXT,
                    sources TEXT,
                    raw_json TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_titles_type ON titles(media_type);
                CREATE INDEX IF NOT EXISTS idx_titles_title ON titles(title);
                CREATE INDEX IF NOT EXISTS idx_titles_updated ON titles(updated_at);

                CREATE TABLE IF NOT EXISTS seasons (
                    id TEXT PRIMARY KEY,
                    series_id TEXT NOT NULL,
                    season_number INTEGER NOT NULL,
                    episodes_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_seasons_series ON seasons(series_id, season_number);

                CREATE TABLE IF NOT EXISTS watch_history (
                    id TEXT PRIMARY KEY,
                    media_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    poster_url TEXT,
                    media_type TEXT NOT NULL,
                    season_number INTEGER,
                    episode_number INTEGER,
                    progress_seconds REAL DEFAULT 0,
                    duration_seconds REAL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_history_updated ON watch_history(updated_at DESC);

                CREATE TABLE IF NOT EXISTS favorites (
                    title_id TEXT PRIMARY KEY,
                    media_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    poster_url TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

    async def save_title(self, item: Movie | TvSeries) -> None:
        """Persist a movie or TV series title with metadata to SQLite."""
        async with self._lock:
            await asyncio.to_thread(self._save_title_sync, item)

    def _save_title_sync(self, item: Movie | TvSeries) -> None:
        """Synchronously upsert a title."""
        media_type = "tv" if isinstance(item, TvSeries) else "movie"
        cast_json = json.dumps(item.cast or [])
        genres_json = json.dumps(item.genres or [])
        catalogs_json = json.dumps(item.catalogs or [])
        sources_json = json.dumps([s.to_dict() for s in getattr(item, "sources", [])])
        raw_json = json.dumps(item.to_dict())

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO titles (
                    id, media_type, title, original_title, year,
                    poster_url, backdrop_url, description, genres,
                    duration, rating, cast_list, director,
                    streamingcommunity_url, cb01_url,
                    tmdb_id, imdb_id, catalogs, sources, raw_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    original_title=excluded.original_title,
                    year=excluded.year,
                    poster_url=COALESCE(excluded.poster_url, titles.poster_url),
                    backdrop_url=COALESCE(excluded.backdrop_url, titles.backdrop_url),
                    description=COALESCE(excluded.description, titles.description),
                    genres=excluded.genres,
                    duration=COALESCE(excluded.duration, titles.duration),
                    rating=COALESCE(excluded.rating, titles.rating),
                    cast_list=excluded.cast_list,
                    director=COALESCE(excluded.director, titles.director),
                    streamingcommunity_url=COALESCE(excluded.streamingcommunity_url, titles.streamingcommunity_url),
                    cb01_url=COALESCE(excluded.cb01_url, titles.cb01_url),
                    tmdb_id=COALESCE(excluded.tmdb_id, titles.tmdb_id),
                    imdb_id=COALESCE(excluded.imdb_id, titles.imdb_id),
                    catalogs=excluded.catalogs,
                    sources=excluded.sources,
                    raw_json=excluded.raw_json,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (
                    item.id,
                    media_type,
                    item.title,
                    getattr(item, "original_title", None),
                    item.year,
                    item.poster_url,
                    item.backdrop_url,
                    item.description,
                    genres_json,
                    getattr(item, "duration", None),
                    item.rating,
                    cast_json,
                    item.director,
                    getattr(item, "streamingcommunity_url", None),
                    getattr(item, "cb01_url", None),
                    item.tmdb_id,
                    item.imdb_id,
                    catalogs_json,
                    sources_json,
                    raw_json,
                ),
            )

    async def get_title(self, title_id: str) -> dict[str, Any] | None:
        """Retrieve cached title dictionary from SQLite."""
        async with self._lock:
            return await asyncio.to_thread(self._get_title_sync, title_id)

    def _get_title_sync(self, title_id: str) -> dict[str, Any] | None:
        """Synchronously get title by id."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT raw_json FROM titles WHERE id = ?", (title_id,))
            row = cursor.fetchone()
            if row and row["raw_json"]:
                try:
                    return json.loads(row["raw_json"])
                except Exception as err:
                    _LOGGER.warning("Corrupted raw_json for title %s: %s", title_id, err)
        return None

    async def save_season(self, series_id: str, season: TvSeason) -> None:
        """Persist a season with all its episodes to SQLite."""
        async with self._lock:
            await asyncio.to_thread(self._save_season_sync, series_id, season)

    def _save_season_sync(self, series_id: str, season: TvSeason) -> None:
        """Synchronously upsert a season and episodes."""
        season_id = f"{series_id}_s{season.number}"
        episodes_json = json.dumps([ep.to_dict() for ep in season.episodes])

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO seasons (id, series_id, season_number, episodes_json, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    episodes_json=excluded.episodes_json,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (season_id, series_id, season.number, episodes_json),
            )

    async def get_season(self, series_id: str, season_number: int) -> TvSeason | None:
        """Retrieve a cached season with its episodes from SQLite."""
        async with self._lock:
            return await asyncio.to_thread(self._get_season_sync, series_id, season_number)

    def _get_season_sync(self, series_id: str, season_number: int) -> TvSeason | None:
        """Synchronously get season by series_id and season_number."""
        season_id = f"{series_id}_s{season_number}"
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT episodes_json FROM seasons WHERE id = ?", (season_id,))
            row = cursor.fetchone()
            if not row or not row["episodes_json"]:
                return None

            try:
                raw_episodes = json.loads(row["episodes_json"])
                episodes: list[TvEpisode] = []
                for ep in raw_episodes:
                    sources = [
                        ProviderSource(
                            id=s.get("id", ""),
                            media_id=s.get("media_id", ""),
                            provider_id=s.get("provider_id", ""),
                            provider_name=s.get("provider_name", ""),
                            page_url=s.get("page_url", ""),
                            language=s.get("language", "ita"),
                            quality=s.get("quality", "1080p FHD"),
                            available=s.get("available", True),
                        )
                        for s in ep.get("sources", [])
                    ]
                    episodes.append(
                        TvEpisode(
                            id=ep.get("id", ""),
                            media_id=ep.get("media_id", series_id),
                            season_number=season_number,
                            episode_number=int(ep.get("episode_number", 1)),
                            title=ep.get("title", ""),
                            description=ep.get("description"),
                            poster_url=ep.get("poster_url"),
                            sources=sources,
                        )
                    )
                return TvSeason(number=season_number, episodes=episodes)
            except Exception as err:
                _LOGGER.warning("Error parsing cached season %s: %s", season_id, err)
                return None

    async def save_watch_progress(
        self,
        media_id: str,
        title: str,
        media_type: str,
        poster_url: str | None = None,
        season_number: int | None = None,
        episode_number: int | None = None,
        progress_seconds: float = 0,
        duration_seconds: float = 0,
    ) -> None:
        """Save playback progress into watch_history table."""
        async with self._lock:
            await asyncio.to_thread(
                self._save_watch_progress_sync,
                media_id,
                title,
                media_type,
                poster_url,
                season_number,
                episode_number,
                progress_seconds,
                duration_seconds,
            )

    def _save_watch_progress_sync(
        self,
        media_id: str,
        title: str,
        media_type: str,
        poster_url: str | None,
        season_number: int | None,
        episode_number: int | None,
        progress_seconds: float,
        duration_seconds: float,
    ) -> None:
        """Synchronously upsert watch history."""
        hist_id = f"{media_id}_s{season_number}e{episode_number}" if season_number and episode_number else media_id
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO watch_history (
                    id, media_id, title, poster_url, media_type,
                    season_number, episode_number, progress_seconds, duration_seconds, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    progress_seconds=excluded.progress_seconds,
                    duration_seconds=excluded.duration_seconds,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (
                    hist_id,
                    media_id,
                    title,
                    poster_url,
                    media_type,
                    season_number,
                    episode_number,
                    progress_seconds,
                    duration_seconds,
                ),
            )

    async def get_watch_history(self, limit: int = 30) -> list[dict[str, Any]]:
        """Retrieve recent watch history."""
        async with self._lock:
            return await asyncio.to_thread(self._get_watch_history_sync, limit)

    def _get_watch_history_sync(self, limit: int) -> list[dict[str, Any]]:
        """Synchronously get watch history."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, media_id, title, poster_url, media_type,
                       season_number, episode_number, progress_seconds, duration_seconds, updated_at
                FROM watch_history
                ORDER BY updated_at DESC
                LIMIT ?;
                """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    async def toggle_favorite(self, title_id: str, media_type: str, title: str, poster_url: str | None) -> bool:
        """Toggle favorite status. Returns True if now favorite, False if removed."""
        async with self._lock:
            return await asyncio.to_thread(self._toggle_favorite_sync, title_id, media_type, title, poster_url)

    def _toggle_favorite_sync(self, title_id: str, media_type: str, title: str, poster_url: str | None) -> bool:
        """Synchronously toggle favorite."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT title_id FROM favorites WHERE title_id = ?", (title_id,))
            if cursor.fetchone():
                conn.execute("DELETE FROM favorites WHERE title_id = ?", (title_id,))
                return False
            conn.execute(
                "INSERT INTO favorites (title_id, media_type, title, poster_url, added_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (title_id, media_type, title, poster_url),
            )
            return True

    async def get_favorites(self) -> list[dict[str, Any]]:
        """Retrieve all user favorites."""
        async with self._lock:
            return await asyncio.to_thread(self._get_favorites_sync)

    def _get_favorites_sync(self) -> list[dict[str, Any]]:
        """Synchronously get all favorites."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT title_id, media_type, title, poster_url, added_at FROM favorites ORDER BY added_at DESC")
            return [dict(row) for row in cursor.fetchall()]
