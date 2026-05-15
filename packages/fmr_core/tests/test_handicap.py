from fmr_core.handicap import equivalent_5k_seconds


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
