"""Station Storage module: local inventory and pending-update persistence."""


def save_offline_change(update: dict) -> dict:
    """Persist a station inventory change and its pending-sync record."""
    raise NotImplementedError


def get_sync_status() -> dict:
    """Return the pending-update count and last successful sync time."""
    raise NotImplementedError


def get_inventory_item(item_id: str) -> dict:
    """Return a station-local inventory record by item ID."""
    raise NotImplementedError


def get_update_history(item_id: str) -> dict:
    """Return the recorded update history for one station inventory item."""
    raise NotImplementedError
