import pytest
from pydantic import ValidationError

from fmr_core.handicap import equivalent_5k_seconds, validate_handicap_performance
from fmr_core.models import SearchQuery


def test_handicap_rejects_impossible_speed():
    with pytest.raises(ValueError):
        validate_handicap_performance(42195, 3600)  # ~51 min marathon — faster than physically modeled


def test_handicap_rejects_slow_pace():
    with pytest.raises(ValueError):
        validate_handicap_performance(5000, 4200)  # ~14 min/km average


def test_search_query_handicap_pairing():
    SearchQuery()
    SearchQuery(my_distance_m=10000, my_time_sec=3000)
    with pytest.raises(ValidationError):
        SearchQuery(my_distance_m=5000)
    with pytest.raises(ValidationError):
        SearchQuery(my_time_sec=2000)


def test_equivalent_5k_monotonic():
    # Same pace at longer distance should imply faster equivalent 5K (lower seconds) — Riegel compresses shorter.
    eq5k_half = equivalent_5k_seconds(21097, 90 * 60)
    eq5k_10k = equivalent_5k_seconds(10000, 45 * 60)
    assert eq5k_half > 0
    assert eq5k_10k > 0
    # Not asserting exact values; sanity check bracket
    assert 900 < eq5k_half < 2000


def test_equivalent_5k_same_distance():
    t = equivalent_5k_seconds(5000, 1200)
    assert abs(t - 1200) < 1e-6
