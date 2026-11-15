"""Inventory Manager module: validates and records supply use."""

from datetime import datetime

from station_storage import get_inventory_item, save_offline_change
from user_permissions import require_authenticated_user


def record_supply_use(
    item_id: str,
    used_quantity: int,
    user_id: str,
    now: datetime,
    update_id: str,
) -> dict:
    """Record a crew member's supply use and return the updated inventory item."""
    user = require_authenticated_user(user_id)
    item = get_inventory_item(item_id)

    time_value = now.isoformat()
    if time_value.endswith("+00:00"):
        time_value = time_value[:-6] + "Z"
    update = {
        "item_id": item_id,
        "used_quantity": used_quantity,
        "quantity": item["quantity"] - used_quantity,
        "unit": item["unit"],
        "user_id": user["user_id"],
        "time": time_value,
        "update_id": update_id,
    }
    saved = save_offline_change(update)
    return {
        "item_id": item_id,
        "name": item.get("name", item_id),
        "quantity": saved["quantity"],
        "unit": saved["unit"],
        "update": update,
    }
