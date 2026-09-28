"""Content classification and rating filter for Streaming Hub profiles.

Provides age classification, certification mapping, and content validation
to prevent adult, mature, or unsuitable content from leaking into family/minor profiles.
"""

from __future__ import annotations

import re
from typing import Any

from .models import Movie, Profile, TvSeries

# Rating Hierarchy: T (0) -> 6+ (6) -> 12+ (12) -> 14+ (14) -> 16+ (16) -> 18+ (18) -> ALL (99)
RATING_MAP: dict[str, int] = {
    # Family / All audiences (0)
    "T": 0, "0": 0, "G": 0, "TV-Y": 0, "TV-G": 0, "PEGI 3": 0, "PEGI 0": 0,
    "KIDS": 0, "BAMBINI": 0, "PER TUTTI": 0, "FAMIGLIA": 0,
    # Children (6)
    "6+": 6, "+6": 6, "6": 6, "PG": 6, "TV-Y7": 6, "TV-PG": 6, "PEGI 7": 6, "PEGI 6": 6,
    # Pre-teen (12)
    "12+": 12, "+12": 12, "12": 12, "PG-13": 13, "PEGI 12": 12,
    # Teen (14)
    "14+": 14, "+14": 14, "14": 14, "VM14": 14, "VM 14": 14, "TV-14": 14, "PEGI 14": 14,
    "TEEN": 14, "RAGAZZI": 14, "MINORI 14": 14,
    # Mature teen (16)
    "16+": 16, "+16": 16, "16": 16, "VM16": 16, "VM 16": 16, "PEGI 16": 16,
    # Adults only (18)
    "18+": 18, "+18": 18, "18": 18, "VM18": 18, "VM 18": 18, "R": 17, "NC-17": 18,
    "TV-MA": 18, "PEGI 18": 18, "ADULT": 18, "ADULTI": 18, "PORNO": 18, "XXX": 18,
    # Unrestricted (99)
    "ALL": 99, "TUTTI": 99, "NONE": 99, "": 99, "DEFAULT": 99,
}

# Explicit adult / erotic keywords across Italian and English
ADULT_KEYWORDS: set[str] = {
    "erotico", "erotica", "erotismo", "erotic", "adulti", "adult", "adulto",
    "pornografico", "pornografia", "porno", "softcore", "hardcore", "hentai",
    "sexy", "red light", "vm18", "vm16", "18+", "16+", "xxx", "sesso", "sessual",
    "sensuale", "nudo", "nuda", "nudita", "nudità", "luce rossa", "a luci rosse",
    "hard", "orgia", "orgie", "orgy", "scambist", "eroguro", "ecchi", "hot",
    "peccato carnale", "tentazione proibita", "incesto", "trasgressione", "voyeur",
    "feticis", "passione carnale", "intimo", "rapporti intimi", "scene esplicite",
    "pellicola a luci rosse", "cinema a luci rosse", "pornodiva", "pornostar"
}

# Strict adult genres that must be blocked for any profile < 18
ADULT_GENRES: set[str] = {
    "erotico", "erotica", "erotismo", "erotic", "adulti", "adult",
    "pornografico", "porno", "softcore", "hardcore", "hentai",
    "sexy", "red light", "xxx"
}

# Content restricted for kids / children (max_allowed <= 6)
KIDS_RESTRICTED_KEYWORDS: set[str] = {
    "horror", "splatter", "gore", "crime", "thriller", "giallo",
    "poliziesco", "guerra", "war", "psicologico", "mistero", "violenza"
}

UNSAFE_TITLE_KEYWORDS: set[str] = {
    "resident evil", "unabomber", "kill", "killer", "assassin", "blood",
    "dead", "death", "zombie", "horror", "morte", "sangue", "massacro",
    "omicidio", "delitto", "erotico", "sesso", "sex", "alien", "predator",
    "nightmare", "saw", "demon", "diavolo", "satana", "evil", "terror"
}

FAMILY_FRIENDLY_KEYWORDS: set[str] = {
    "animazione", "animation", "famiglia", "family", "kids", "bambini",
    "ragazzi", "children", "avventura", "adventure", "musica", "music",
    "commedia", "comedy", "documentario", "documentary", "fantasy", "fiaba"
}


