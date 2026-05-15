from __future__ import annotations

import math


def equivalent_5k_seconds(distance_m: int, time_sec: float, *, exponent: float = 1.06) -> float:
    """
    Map an arbitrary-distance performance to equivalent 5K time using a Riegel-style factor.

    T2 = T1 * (D2/D1)^exponent

    This is a coarse public-road approximation; agents can swap in VDOT / WMA tables later
    without changing API shapes if they keep returning "seconds for equivalent 5K".
    """
    if distance_m <= 0 or time_sec <= 0:
        raise ValueError("distance_m and time_sec must be positive")
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
