from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from app.services.races import load_races
from fmr_core.models import SearchQuery
from fmr_core.search import scored_matches

router = APIRouter(tags=["search"])


def _serialize_match(m: Any) -> dict[str, Any]:
    r = m.race
    return {
        "race": {
            "id": r.id,
            "title": r.title,
            "start": r.start.isoformat(),
            "region": r.region,
            "location_label": r.location_label,
            "country": r.country,
            "coordinates": r.coordinates.model_dump() if r.coordinates else None,
            "postal_prefix": r.postal_prefix,
            "course": r.course.model_dump(),
            "field_summary": r.field_summary.model_dump() if r.field_summary else None,
            "sign_up_url": r.sign_up_url,
            "metadata": r.metadata,
        },
        "composite_score": round(m.composite_score, 4),
        "distance_km": None if m.distance_km is None else round(m.distance_km, 3),
        "user_equiv_5k_sec": m.user_equiv_5k_sec,
        "field_delta_sec": m.field_delta_sec,
        "reasons": m.reasons,
    }


@router.get("/search")
def search(request: Request, q: Annotated[SearchQuery, Depends()]) -> dict[str, Any]:
    path = request.app.state.races_path
    races = load_races(path)
    matches = scored_matches(races, q)
    return {
        "query": q.model_dump(),
        "count": len(matches),
        "results": [_serialize_match(m) for m in matches],
    }


@router.post("/search")
def search_post(request: Request, body: SearchQuery) -> dict[str, Any]:
    return search(request, body)
