from __future__ import annotations

import math


def max_plausible_average_speed_mps(distance_km: float) -> float:
    """
    Soft upper bound on average race speed versus distance (~world-record calibre, slightly generous).

    Tuned so (distance / v_max) is just below plausible WR averages from ~1 mi through marathon;
    extrapolates to ultras. Used only to reject obvious typos, not elite performances.
    """
    return 7.15 - 0.34 * math.log(distance_km + 1)


def validate_handicap_performance(distance_m: int, time_sec: float) -> None:
    """
    Ensure distance/time describe a plausible *running race* effort before Riegel mapping.

    Raises ValueError with a caller-facing reason when out of bounds.
    """
    if distance_m < 400 or distance_m > 120_000:
        raise ValueError("Handicap distance must be between 400 m and 120 km.")
    if time_sec <= 0:
        raise ValueError("Handicap time must be positive.")

    km = distance_m / 1000.0
    pace_sec_per_km = time_sec / km
    vmax = max_plausible_average_speed_mps(km)

    # Reject typo-slow paces (~13½ min/km sustained or slower across any distance bucket).
    if pace_sec_per_km > 810:
        raise ValueError(
            f"Pace averages about {pace_sec_per_km / 60.0:.1f} min/km — slower than handicap matching accepts. "
            "Tighten the time or clear it for geography-only sorting."
        )

    t_too_fast = (distance_m / vmax) * 0.982
    if time_sec < t_too_fast:
        floor_s = distance_m / vmax
        raise ValueError(
            f"That time is unrealistically fast for {km:g} km (~faster than {seconds_to_mmss(floor_s)} "
            "sustained). Check distance and clock time."
        )


def equivalent_5k_seconds(distance_m: int, time_sec: float, *, exponent: float = 1.06) -> float:
    """
    Map an arbitrary-distance performance to equivalent 5K time using a Riegel-style factor.

    T2 = T1 * (D2/D1)^exponent

    This is a coarse public-road approximation; agents can swap in VDOT / WMA tables later
    without changing API shapes if they keep returning "seconds for equivalent 5K".
    """
    if distance_m <= 0 or time_sec <= 0:
        raise ValueError("distance_m and time_sec must be positive")
    validate_handicap_performance(distance_m, time_sec)
    ratio = 5000.0 / float(distance_m)
    return float(time_sec) * (ratio**exponent)


def seconds_to_mmss(sec: float) -> str:
    if sec != sec:  # NaN
        return "—"
    s = max(0, int(round(sec)))
    m, r = divmod(s, 60)
    return f"{m}:{r:02d}"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))
    return r * c
