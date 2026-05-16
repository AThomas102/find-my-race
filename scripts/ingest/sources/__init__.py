"""Discoverable ingest sources (plugin-style registry)."""

from __future__ import annotations

from typing import Callable

from ingest.sources.base import RaceDetailSource, RaceListingSource
from ingest.sources.curated_json import CuratedJsonListingSource, CuratedJsonPassThroughDetail
from ingest.sources.seed_ldjson import SeedLdjsonListingSource

SOURCE_REGISTRY: dict[str, Callable[..., RaceListingSource]] = {
    "curated": CuratedJsonListingSource,
    "curated_json": CuratedJsonListingSource,
    "seed-ldjson": SeedLdjsonListingSource,
}

DETAIL_REGISTRY: dict[str, Callable[..., RaceDetailSource]] = {
    "curated": CuratedJsonPassThroughDetail,
    "curated_json": CuratedJsonPassThroughDetail,
    "seed-ldjson": CuratedJsonPassThroughDetail,
}


def get_listing_source(name: str, config_path: str) -> RaceListingSource:
    try:
        factory = SOURCE_REGISTRY[name]
    except KeyError as e:
        raise KeyError(f"Unknown listing source {name!r}. Available: {sorted(SOURCE_REGISTRY)}") from e
    return factory(config_path)


def get_detail_source(name: str) -> RaceDetailSource:
    try:
        factory = DETAIL_REGISTRY[name]
    except KeyError as e:
        raise KeyError(f"Unknown detail source {name!r}. Available: {sorted(DETAIL_REGISTRY)}") from e
    return factory()
