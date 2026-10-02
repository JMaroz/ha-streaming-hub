"""Unit tests for watch history, progress tracking, and continue watching shelves."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile

from streaming_hub.backend.database import MediaDatabase


class TestWatchHistory:
    """Test suite for watch history persistence and shelf logic."""

    def setup_method(self, method=None) -> None:
        """Create a temporary SQLite database for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_history.db"
        self.db = MediaDatabase(self.db_path)
        asyncio.run(self.db.init())

    def teardown_method(self, method=None) -> None:
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def test_movie_continue_watching_and_resume(self) -> None:
        """Test movie in-progress saving and retrieval."""
        asyncio.run(
            self.db.save_watch_progress(
                media_id="movie_1",
                title="Inception",
                media_type="movie",
                poster_url="https://image.tmdb.org/t/p/w500/inception.jpg",
                season_number=None,
                episode_number=None,
                progress_seconds=1800.0,
                duration_seconds=7200.0,
                profile_id="default",
            )
        )

        prog = asyncio.run(self.db.get_media_progress("movie_1", profile_id="default"))
        assert prog is not None
        assert prog["progress_seconds"] == 1800.0
        assert prog["duration_seconds"] == 7200.0

        cw = asyncio.run(self.db.get_continue_watching("default"))
        assert len(cw) == 1
        assert cw[0]["media_id"] == "movie_1"
        assert cw[0]["progress_percent"] == 25.0
        assert cw[0]["remaining_seconds"] == 5400
        assert not cw[0]["is_next_episode"]

    def test_movie_completion_thresholds(self) -> None:
        """Test that movies >= 90% progress are removed from continue watching and added to watched."""
        # 1. Below 90%
        asyncio.run(
            self.db.save_watch_progress(
                media_id="movie_2",
                title="Interstellar",
                media_type="movie",
                poster_url=None,
                season_number=None,
                episode_number=None,
                progress_seconds=3000.0,
                duration_seconds=6000.0,
                profile_id="default",
            )
        )
        cw = asyncio.run(self.db.get_continue_watching("default"))
        assert len(cw) == 1
        watched = asyncio.run(self.db.get_watched_history("default"))
        assert len(watched) == 0

        # 2. Reached 95% completion
        asyncio.run(
            self.db.save_watch_progress(
                media_id="movie_2",
                title="Interstellar",
                media_type="movie",
                poster_url=None,
                season_number=None,
                episode_number=None,
                progress_seconds=5800.0,
                duration_seconds=6000.0,
                profile_id="default",
            )
        )
        cw_after = asyncio.run(self.db.get_continue_watching("default"))
        assert len(cw_after) == 0
        watched_after = asyncio.run(self.db.get_watched_history("default"))
        assert len(watched_after) == 1
        assert watched_after[0]["media_id"] == "movie_2"
        assert watched_after[0]["progress_percent"] == 100.0

    def test_min_progress_threshold_ignored(self) -> None:
        """Test that titles with less than 15 seconds watched are not added to continue watching."""
        asyncio.run(
            self.db.save_watch_progress(
                media_id="movie_short",
                title="Short Preview",
                media_type="movie",
                poster_url=None,
                season_number=None,
                episode_number=None,
                progress_seconds=10.0,
                duration_seconds=3600.0,
                profile_id="default",
            )
        )
        cw = asyncio.run(self.db.get_continue_watching("default"))
        assert len(cw) == 0

    def test_tv_series_next_episode_advancement(self) -> None:
        """Test TV series continue watching and automatic next episode advancement."""
        # Prepopulate seasons table
        with self.db._get_connection() as conn:
            conn.execute(
                "INSERT INTO titles (id, media_type, title) VALUES (?, ?, ?)",
                ("series_1", "tv", "Stranger Things"),
            )
            episodes = [
                {"episode_number": 1, "title": "Chapter One", "poster_url": "s1e1.jpg"},
                {"episode_number": 2, "title": "Chapter Two", "poster_url": "s1e2.jpg"},
            ]
            conn.execute(
                "INSERT INTO seasons (id, series_id, season_number, episodes_json) VALUES (?, ?, ?, ?)",
                ("series_1_s1", "series_1", 1, json.dumps(episodes)),
            )

        # 1. Watch S1E1 at 50%
        asyncio.run(
            self.db.save_watch_progress(
                media_id="series_1",
                title="Stranger Things",
                media_type="tv",
                poster_url="series.jpg",
                season_number=1,
                episode_number=1,
                progress_seconds=1500.0,
                duration_seconds=3000.0,
                profile_id="default",
            )
        )
        cw = asyncio.run(self.db.get_continue_watching("default"))
        assert len(cw) == 1
        assert cw[0]["season_number"] == 1
        assert cw[0]["episode_number"] == 1
        assert not cw[0]["is_next_episode"]

        # 2. Finish S1E1 at 95%
        asyncio.run(
            self.db.save_watch_progress(
                media_id="series_1",
                title="Stranger Things",
                media_type="tv",
                poster_url="series.jpg",
                season_number=1,
                episode_number=1,
                progress_seconds=2900.0,
                duration_seconds=3000.0,
                profile_id="default",
            )
        )
        cw_next = asyncio.run(self.db.get_continue_watching("default"))
        assert len(cw_next) == 1
        assert cw_next[0]["season_number"] == 1
        assert cw_next[0]["episode_number"] == 2
        assert cw_next[0]["is_next_episode"]
        assert cw_next[0]["progress_seconds"] == 0

    def test_episode_specific_progress_lookup(self) -> None:
        """Test retrieving progress for specific seasons and episodes."""
        # Watch episode 1
        asyncio.run(
            self.db.save_watch_progress(
                media_id="series_2",
                title="Breaking Bad",
                media_type="tv",
                poster_url=None,
                season_number=1,
                episode_number=1,
                progress_seconds=1200.0,
                duration_seconds=3000.0,
                profile_id="default",
            )
        )
        # Watch episode 2
        asyncio.run(
            self.db.save_watch_progress(
                media_id="series_2",
                title="Breaking Bad",
                media_type="tv",
                poster_url=None,
                season_number=1,
                episode_number=2,
                progress_seconds=800.0,
                duration_seconds=3000.0,
                profile_id="default",
            )
        )

        # Lookup S1E1 specifically
        prog_ep1 = asyncio.run(
            self.db.get_media_progress("series_2", profile_id="default", season_number=1, episode_number=1)
        )
        assert prog_ep1 is not None
        assert prog_ep1["progress_seconds"] == 1200.0

        # Lookup S1E2 specifically
        prog_ep2 = asyncio.run(
            self.db.get_media_progress("series_2", profile_id="default", season_number=1, episode_number=2)
        )
        assert prog_ep2 is not None
        assert prog_ep2["progress_seconds"] == 800.0

        # Lookup non-existent S1E3
        prog_ep3 = asyncio.run(
            self.db.get_media_progress("series_2", profile_id="default", season_number=1, episode_number=3)
        )
        assert prog_ep3 is None

    def test_progress_not_carried_over_between_shows(self) -> None:
        """Test that switching between different movies or shows strictly isolates their progress."""
        # Save progress for Movie A
        asyncio.run(
            self.db.save_watch_progress(
                media_id="movie_A",
                title="Movie A",
                media_type="movie",
                poster_url=None,
                season_number=None,
                episode_number=None,
                progress_seconds=1000.0,
                duration_seconds=3000.0,
                profile_id="default",
            )
        )

        # Save progress for Movie B
        asyncio.run(
            self.db.save_watch_progress(
                media_id="movie_B",
                title="Movie B",
                media_type="movie",
                poster_url=None,
                season_number=None,
                episode_number=None,
                progress_seconds=150.0,
                duration_seconds=4000.0,
                profile_id="default",
            )
        )

        # Ensure querying Movie C (never watched) returns None, NOT Movie A or B's progress
        prog_c = asyncio.run(self.db.get_media_progress("movie_C", profile_id="default"))
        assert prog_c is None

        # Ensure querying Movie B returns exactly 150.0, not contaminated by Movie A
        prog_b = asyncio.run(self.db.get_media_progress("movie_B", profile_id="default"))
        assert prog_b is not None
        assert prog_b["progress_seconds"] == 150.0

        # Save progress for Series X S1E1
        asyncio.run(
            self.db.save_watch_progress(
                media_id="series_X",
                title="Series X",
                media_type="tv",
                poster_url=None,
                season_number=1,
                episode_number=1,
                progress_seconds=1200.0,
                duration_seconds=2400.0,
                profile_id="default",
            )
        )

        # Ensure querying Series Y S1E1 (same season and episode, different series) returns None
        prog_y = asyncio.run(
            self.db.get_media_progress("series_Y", profile_id="default", season_number=1, episode_number=1)
        )
        assert prog_y is None


