"""Station Storage module: local inventory and pending-update persistence."""


def save_offline_change(update: dict) -> dict:
    """Persist a station inventory change and its pending-sync record."""
    raise NotImplementedError


def get_sync_status() -> dict:
    """Return the pending-update count and last successful sync time."""
    raise NotImplementedError
