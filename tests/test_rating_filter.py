"""Unit tests for rating filter, adult content detection, and crawler age classification."""

from __future__ import annotations

import unittest

from streaming_hub.backend.crawler_parser import CrawlerCatalogParser
from streaming_hub.backend.models import Movie, Profile, TvSeries
from streaming_hub.backend.rating_filter import (
    get_profile_max_rating,
    is_title_allowed_for_profile,
)


class TestRatingFilter(unittest.TestCase):
    """Test suite for rating filter rules and profile safety."""

    def setUp(self) -> None:
        """Set up test profile instances."""
        self.profile_t = Profile(id="p_t", name="Bambini T", rating_filter="T")
        self.profile_6 = Profile(id="p_6", name="Bambini 6+", rating_filter="6+")
        self.profile_12 = Profile(id="p_12", name="Pre-teen 12+", rating_filter="12+")
        self.profile_14 = Profile(id="p_14", name="Teen 14+", rating_filter="14+")
        self.profile_18 = Profile(id="p_18", name="Adult 18+", rating_filter="18+")

    def test_get_profile_max_rating(self) -> None:
        """Test parsing profile rating filters to numeric thresholds."""
        self.assertEqual(get_profile_max_rating(self.profile_t), 0)
        self.assertEqual(get_profile_max_rating(self.profile_6), 6)
        self.assertEqual(get_profile_max_rating(self.profile_12), 12)
        self.assertEqual(get_profile_max_rating(self.profile_14), 14)
        self.assertEqual(get_profile_max_rating(self.profile_18), 18)
        self.assertEqual(get_profile_max_rating(Profile(id="p_all", name="All", rating_filter="ALL")), 99)

    def test_explicit_adult_flag_blocked(self) -> None:
        """Test that items with is_adult=True are blocked on any profile < 18."""
        adult_movie = Movie(id="m_adult", title="Titolo Generico", is_adult=True)
        self.assertFalse(is_title_allowed_for_profile(adult_movie, self.profile_t))
        self.assertFalse(is_title_allowed_for_profile(adult_movie, self.profile_6))
        self.assertFalse(is_title_allowed_for_profile(adult_movie, self.profile_14))
        self.assertTrue(is_title_allowed_for_profile(adult_movie, self.profile_18))

    def test_certification_vm18_blocked(self) -> None:
        """Test that certification VM18 is blocked on any profile < 18."""
        vm18_movie = Movie(id="m_vm18", title="Pellicola Drammatica", certification="VM18")
        self.assertFalse(is_title_allowed_for_profile(vm18_movie, self.profile_t))
        self.assertFalse(is_title_allowed_for_profile(vm18_movie, self.profile_6))
        self.assertFalse(is_title_allowed_for_profile(vm18_movie, self.profile_14))
        self.assertTrue(is_title_allowed_for_profile(vm18_movie, self.profile_18))

    def test_adult_franchises_blocked(self) -> None:
        """Test that famous adult/erotic titles and franchises are blocked on minor profiles."""
        adult_titles = [
            Movie(id="a1", title="365 Giorni", genres=["Drammatico"]),
            Movie(id="a2", title="365 Days: This Day", genres=["Drama"]),
            Movie(id="a3", title="Cinquanta Sfumature di Grigio", genres=["Drammatico", "Romantico"]),
            Movie(id="a4", title="Fifty Shades Freed", genres=["Drama", "Romance"]),
            Movie(id="a5", title="Nymphomaniac: Vol. I", genres=["Drammatico"]),
            Movie(id="a6", title="Kamasutra 3D", genres=["Drammatico"]),
            Movie(id="a7", title="Lucia y el sexo", genres=["Drammatico"]),
            Movie(id="a8", title="Desideri Proibiti", genres=["Erotico"]),
            Movie(id="a9", title="Peccati di Famiglia", genres=["Drammatico"]),
            Movie(id="a10", title="Malizia", genres=["Commedia"]),
        ]
        for m in adult_titles:
            with self.subTest(title=m.title):
                self.assertFalse(is_title_allowed_for_profile(m, self.profile_t))
                self.assertFalse(is_title_allowed_for_profile(m, self.profile_6))
                self.assertFalse(is_title_allowed_for_profile(m, self.profile_14))
                self.assertTrue(is_title_allowed_for_profile(m, self.profile_18))

    def test_uncertified_unfriendly_content_excluded_on_kids_profiles(self) -> None:
        """Test that uncertified content without family tags is excluded on Kids (T and 6+) profiles."""
        uncertified_items = [
            Movie(id="u1", title="Casalinghe disperate", description="", genres=[]),
            Movie(id="u2", title="Film Sospetto Sconosciuto", description="", genres=[]),
            Movie(id="u3", title="Dramma Familiare Intenso", description="Un dramma", genres=["Drammatico"]),
        ]
        for item in uncertified_items:
            with self.subTest(title=item.title):
                self.assertFalse(is_title_allowed_for_profile(item, self.profile_t))
                self.assertFalse(is_title_allowed_for_profile(item, self.profile_6))

    def test_safe_family_titles_allowed_on_kids_profiles(self) -> None:
        """Test that safe family titles and franchises pass for Kids profiles."""
        safe_items = [
            Movie(id="s1", title="Il Re Leone", genres=["Animazione", "Famiglia"]),
            Movie(id="s2", title="Frozen - Il regno di ghiaccio", genres=["Animazione", "Famiglia"]),
            Movie(id="s3", title="Paw Patrol: Il film", genres=["Animazione", "Kids"]),
            Movie(id="s4", title="Peppa Pig", genres=["Animazione", "Bambini"]),
            Movie(id="s5", title="Harry Potter e la Pietra Filosofale", genres=["Avventura", "Fantasy", "Famiglia"]),
        ]
        for item in safe_items:
            with self.subTest(title=item.title):
                self.assertTrue(is_title_allowed_for_profile(item, self.profile_t))
                self.assertTrue(is_title_allowed_for_profile(item, self.profile_6))
                self.assertTrue(is_title_allowed_for_profile(item, self.profile_14))

    def test_crawler_parser_extracts_age_certification(self) -> None:
        """Test that CrawlerCatalogParser extracts age certifications from HTML and title tags."""
        clean_title, year, quality, cert = CrawlerCatalogParser.clean_title("Film Proibito [VM18] (2023) [HD]")
        self.assertEqual(clean_title, "Film Proibito")
        self.assertEqual(year, 2023)
        self.assertEqual(quality, "HD")
        self.assertEqual(cert, "VM18")

        clean_title2, _, _, cert2 = CrawlerCatalogParser.clean_title("Azione Violenta 14+ Streaming")
        self.assertEqual(clean_title2, "Azione Violenta")
        self.assertEqual(cert2, "14+")

        genres, duration, country, meta_cert = CrawlerCatalogParser.parse_metadata_line("DURATA 120m - ITALIA - VM18")
        self.assertEqual(meta_cert, "VM18")
        self.assertEqual(duration, 120)


if __name__ == "__main__":
    unittest.main()
