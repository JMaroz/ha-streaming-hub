"""Unit tests for database cache TTL, record age tracking, and background sync candidate selection."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from streaming_hub.backend.database import MediaDatabase
from streaming_hub.backend.main import get_season_episodes, get_title_details, source_manager
from streaming_hub.backend.models import Movie, ProviderSource, TvEpisode, TvSeason


class TestDatabaseCacheTTL:
    """Test suite ensuring cache TTL and record metadata tracking."""

    def setup_method(self, method=None) -> None:
        """Create a temporary database for isolation."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_ttl.db"
        self.db = MediaDatabase(self.db_path)
        asyncio.run(self.db.init())

    def teardown_method(self, method=None) -> None:
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def test_title_record_age_tracking(self) -> None:
        """Test that get_title_record returns valid data and age_seconds."""
        movie = Movie(
            id="movie_test_1",
            title="Inception",
            year=2010,
            rating=8.8,
            sources=[
                ProviderSource(
                    id="s1",
                    media_id="movie_test_1",
                    provider_id="reactive",
                    provider_name="ReactiveSource",
                    page_url="https://example.com/movie/1",
                )
            ],
        )
        asyncio.run(self.db.save_title(movie))

        rec = asyncio.run(self.db.get_title_record("movie_test_1"))
        assert rec is not None
        assert rec["data"]["title"] == "Inception"
        assert rec["data"]["year"] == 2010
        assert rec["age_seconds"] >= 0
        assert rec["updated_at"] != ""

        # Test standard get_title delegation
        direct = asyncio.run(self.db.get_title("movie_test_1"))
        assert direct is not None
        assert direct["title"] == "Inception"

    def test_season_record_age_tracking(self) -> None:
        """Test that get_season_record returns valid TvSeason and age_seconds."""
        season = TvSeason(
            number=2,
            episodes=[
                TvEpisode(
                    id="ep1",
                    media_id="series_test_1",
                    season_number=2,
                    episode_number=1,
                    title="Chapter 1",
                    sources=[
                        ProviderSource(
                            id="src_ep1",
                            media_id="series_test_1",
                            provider_id="reactive",
                            provider_name="ReactiveSource",
                            page_url="https://example.com/ep1",
                        )
                    ],
                ),
                TvEpisode(
                    id="ep2",
                    media_id="series_test_1",
                    season_number=2,
                    episode_number=2,
                    title="Chapter 2",
                ),
            ],
        )
        asyncio.run(self.db.save_season("series_test_1", season))

        rec = asyncio.run(self.db.get_season_record("series_test_1", 2))
        assert rec is not None
        assert isinstance(rec["season"], TvSeason)
        assert rec["season"].number == 2
        assert len(rec["season"].episodes) == 2
        assert rec["season"].episodes[0].title == "Chapter 1"
        assert rec["age_seconds"] >= 0
        assert rec["updated_at"] != ""

        # Test get_season delegation
        direct_season = asyncio.run(self.db.get_season("series_test_1", 2))
        assert direct_season is not None
        assert len(direct_season.episodes) == 2

    def test_background_sync_candidates_filtering(self) -> None:
        """Test candidate selection strictly filters to active items older than 12h."""
        # 1. Add fresh item in watch history (updated right now)
        asyncio.run(
            self.db.save_watch_progress(
                media_id="series_fresh",
                title="Fresh Series",
                media_type="tv",
                season_number=1,
                episode_number=1,
                progress_seconds=500,
                duration_seconds=2000,
            )
        )
        # Seed fresh season updated right now
        asyncio.run(self.db.save_season("series_fresh", TvSeason(number=1, episodes=[])))

        # 2. Add stale series in watch history, with a season updated 2 days ago
        asyncio.run(
            self.db.save_watch_progress(
                media_id="series_stale",
                title="Stale Series",
                media_type="tv",
                season_number=3,
                episode_number=2,
                progress_seconds=1200,
                duration_seconds=3000,
            )
        )
        with self.db._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO seasons (id, series_id, season_number, episodes_json, updated_at)
                VALUES ('series_stale_s3', 'series_stale', 3, '[]', datetime('now', '-2 days'))
                """
            )

        # 3. Add stale movie in favorites, updated 3 days ago in titles
        asyncio.run(
            self.db.toggle_favorite(
                title_id="movie_stale",
                media_type="movie",
                title="Stale Movie",
                poster_url=None,
            )
        )
        with self.db._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO titles (id, media_type, title, updated_at)
                VALUES ('movie_stale', 'movie', 'Stale Movie', datetime('now', '-3 days'))
                """
            )

        candidates = asyncio.run(self.db.get_candidates_for_background_sync(limit=10))

        # Fresh series should NOT be a candidate because age_seconds <= 43200
        candidate_ids = [c["media_id"] for c in candidates]
        assert "series_fresh" not in candidate_ids
        assert "series_stale" in candidate_ids
        assert "movie_stale" in candidate_ids

        # Verify target season for series_stale is season 3
        stale_cand = next(c for c in candidates if c["media_id"] == "series_stale")
        assert stale_cand["season_number"] == 3
        assert stale_cand["media_type"] == "tv"
        assert stale_cand["age_seconds"] > 86400  # Older than 1 day


