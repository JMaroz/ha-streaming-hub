"""SQLite Persistence Database for Streaming Hub.

Stores titles, posters, descriptions, TV seasons/episodes,
watch history, and user favorites persistently in /data/streaming_hub.db.
"""

from __future__ import annotations

import asyncio
import contextlib
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

    async def get_titles_by_genre(
        self,
        genre: str,
        media_type: str = "movie",
        limit: int = 40,
    ) -> list[Movie | TvSeries]:
        """Retrieve cached titles matching a genre."""
        async with self._lock:
            return await asyncio.to_thread(self._get_titles_by_genre_sync, genre, media_type, limit)

    def _get_titles_by_genre_sync(
        self,
        genre: str,
        media_type: str = "movie",
        limit: int = 40,
    ) -> list[Movie | TvSeries]:
        """Synchronously query titles matching a genre."""
        pattern = f"%{genre.lower()}%"
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT raw_json, media_type FROM titles
                WHERE (media_type = ? OR ? = 'all')
                  AND LOWER(genres) LIKE ?
                ORDER BY year DESC, rating DESC
                LIMIT ?
                """,
                (media_type, media_type, pattern, limit),
            )
            rows = cursor.fetchall()
            items: list[Movie | TvSeries] = []
            for row in rows:
                if row["raw_json"]:
                    try:
                        data = json.loads(row["raw_json"])
                        if row["media_type"] == "tv":
                            items.append(TvSeries.from_dict(data))
                        else:
                            items.append(Movie.from_dict(data))
                    except Exception:
                        continue
            return items

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

    async def get_continue_watching(self, limit: int = 20) -> list[dict[str, Any]]:
        """Retrieve deduplicated in-progress movies and TV series for 'Continua a guardare'."""
        async with self._lock:
            return await asyncio.to_thread(self._get_continue_watching_sync, limit)

    def _get_continue_watching_sync(self, limit: int) -> list[dict[str, Any]]:
        """Synchronously get continue watching list."""
        with self._get_connection() as conn:
            query = """
                SELECT h.id, h.media_id, h.title, h.poster_url, h.media_type,
                       h.season_number, h.episode_number, h.progress_seconds,
                       h.duration_seconds, h.updated_at,
                       t.backdrop_url, t.poster_url as title_poster, t.title as title_canonical
                FROM watch_history h
                INNER JOIN (
                    SELECT media_id, MAX(updated_at) as max_updated
                    FROM watch_history
                    GROUP BY media_id
                ) latest ON h.media_id = latest.media_id AND h.updated_at = latest.max_updated
                LEFT JOIN titles t ON h.media_id = t.id
                ORDER BY h.updated_at DESC
                LIMIT ?;
            """
            cursor = conn.execute(query, (limit * 2,))
            rows = [dict(r) for r in cursor.fetchall()]

            results: list[dict[str, Any]] = []
            for r in rows:
                media_type = r.get("media_type", "movie")
                duration = float(r.get("duration_seconds") or 0)
                progress = float(r.get("progress_seconds") or 0)
                percent = round((progress / duration * 100), 1) if duration > 0 else 0
                title_name = r.get("title_canonical") or r.get("title") or "Senza Titolo"
                poster = r.get("title_poster") or r.get("poster_url")
                backdrop = r.get("backdrop_url")

                if media_type == "movie":
                    if progress < 15:
                        continue
                    if percent >= 90 or (duration > 300 and (duration - progress) < 180):
                        continue

                    remaining = max(0, int(duration - progress)) if duration > 0 else 0
                    results.append({
                        "media_id": r["media_id"],
                        "title": title_name,
                        "media_type": "movie",
                        "poster_url": poster,
                        "backdrop_url": backdrop,
                        "progress_seconds": progress,
                        "duration_seconds": duration,
                        "progress_percent": percent,
                        "remaining_seconds": remaining,
                        "is_next_episode": False,
                        "updated_at": r["updated_at"],
                    })
                elif media_type == "tv":
                    curr_season = r.get("season_number") or 1
                    curr_ep = r.get("episode_number") or 1

                    is_completed = percent >= 90 or (duration > 120 and (duration - progress) < 90)
                    if is_completed:
                        next_ep = self._find_next_episode_sync(conn, r["media_id"], curr_season, curr_ep)
                        if next_ep:
                            results.append({
                                "media_id": r["media_id"],
                                "title": title_name,
                                "media_type": "tv",
                                "poster_url": next_ep.get("poster_url") or poster,
                                "backdrop_url": backdrop,
                                "season_number": next_ep["season_number"],
                                "episode_number": next_ep["episode_number"],
                                "episode_title": next_ep.get("title") or f"Episodio {next_ep['episode_number']}",
                                "progress_seconds": 0,
                                "duration_seconds": 0,
                                "progress_percent": 0,
                                "remaining_seconds": 0,
                                "is_next_episode": True,
                                "updated_at": r["updated_at"],
                            })
                    else:
                        if progress < 15:
                            continue
                        remaining = max(0, int(duration - progress)) if duration > 0 else 0
                        ep_title = self._get_episode_title_sync(conn, r["media_id"], curr_season, curr_ep)
                        results.append({
                            "media_id": r["media_id"],
                            "title": title_name,
                            "media_type": "tv",
                            "poster_url": poster,
                            "backdrop_url": backdrop,
                            "season_number": curr_season,
                            "episode_number": curr_ep,
                            "episode_title": ep_title or f"Episodio {curr_ep}",
                            "progress_seconds": progress,
                            "duration_seconds": duration,
                            "progress_percent": percent,
                            "remaining_seconds": remaining,
                            "is_next_episode": False,
                            "updated_at": r["updated_at"],
                        })

                if len(results) >= limit:
                    break

            return results

    def _find_next_episode_sync(self, conn: sqlite3.Connection, series_id: str, season_num: int, ep_num: int) -> dict[str, Any] | None:
        """Find the next episode in the current season or the first episode of the next season."""
        s_cursor = conn.execute("SELECT episodes_json FROM seasons WHERE series_id = ? AND season_number = ?", (series_id, season_num))
        row = s_cursor.fetchone()
        if row and row["episodes_json"]:
            with contextlib.suppress(Exception):
                episodes = json.loads(row["episodes_json"])
                for ep in episodes:
                    if int(ep.get("episode_number", 0)) == ep_num + 1:
                        return {
                            "season_number": season_num,
                            "episode_number": ep_num + 1,
                            "title": ep.get("title"),
                            "poster_url": ep.get("poster_url"),
                        }

        next_s_cursor = conn.execute(
            "SELECT episodes_json, season_number FROM seasons WHERE series_id = ? AND season_number = ?",
            (series_id, season_num + 1),
        )
        next_row = next_s_cursor.fetchone()
        if next_row and next_row["episodes_json"]:
            with contextlib.suppress(Exception):
                episodes = json.loads(next_row["episodes_json"])
                if episodes:
                    first_ep = episodes[0]
                    return {
                        "season_number": season_num + 1,
                        "episode_number": int(first_ep.get("episode_number", 1)),
                        "title": first_ep.get("title"),
                        "poster_url": first_ep.get("poster_url"),
                    }
        return None

    def _get_episode_title_sync(self, conn: sqlite3.Connection, series_id: str, season_num: int, ep_num: int) -> str | None:
        """Get cached episode title."""
        cursor = conn.execute("SELECT episodes_json FROM seasons WHERE series_id = ? AND season_number = ?", (series_id, season_num))
        row = cursor.fetchone()
        if row and row["episodes_json"]:
            with contextlib.suppress(Exception):
                episodes = json.loads(row["episodes_json"])
                for ep in episodes:
                    if int(ep.get("episode_number", 0)) == ep_num:
                        return ep.get("title")
        return None

    async def delete_watch_history(self, media_id: str) -> None:
        """Remove a title and all its episodes from watch history."""
        async with self._lock:
            await asyncio.to_thread(self._delete_watch_history_sync, media_id)

    def _delete_watch_history_sync(self, media_id: str) -> None:
        """Synchronously delete history by media_id."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM watch_history WHERE media_id = ?", (media_id,))

    async def get_media_progress(self, media_id: str) -> dict[str, Any] | None:
        """Get latest watch progress for a media_id."""
        async with self._lock:
            return await asyncio.to_thread(self._get_media_progress_sync, media_id)

    def _get_media_progress_sync(self, media_id: str) -> dict[str, Any] | None:
        """Synchronously get latest progress."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, media_id, title, poster_url, media_type,
                       season_number, episode_number, progress_seconds, duration_seconds, updated_at
                FROM watch_history
                WHERE media_id = ?
                ORDER BY updated_at DESC
                LIMIT 1;
                """,
                (media_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

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
