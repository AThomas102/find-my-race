from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from fmr_core.handicap import validate_handicap_performance

Provenance = Literal["past_results", "entrants", "estimated", "unknown"]


class Coordinates(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class FieldSummary(BaseModel):
    """Ability of the field expressed in equivalent 5K time (seconds, lower = faster)."""

    median_5k_sec: float | None = None
    p25_5k_sec: float | None = None
    p75_5k_sec: float | None = None
    sample_size: int | None = None
    provenance: Provenance = "unknown"


class CourseProfile(BaseModel):
    """Extensible course facts; add fields as new data sources appear."""

    distance_m: int | None = None
    surface: Literal["road", "trail", "track", "mixed", "unknown"] = "unknown"
    terrain: Literal["flat", "undulating", "hilly", "unknown"] = "unknown"
    elevation_gain_m: int | None = None
    loop_or_point_to_point: Literal["loop", "out_and_back", "point_to_point", "unknown"] = "unknown"


class Race(BaseModel):
    """Canonical race record consumed by search. JSON in `data/demo_races.json` matches this."""

    id: str
    title: str
    start: date | datetime
    region: str | None = None
    country: str = "GB"
    location_label: str | None = None
    coordinates: Coordinates | None = None
    postal_prefix: str | None = Field(
        default=None,
        description="Optional UK outward code or similar for coarse geo without precise coords.",
    )
    course: CourseProfile = Field(default_factory=CourseProfile)
    field_summary: FieldSummary | None = None
    sign_up_url: str | None = None
    results_url: str | None = Field(
        default=None,
        description="Official archive / results finder URL (distinct from signup when possible).",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("start", mode="before")
    @classmethod
    def parse_start(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                return date.fromisoformat(v[:10])
        return v

    @model_validator(mode="after")
    def lift_results_url_from_metadata(self) -> "Race":
        if self.results_url:
            return self
        if isinstance(self.metadata, dict):
            ru = self.metadata.get("results_url")
            if isinstance(ru, str) and ru.strip():
                return self.model_copy(update={"results_url": ru.strip()})
        return self


class SearchQuery(BaseModel):
    """User intent for /api/search; keep flat for simple query strings."""

    q: str | None = Field(default=None, description="Free-text over title / location")
    region: str | None = None
    center_lat: float | None = None
    center_lon: float | None = None
    radius_km: float = Field(default=80.0, ge=1, le=800)
    max_results: int = Field(default=30, ge=1, le=120)

    my_distance_m: int | None = Field(default=None, description="Recent race distance in metres")
    my_time_sec: float | None = Field(default=None, description="Recent race time in seconds")

    prefer_terrain: Literal["any", "flat", "undulating", "hilly"] = "any"
    prefer_surface: Literal["any", "road", "trail", "track", "mixed"] = "any"

    # How much to weight field match vs geography (0..1). 0.5 = equal.
    field_weight: float = Field(default=0.55, ge=0, le=1)

    @model_validator(mode="after")
    def handicap_inputs_consistent(self) -> SearchQuery:
        d, t = self.my_distance_m, self.my_time_sec
        if (d is None) != (t is None):
            raise ValueError(
                "Provide both my_distance_m and my_time_sec together, or omit both for geography-only search."
            )
        if d is not None and t is not None:
            validate_handicap_performance(int(d), float(t))
        return self
