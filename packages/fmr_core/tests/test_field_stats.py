from fmr_core.field_stats import field_summary_stats_from_equiv_5k


def test_empty():
    assert field_summary_stats_from_equiv_5k([]) == {
        "median_5k_sec": None,
        "p25_5k_sec": None,
        "p75_5k_sec": None,
        "sample_size": 0,
    }


def test_basic_percentiles():
    out = field_summary_stats_from_equiv_5k([1000.0, 1200.0, 1400.0, 1600.0, 1800.0])
    assert out["sample_size"] == 5
    assert out["median_5k_sec"] == 1400.0
    assert out["p25_5k_sec"] is not None and out["p75_5k_sec"] is not None
    assert out["p25_5k_sec"] < out["median_5k_sec"] < out["p75_5k_sec"]
