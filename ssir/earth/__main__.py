"""Start the Earth Service: wiring only, no logic (see contracts.md, "Additions")."""
from __future__ import annotations

import argparse
import threading
from datetime import datetime, timezone
from typing import Optional

from ssir.domain_rules import IdentityDirectory
from ssir.earth.earth_store import EarthStore
from ssir.earth.gateway import EarthGateway, Handler, Operation
from ssir.earth.inventory_service import InventoryService
from ssir.earth.mission_service import MissionService
from ssir.earth.sync_endpoint import SyncEndpoint
from ssir.screens import EarthScreens


def _name(directory: IdentityDirectory, user_id: Optional[str]) -> str:
    """A user's name from the identity system, for display only."""
    if user_id is None:
        return "unknown"
    try:
        return directory.get_user(user_id).name
    except Exception:
        return user_id


def _register_handlers(handlers: dict[Operation, Handler], gateway: EarthGateway,
                       inventory: InventoryService, missions: MissionService,
                       directory: IdentityDirectory) -> None:
    """Map each Earth Operation to the service call that serves it (contracts gap 1).
    Wiring only: no rules."""
    handlers[Operation.LINK_STATUS] = lambda user, payload: gateway.link_status()
    handlers[Operation.DASHBOARD] = gateway.dashboard
    handlers[Operation.SEARCH_ITEMS] = lambda user, p: inventory.search_items(p["query"], p["filter"])
    handlers[Operation.GET_ITEM] = lambda user, p: {"item": inventory.get_item(p["item_id"]),
                                                    "locations": inventory.list_locations()}
    def item_history(user, p):
        updates = inventory.item_history(p["item_id"])
        return {"item": inventory.get_item(p["item_id"]), "updates": updates,
                "locations": inventory.list_locations(),
                "users": {u.display_id: _name(directory, u.recorded_by) for u in updates}}
    handlers[Operation.ITEM_HISTORY] = item_history
    handlers[Operation.CREATE_MISSION] = lambda user, p: missions.create_mission(
        user, p["mass_capacity_kg"], p["volume_capacity_m3"])
    handlers[Operation.SAVE_MANIFEST] = lambda user, p: missions.save_manifest(
        user, p["mission_id"], p["base_version"], p["draft"])
    handlers[Operation.GET_MANIFEST] = lambda user, p: missions.get_manifest(
        p["mission_id"], p.get("version"))
    handlers[Operation.MANIFEST_EDITOR] = lambda user, p: missions.manifest_editor(p["mission_id"])
    handlers[Operation.SUBMIT_MISSION] = lambda user, p: missions.submit(user, p["mission_id"])
    handlers[Operation.APPROVE_MISSION] = lambda user, p: missions.approve(user, p["mission_id"])
    handlers[Operation.RETURN_MISSION] = lambda user, p: missions.return_to_draft(
        user, p["mission_id"], p["reason"])
    handlers[Operation.REOPEN_MISSION] = lambda user, p: missions.reopen(user, p["mission_id"], p["reason"])
    handlers[Operation.CANCEL_MISSION] = lambda user, p: missions.cancel(user, p["mission_id"], p["reason"])
    handlers[Operation.CONFIRM_DISPATCH] = lambda user, p: missions.confirm_dispatch(user, p["mission_id"])
    handlers[Operation.RECORD_LOADED_QUANTITY] = lambda user, p: missions.record_loaded_quantity(
        user, p["mission_id"], p["item_id"], p["loaded_quantity"])
    handlers[Operation.ADD_LOADING_ISSUE] = lambda user, p: missions.add_loading_issue(
        user, p["mission_id"], p["text"])
    handlers[Operation.LOADING_REVIEW] = lambda user, p: {
        "review": missions.loading_review(p["mission_id"]),
        "issues": missions.list_loading_issues(p["mission_id"])}
    handlers[Operation.LIST_MISSIONS] = lambda user, p: missions.list_missions()

    def get_mission(user, p):
        mission = missions.get_mission(p["mission_id"])
        return {"mission": mission,
                "users": {e.user_id: _name(directory, e.user_id) for e in mission.status_history}}
    handlers[Operation.GET_MISSION] = get_mission
    handlers[Operation.CREATE_ITEM] = lambda user, p: inventory.create_item(user, p["item"])
    handlers[Operation.EDIT_ITEM] = lambda user, p: inventory.edit_item(
        user, p["item_id"], p["edit"], p["expected_version"])
    handlers[Operation.CREATE_LOCATION] = lambda user, p: inventory.create_location(
        user, p["location_id"], p["name"])
    handlers[Operation.CORRECT_ITEM] = lambda user, p: inventory.correct_item(
        user, p["item_id"], p["field"], p["value"], p["reason"], p["expected_version"])


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m ssir.earth")
    parser.add_argument("--dsn", required=True, help="Earth Store connection string")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8443)
    args = parser.parse_args()

    def now() -> datetime:
        return datetime.now(timezone.utc)

    directory: IdentityDirectory = NotImplemented  # external identity system
    store = EarthStore(args.dsn)
    inventory = InventoryService(store, now)
    missions = MissionService(store, inventory, now)
    endpoint = SyncEndpoint(store, inventory, missions, directory, now)
    handlers: dict[Operation, Handler] = {}       # Operation -> service method, filled when implemented
    gateway = EarthGateway(store, directory,
                           station_credential_check=lambda credential: False,
                           handlers=handlers,
                           station_handler=lambda call, message: getattr(endpoint, call)(message),
                           now=now)
    _register_handlers(handlers, gateway, inventory, missions, directory)
    screens = EarthScreens(gateway)

    stop = threading.Event()
    store.open()
    screens.serve(args.host, args.port, stop)


if __name__ == "__main__":
    main()