@pytest.mark.asyncio
class TestRefreshEndpoints:
    """Test suite ensuring ?refresh=true triggers fresh fetches and fallback."""

    @pytest.fixture(autouse=True)
    async def setup_db(self) -> None:
        """Initialize main.db tables before running endpoint tests."""
        from streaming_hub.backend.main import db

        await db.init()

    async def test_season_endpoint_refresh_flow(self) -> None:
        """Test get_season_episodes handles fresh fetch and refresh=true."""
        mock_season = TvSeason(
            number=2,
            episodes=[
                TvEpisode(
                    id="ep1",
                    media_id="sc-mobland-test",
                    season_number=2,
                    episode_number=1,
                    title="Episodio 1",
                ),
                TvEpisode(
                    id="ep2",
                    media_id="sc-mobland-test",
                    season_number=2,
                    episode_number=2,
                    title="Episodio 2",
                ),
                TvEpisode(
                    id="ep3",
                    media_id="sc-mobland-test",
                    season_number=2,
                    episode_number=3,
                    title="Episodio 3",
                ),
            ],
        )

        with patch.object(source_manager, "get_season", new_callable=AsyncMock) as mock_get_season:
            mock_get_season.return_value = mock_season

            data = await get_season_episodes("sc-mobland-test", 2, refresh=True)
            assert data["number"] == 2
            assert len(data["episodes"]) == 3
            assert data["episodes"][2]["title"] == "Episodio 3"
            assert data["age_seconds"] == 0
            assert "updated_at" in data

    async def test_season_endpoint_fallback_on_upstream_failure(self) -> None:
        """Test get_season_episodes falls back to cache when upstream fails."""
        initial_season = TvSeason(
            number=1,
            episodes=[
                TvEpisode(
                    id="ep1",
                    media_id="fallback_series",
                    season_number=1,
                    episode_number=1,
                    title="Initial Ep 1",
                )
            ],
        )
        with patch.object(source_manager, "get_season", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = initial_season
            data1 = await get_season_episodes("fallback_series", 1, refresh=True)
            assert len(data1["episodes"]) == 1

        # Trigger refresh with upstream failure
        with patch.object(source_manager, "get_season", new_callable=AsyncMock) as mock_fail:
            mock_fail.side_effect = RuntimeError("Upstream provider offline")

            data_fallback = await get_season_episodes("fallback_series", 1, refresh=True)
            assert len(data_fallback["episodes"]) == 1
            assert data_fallback["episodes"][0]["title"] == "Initial Ep 1"

    async def test_title_endpoint_refresh_flow(self) -> None:
        """Test get_title_details updates sources on refresh=true."""
        fresh_movie = Movie(
            id="movie_refresh_test",
            title="Gladiator II",
            year=2024,
            sources=[
                ProviderSource(
                    id="ms_1",
                    media_id="movie_refresh_test",
                    provider_id="maxstream",
                    provider_name="Maxstream",
                    page_url="https://maxstream.video/123",
                    quality="1080p FHD",
                )
            ],
        )

        with patch.object(source_manager, "get_details", new_callable=AsyncMock) as mock_details:
            mock_details.return_value = fresh_movie

            data = await get_title_details("movie", "movie_refresh_test", refresh=True)
            assert data["title"] == "Gladiator II"
            assert len(data["sources"]) == 1
            assert data["sources"][0]["quality"] == "1080p FHD"
            assert data["age_seconds"] == 0
