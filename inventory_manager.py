"""Inventory Manager module: validates and records supply use."""

from datetime import datetime


def record_supply_use(
    item_id: str,
    used_quantity: int,
    user_id: str,
    now: datetime,
    update_id: str,
) -> dict:
    """Record a crew member's supply use and return the updated inventory item."""
    raise NotImplementedError
