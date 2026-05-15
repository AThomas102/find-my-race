from datetime import date

from typing import Literal

from fmr_core.models import Coordinates, CourseProfile, FieldSummary, Race, SearchQuery
from fmr_core.search import scored_matches


def _race(
    rid: str,
    title: str,
    *,
    lat: float,
    lon: float,
    median: float,
    terrain: Literal["flat", "undulating", "hilly", "unknown"] = "flat",
) -> Race:
    return Race(
        id=rid,
        title=title,
        start=date(2026, 6, 1),
        region="Testshire",
        coordinates=Coordinates(lat=lat, lon=lon),
        course=CourseProfile(distance_m=5000, terrain=terrain),
        field_summary=FieldSummary(
            median_5k_sec=median,
            p25_5k_sec=median - 60,
            p75_5k_sec=median + 60,
            sample_size=100,
            provenance="estimated",
        ),
    )


def test_geo_and_field_scoring_prefers_both():
    races = [
        _race("a", "Nearby soft field", lat=51.51, lon=-0.13, median=2000),
        _race("b", "Far strong field", lat=53.48, lon=-2.24, median=1200),
    ]
    q = SearchQuery(
        center_lat=51.5074,
        center_lon=-0.1278,
        radius_km=200,
        my_distance_m=5000,
        my_time_sec=1500,  # faster than 2000 median nearby
        field_weight=0.6,
    )
    m = scored_matches(races, q)
    titles = [x.race.title for x in m]
    assert "Nearby soft field" in titles
    # ordering: nearby should dominate with reasonable field overlap
    assert m[0].race.id == "a"
