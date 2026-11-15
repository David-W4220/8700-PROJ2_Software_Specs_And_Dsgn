"""Station Storage module: local inventory and pending-update persistence."""

_state = {
    "items": {},
    "updates": [],
    "pending": [],
    "last_successful_sync": None,
}


def save_offline_change(update: dict) -> dict:
    """Persist a station inventory change and its pending-sync record."""
    item_id = update["item_id"]
    item = _state["items"][item_id]
    item["quantity"] = update["quantity"]
    record = dict(update)
    _state["updates"].append(record)
    _state["pending"].append(record)
    return {
        "item_id": item_id,
        "quantity": item["quantity"],
        "unit": item["unit"],
        "pending_count": len(_state["pending"]),
        "last_successful_sync": _state["last_successful_sync"],
        "update_id": record["update_id"],
    }


def get_sync_status() -> dict:
    """Return the pending-update count and last successful sync time."""
    return {
        "pending_count": len(_state["pending"]),
        "last_successful_sync": _state["last_successful_sync"],
    }


def get_inventory_item(item_id: str) -> dict:
    """Return a station-local inventory record by item ID."""
    return dict(_state["items"][item_id])


def get_update_history(item_id: str) -> dict:
    """Return the recorded update history for one station inventory item."""
    return {
        "updates": [dict(update) for update in _state["updates"] if update["item_id"] == item_id]
    }
