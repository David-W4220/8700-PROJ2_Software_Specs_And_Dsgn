"""Conflict Review module: authorized review of station/Earth conflicts."""

from datetime import datetime


def resolve_conflict(
    conflict_id: str,
    selected_location: str,
    reason: str,
    reviewer_id: str,
    now: datetime,
) -> dict:
    """Resolve a location conflict and return its recorded resolution."""
    raise NotImplementedError
