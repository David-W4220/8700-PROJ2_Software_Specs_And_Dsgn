import math, uuid
from fastapi import HTTPException
from app.modules import local_data_storage as storage


def find_item(item_id: str) -> dict:
    #Find one inventory item using local storage.
    item = storage.get_inventory_item(item_id)

    if item is None:
        raise HTTPException(status_code=404, detail=f"Inventory item '{item_id}' was not found.",)

    return item


def set_quantity(item_id: str, quantity: float, user_id: str,) -> dict:
    """
    Set an item's current quantity (must >= 0)
    The inventory update and audit record are saved atomically
    """
    try:
        new_quantity = float(quantity)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Quantity must be a number!",)

    if not math.isfinite(new_quantity) or new_quantity < 0:
        raise HTTPException(status_code=422, detail="Quantity must >= 0!",)

    item = storage.get_inventory_item(item_id)

    if item is None:
        raise HTTPException(status_code=404, detail=f"Inventory item '{item_id}' was not found.",)

    old_quantity = float(item["quantity"])
    timestamp = storage.utc_timestamp()

    updated_item = {
        **item,
        "quantity": new_quantity,
        "updated_at": timestamp,
    }

    update_record = {
        "update_id": str(uuid.uuid4()),
        "item_id": item_id,
        "user_id": user_id,
        "old_quantity": old_quantity,
        "new_quantity": new_quantity,
        "update_type": "quantity_update",
        "timestamp": timestamp,
        "details": {},
    }

    audit_record = {
        "audit_id": str(uuid.uuid4()),
        "timestamp": timestamp,
        "user_id": user_id,
        "action": "inventory.quantity_updated",
        "entity_type": "inventory_item",
        "entity_id": item_id,
        "old_values": {"quantity": old_quantity},
        "new_values": {"quantity": new_quantity},
        "details": {},
    }

    try:
        storage.save_quantity_change(updated_item, update_record,audit_record,)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Inventory item '{item_id}' was not found.",)
    return updated_item


def get_update_history(item_id: str) -> list[dict]:
    #Return the quantity update history for one inventory item.
    find_item(item_id)
    return storage.list_inventory_updates(item_id)


def list_inventory() -> list[dict]:
    #Return all locally stored inventory items.
    return storage.list_inventory_items()


def record_usage(item_id: str, quantity_used: float, user_id: str,):
    raise NotImplementedError


def add_received_quantity(item_id: str, quantity_received: float,user_id: str,):
    raise NotImplementedError
