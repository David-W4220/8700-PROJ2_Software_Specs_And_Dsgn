"""Ground Storage module: Earth-side inventory records."""

_state = {"items": [], "last_successful_sync": None, "conflicts": {}}


def get_inventory_snapshot() -> dict:
    """Return the inventory snapshot stored on Earth."""
    raise NotImplementedError
