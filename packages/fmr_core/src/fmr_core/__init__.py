"""Find My Race — core domain logic (no FastAPI/React dependencies)."""

from fmr_core.handicap import equivalent_5k_seconds, seconds_to_mmss
from fmr_core.models import Coordinates, CourseProfile, FieldSummary, Race, SearchQuery
from fmr_core.search import scored_matches

__all__ = [
    "Coordinates",
    "CourseProfile",
    "FieldSummary",
    "Race",
    "SearchQuery",
    "equivalent_5k_seconds",
    "seconds_to_mmss",
    "scored_matches",
]
