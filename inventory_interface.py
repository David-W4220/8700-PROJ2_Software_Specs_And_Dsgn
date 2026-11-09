"""Inventory Interface module: user-facing inventory views."""


def get_earth_inventory_view() -> dict:
    """Return inventory quantities, units, and the last successful sync time."""
    raise NotImplementedError