def get_profile_max_rating(profile: Profile | str | None) -> int:
    """Parse profile rating filter into maximum numerical age limit.

    Hierarchy:
      - 'T' / '0' / 'KIDS' / 'PEGI 3' -> 0
      - '6+' / '+6' / 'PEGI 7' -> 6
      - '12+' / '+12' / 'PEGI 12' -> 12
      - '14+' / '+14' / 'PEGI 14' -> 14
      - '16+' / '+16' / 'PEGI 16' -> 16
      - '18+' / '+18' / 'PEGI 18' -> 18
      - 'ALL' / None -> 99
    """
    if profile is None:
        return 99

    raw_filter = getattr(profile, "rating_filter", profile)
    filter_val = str(raw_filter or "ALL").upper().strip()

    if filter_val in ("ALL", "", "NONE", "TUTTI", "DEFAULT"):
        return 99

    if filter_val in RATING_MAP:
        return RATING_MAP[filter_val]

    # Normalize by stripping spaces and symbols (e.g. "+14", "VM 14", "PEGI 14")
    normalized = re.sub(r"[\s\-_]", "", filter_val)
    if normalized in RATING_MAP:
        return RATING_MAP[normalized]

    # Extract digits like '+14' -> 14, '18' -> 18, '6' -> 6
    digits = "".join(ch for ch in filter_val if ch.isdigit())
    if digits:
        val = int(digits)
        return 0 if val <= 3 else val

    return 99


def get_profile_by_id(profile_id: str, profiles: list[Profile] | None = None) -> Profile:
    """Find profile by id or name with case-insensitivity, or fallback to first profile."""
    if not profiles:
        return Profile(id="default", name="Principale")

    target = str(profile_id or "").strip().lower()

    # 1. Exact match on id or name (case-insensitive)
    for p in profiles:
        if p.id.lower() == target or p.name.strip().lower() == target:
            return p

    # 2. Check if target matches slugified name or rating filter
    clean_target = re.sub(r"[^a-z0-9]", "", target)
    for p in profiles:
        slug_id = re.sub(r"[^a-z0-9]", "", p.id.lower())
        slug_name = re.sub(r"[^a-z0-9]", "", p.name.lower())
        slug_rating = re.sub(r"[^a-z0-9]", "", str(p.rating_filter or "").lower())
        if clean_target in (slug_id, slug_name, slug_rating):
            return p

    return profiles[0]


def is_title_allowed_for_profile(
    title_item: Movie | TvSeries | dict[str, Any],
    profile: Profile,
) -> bool:
    """Determine if a title passes the profile's content classification filter.

    Enforces strict rules:
      - Profiles under 18 strictly block any adult/erotic content, adult keywords,
        or certifications > max_allowed.
      - Teen profiles (<= 14) block extreme splatter, gore, excessive violence, and adult content.
      - Children profiles (<= 6) block horror, crime, thriller, psychological violence.
      - Kids profiles (T / 0) strictly require family-friendly genres/keywords.
    """
    max_allowed = get_profile_max_rating(profile)
    if max_allowed >= 99:
        return True

    # Extract title, certification, genres, and full description
    if isinstance(title_item, dict):
        title = str(title_item.get("title") or "").lower()
        cert = str(title_item.get("certification") or "").upper().strip()
        genres = [str(g).lower().strip() for g in title_item.get("genres") or []]
        desc = str(title_item.get("description") or "").lower()
    else:
        title = str(getattr(title_item, "title", "") or "").lower()
        cert = str(getattr(title_item, "certification", "") or "").upper().strip()
        genres = [str(g).lower().strip() for g in getattr(title_item, "genres", []) or []]
        desc = str(getattr(title_item, "description", "") or "").lower()

    genres_str = " ".join(genres)
    combined_text = f"{title} {genres_str} {desc}"

    # For any profile under 18: strictly block adult / erotic content
    if max_allowed < 18:
        # Check adult genres
        if any(ag in genres_str for ag in ADULT_GENRES):
            return False

        # Check adult keywords across full metadata
        if any(ak in combined_text for ak in ADULT_KEYWORDS):
            return False

    # Check explicit certification if available
    if cert:
        score = RATING_MAP.get(cert)
        if score is None:
            clean_digits = "".join(ch for ch in cert if ch.isdigit())
            score = int(clean_digits) if clean_digits else None
        if score is not None:
            return score <= max_allowed

    # Fallback heuristic when certification is not explicitly tagged
    if max_allowed <= 6:
        # Kids / Children profile (T or 6+ / PEGI 3 / PEGI 7)
        if any(rk in combined_text for rk in KIDS_RESTRICTED_KEYWORDS):
            return False
        if any(uk in title for uk in UNSAFE_TITLE_KEYWORDS):
            return False

        # If profile is 'T' (0) - strict family / kids content only
        if max_allowed == 0:
            if genres and not any(fk in genres_str for fk in FAMILY_FRIENDLY_KEYWORDS):
                return False

    elif max_allowed <= 14:
        # Teen profile (12+ / 14+ / PEGI 12 / PEGI 14)
        if any(w in combined_text for w in (
            "splatter", "gore", "extreme horror", "hardcore", "snuff",
            "cannibal", "massacro", "tortura", "sadico"
        )):
            return False
        if any(uk in title for uk in ("erotico", "porno", "sesso", "xxx", "hardcore", "luci rosse")):
            return False

    return True
