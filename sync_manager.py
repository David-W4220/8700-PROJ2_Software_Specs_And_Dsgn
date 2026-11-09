"""Sync Manager module: transfers pending station updates to Earth."""


def sync_pending_updates() -> dict:
    """Send pending updates and report which updates Earth accepted."""
    raise NotImplementedError


def retry_update(update_id: str) -> dict:
    """Retry one update using its unique update ID."""
    raise NotImplementedError
