from __future__ import annotations

from dataclasses import dataclass
import math

from fmr_core.handicap import equivalent_5k_seconds, haversine_km
from fmr_core.models import Race, SearchQuery


@dataclass(frozen=True)
class RaceMatch:
    race: Race
    composite_score: float
    distance_km: float | None
    user_equiv_5k_sec: float | None
    field_delta_sec: float | None
    reasons: list[str]


# Field match prefers you ~slightly slower than median finisher on equivalent 5K (mid-pack realism).
TARGET_FIELD_Z = -0.18
SIGMA_MIN = 0.74
SIGMA_MAX = 1.28
SIGMA_BASE = 0.92


def _text_haystack(r: Race) -> str:
    parts = [r.title, r.location_label or "", r.region or "", r.postal_prefix or ""]
    return " ".join(p for p in parts if p).lower()


def _passes_text(r: Race, q: SearchQuery) -> bool:
    if not q.q or not q.q.strip():
        return True
    needle = q.q.strip().lower()
    return needle in _text_haystack(r)


def _passes_region(r: Race, q: SearchQuery) -> bool:
    if not q.region or not q.region.strip():
        return True
    reg = q.region.strip().lower()
    return (r.region or "").lower() == reg or reg in (r.location_label or "").lower()


def _terrain_ok(r: Race, q: SearchQuery) -> bool:
    if q.prefer_terrain == "any":
        return True
    return r.course.terrain == q.prefer_terrain or r.course.terrain == "unknown"


def _surface_ok(r: Race, q: SearchQuery) -> bool:
    if q.prefer_surface == "any":
        return True
    return r.course.surface == q.prefer_surface or r.course.surface == "unknown"


def _geo_distance_km(r: Race, q: SearchQuery) -> float | None:
    if q.center_lat is None or q.center_lon is None:
        return None
    if r.coordinates is None:
        return None
    return haversine_km(q.center_lat, q.center_lon, r.coordinates.lat, r.coordinates.lon)


def _field_z_score(user_eq: float, race: Race) -> float | None:
    fs = race.field_summary
    if fs is None or fs.median_5k_sec is None:
        return None
    spread = None
    if fs.p25_5k_sec is not None and fs.p75_5k_sec is not None:
        iqr = max(fs.p75_5k_sec - fs.p25_5k_sec, 1e-6)
        spread = iqr / 1.349  # normal approx for IQR
    if spread is None or spread <= 0:
        spread = max(abs(fs.median_5k_sec) * 0.05, 30.0)
    return (user_eq - fs.median_5k_sec) / spread


def _field_sigma(race: Race) -> float:
    """Wider spread in field summary → more uncertainty → gentler z penalty."""
    fs = race.field_summary
    if fs is None or fs.median_5k_sec is None:
        return SIGMA_BASE
    spread = None
    if fs.p25_5k_sec is not None and fs.p75_5k_sec is not None:
        iqr = max(fs.p75_5k_sec - fs.p25_5k_sec, 1e-6)
        spread = iqr / 1.349
    if spread is None or spread <= 0:
        return SIGMA_BASE
    med = max(abs(fs.median_5k_sec), 400.0)
    norm = spread / max(med * 0.08, 35.0)
    return max(SIGMA_MIN, min(SIGMA_MAX, SIGMA_BASE * (0.84 + 0.28 * min(norm, 2.2))))


def _field_gaussian_score(z: float, sigma: float) -> float:
    return math.exp(-((z - TARGET_FIELD_Z) ** 2) / (2.0 * sigma * sigma))


def _distance_alignment_factor(race: Race, q: SearchQuery) -> float:
    """Slight preference for events whose stated distance is close to the performance you entered."""
    if not q.my_distance_m or not race.course.distance_m:
        return 1.0
    a, b = float(q.my_distance_m), float(race.course.distance_m)
    ratio = min(a, b) / max(a, b)
    return 0.78 + 0.22 * math.sqrt(ratio)


def scored_matches(races: list[Race], q: SearchQuery) -> list[RaceMatch]:
    """
    Score races for the UI. Higher composite_score is better.

    - Geography: events inside radius score ~1 at center, decay outside (or neutral if no coords).
    - Field: Gaussian on z-score vs typical finisher; peak slightly slower than median; sigma widens
      when field quartiles are noisy. Small boost when event distance matches your reference distance.
    """
    user_eq: float | None
    try:
        if q.my_distance_m and q.my_time_sec:
            user_eq = equivalent_5k_seconds(q.my_distance_m, q.my_time_sec)
        else:
            user_eq = None
    except ValueError:
        user_eq = None

    matches: list[RaceMatch] = []
    for r in races:
        if not _passes_text(r, q) or not _passes_region(r, q):
            continue
        if not _terrain_ok(r, q) or not _surface_ok(r, q):
            continue

        dist_km = _geo_distance_km(r, q)
        if dist_km is not None and dist_km > q.radius_km:
            continue

        reasons: list[str] = []

        # Geo component 0..1
        if dist_km is None:
            geo_score = 0.55
            reasons.append("Location filter skipped (no coordinates on event or query).")
        else:
            geo_score = max(0.0, 1.0 - (dist_km / max(q.radius_km, 1.0)))
            reasons.append(f"Within ~{dist_km:.1f} km of search centre.")

        # Field component — smooth preference around target z; align with event distance
        field_score = 0.5
        field_delta: float | None = None
        if user_eq is not None and r.field_summary and r.field_summary.median_5k_sec is not None:
            field_delta = user_eq - r.field_summary.median_5k_sec
            z = _field_z_score(user_eq, r)
            assert z is not None
            sigma = _field_sigma(r)
            field_score = _field_gaussian_score(z, sigma)
            field_score = min(1.0, field_score * _distance_alignment_factor(r, q))
            if z < -2.0:
                reasons.append("You look much faster than typical finishers — expect a small front pack.")
            elif z < -0.9:
                reasons.append("You look faster than typical finishers — expect to be up front.")
            elif z > 2.0:
                reasons.append("Typical finishers appear much faster — ambitious target or development race.")
            elif z > 0.9:
                reasons.append("Typical finishers appear faster — good stretch target.")
            else:
                reasons.append("Likely comparable to typical finishers (handicap vs median field).")

        fw = q.field_weight
        composite = fw * field_score + (1.0 - fw) * geo_score

        matches.append(
            RaceMatch(
                race=r,
                composite_score=composite,
                distance_km=dist_km,
                user_equiv_5k_sec=user_eq,
                field_delta_sec=field_delta,
                reasons=reasons,
            )
        )

    matches.sort(key=lambda m: m.composite_score, reverse=True)
    return matches[: q.max_results]
