"""HTTP entry point for the station inventory skeleton."""

from flask import Flask, jsonify, request

from conflict_review import resolve_conflict
from inventory_interface import get_earth_inventory_view
from inventory_manager import record_supply_use
from station_storage import get_inventory_item, get_sync_status, get_update_history, save_offline_change
from sync_manager import retry_update, sync_pending_updates

app = Flask(__name__)


def not_implemented_response(operation: str):
    return jsonify(
        error="not_implemented",
        message=f"{operation} is declared by the contract but not implemented.",
    ), 501


@app.post("/inventory/items/<item_id>/usage")
def post_supply_use(item_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        record_supply_use(
            item_id=item_id,
            used_quantity=payload.get("used_quantity"),
            user_id=payload.get("user_id"),
            now=payload.get("now"),
            update_id=payload.get("update_id"),
        )
    except NotImplementedError:
        return not_implemented_response("Record supply use")
    return not_implemented_response("Record supply use")


@app.get("/earth/inventory")
def get_earth_inventory():
    try:
        get_earth_inventory_view()
    except NotImplementedError:
        return not_implemented_response("View inventory from Earth")
    return not_implemented_response("View inventory from Earth")


@app.post("/station/offline/updates")
def post_offline_update():
    payload = request.get_json(silent=True) or {}
    try:
        save_offline_change(update=payload.get("update"))
    except NotImplementedError:
        return not_implemented_response("Save an offline inventory change")
    return not_implemented_response("Save an offline inventory change")


@app.get("/station/sync-status")
def get_station_sync_status():
    try:
        get_sync_status()
    except NotImplementedError:
        return not_implemented_response("View station synchronization status")
    return not_implemented_response("View station synchronization status")


@app.get("/station/inventory/items/<item_id>")
def get_station_inventory_item(item_id: str):
    try:
        get_inventory_item(item_id=item_id)
    except NotImplementedError:
        return not_implemented_response("View station inventory item")
    return not_implemented_response("View station inventory item")


@app.get("/station/inventory/items/<item_id>/updates")
def get_station_item_updates(item_id: str):
    try:
        get_update_history(item_id=item_id)
    except NotImplementedError:
        return not_implemented_response("View station item update history")
    return not_implemented_response("View station item update history")


@app.post("/sync")
def post_sync():
    try:
        sync_pending_updates()
    except NotImplementedError:
        return not_implemented_response("Synchronize pending updates")
    return not_implemented_response("Synchronize pending updates")


@app.post("/sync/updates/<update_id>/retry")
def post_retry_update(update_id: str):
    try:
        retry_update(update_id=update_id)
    except NotImplementedError:
        return not_implemented_response("Retry an inventory update")
    return not_implemented_response("Retry an inventory update")


@app.post("/conflicts/<conflict_id>/resolve")
def post_resolve_conflict(conflict_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        resolve_conflict(
            conflict_id=conflict_id,
            selected_location=payload.get("selected_location"),
            reason=payload.get("reason"),
            reviewer_id=payload.get("reviewer_id"),
            now=payload.get("now"),
        )
    except NotImplementedError:
        return not_implemented_response("Resolve an inventory conflict")
    return not_implemented_response("Resolve an inventory conflict")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
