"""Earth Gateway: authenticate every caller and reject actions the caller's
role does not allow (FR-003, NFR-003, K11, K14, K21)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Callable, Mapping

from ssir.domain_rules import (
    RECENT_ACTIVITY_WINDOW, Action, Forbidden, IdentityDirectory, LinkStatus, Role, User,
    earth_link_available, require_permission,
)
from ssir.earth.earth_store import EarthStore


class Operation(Enum):
    """Every request an Earth screen can send, with the Action it is checked as."""
    # reads (Action.VIEW)
    DASHBOARD = "dashboard"
    SEARCH_ITEMS = "search items"
    GET_ITEM = "get item"
    ITEM_HISTORY = "item history"
    LIST_MISSIONS = "list missions"
    GET_MISSION = "get mission"
    GET_MANIFEST = "get manifest"
    MANIFEST_EDITOR = "manifest editor"
    LOADING_REVIEW = "loading review"
    LIST_DISCREPANCIES = "list discrepancies"
    LIST_CONFLICTS = "list conflicts"
    LINK_STATUS = "link status"
    # writes
    CORRECT_ITEM = "correct item"
    CREATE_ITEM = "create item"
    EDIT_ITEM = "edit item"
    CREATE_LOCATION = "create location"
    CREATE_MISSION = "create mission"
    SAVE_MANIFEST = "save manifest"
    SUBMIT_MISSION = "submit mission"
    APPROVE_MISSION = "approve mission"
    RETURN_MISSION = "return mission"
    REOPEN_MISSION = "reopen mission"
    CANCEL_MISSION = "cancel mission"
    RECORD_LOADED_QUANTITY = "record loaded quantity"
    ADD_LOADING_ISSUE = "add loading issue"
    CONFIRM_DISPATCH = "confirm dispatch"
    RESOLVE_DISCREPANCY = "resolve discrepancy"
    RESOLVE_CONFLICT = "resolve conflict"


# The Action each Operation is checked as (FR-003). Reads are VIEW.
OPERATION_ACTIONS: Mapping[Operation, Action] = {
    Operation.DASHBOARD: Action.VIEW,
    Operation.SEARCH_ITEMS: Action.VIEW,
    Operation.GET_ITEM: Action.VIEW,
    Operation.ITEM_HISTORY: Action.VIEW,
    Operation.LIST_MISSIONS: Action.VIEW,
    Operation.GET_MISSION: Action.VIEW,
    Operation.GET_MANIFEST: Action.VIEW,
    Operation.MANIFEST_EDITOR: Action.VIEW,
    Operation.LOADING_REVIEW: Action.VIEW,
    Operation.LIST_DISCREPANCIES: Action.VIEW,
    Operation.LIST_CONFLICTS: Action.VIEW,
    Operation.LINK_STATUS: Action.VIEW,
    Operation.CORRECT_ITEM: Action.CORRECT_ITEM,
    Operation.CREATE_ITEM: Action.CREATE_ITEM,
    Operation.EDIT_ITEM: Action.EDIT_ITEM,
    Operation.CREATE_LOCATION: Action.CREATE_LOCATION,
    Operation.CREATE_MISSION: Action.CREATE_MISSION,
    Operation.SAVE_MANIFEST: Action.SAVE_MANIFEST,
    Operation.SUBMIT_MISSION: Action.SUBMIT_MISSION,
    Operation.APPROVE_MISSION: Action.APPROVE_MISSION,
    Operation.RETURN_MISSION: Action.RETURN_MISSION,
    Operation.REOPEN_MISSION: Action.REOPEN_MISSION,
    Operation.CANCEL_MISSION: Action.CANCEL_MISSION,
    Operation.RECORD_LOADED_QUANTITY: Action.RECORD_LOADING,
    Operation.ADD_LOADING_ISSUE: Action.RECORD_LOADING,
    Operation.CONFIRM_DISPATCH: Action.CONFIRM_DISPATCH,
    Operation.RESOLVE_DISCREPANCY: Action.RESOLVE_DISCREPANCY,
    Operation.RESOLVE_CONFLICT: Action.RESOLVE_CONFLICT,
}

# Decision (Nov 16, 2026): station crew changes reach Earth only as signed
# station updates through the sync channel (NFR-003), so on the Earth
# Gateway these roles may only view.
_VIEW_ONLY_ON_EARTH = frozenset({Role.STATION_CREW})

Handler = Callable[[User, Mapping[str, object]], object]
StationHandler = Callable[[str, object], object]


class EarthGateway:
    def __init__(self, store: EarthStore, directory: IdentityDirectory,
                 station_credential_check: Callable[[bytes], bool],
                 handlers: Mapping[Operation, Handler],
                 station_handler: StationHandler,
                 now: Callable[[], datetime]) -> None:
        self._store = store
        self._directory = directory
        self._station_credential_check = station_credential_check
        self._handlers = handlers
        self._station_handler = station_handler
        self._now = now

    def authenticate_user(self, token: str) -> User:
        return self._directory.authenticate(token)

    def authorize(self, user: User, operation: Operation) -> Action:
        action = OPERATION_ACTIONS[operation]
        if user.role in _VIEW_ONLY_ON_EARTH and action is not Action.VIEW:
            raise Forbidden([f"{user.role.value} changes reach Earth only through station sync"])
        require_permission(user, action)
        return action

    def handle(self, token: str, operation: Operation,
               payload: Mapping[str, object]) -> object:
        user = self.authenticate_user(token)
        self.authorize(user, operation)
        return self._handlers[operation](user, payload)

    def handle_station(self, credential: bytes, call: str, message: object) -> object:
        raise NotImplementedError

    def dashboard(self, user: User, payload: Mapping[str, object]) -> Mapping[str, object]:
        """Addition (Nov 16, 2026, not in contracts.md; Design question 3): the
        DASHBOARD handler. Reads what Earth S1 needs in one transaction:
        items, active alerts, missions, recent events (raw, 7-day window from
        the Earth clock), and the pending count the station last reported."""
        now = self._now()
        with self._store.transaction() as tx:
            return {
                "now": now,
                "items": tx.list_items(),
                "alerts": tx.list_active_alerts(),
                "missions": tx.list_missions(),
                "events": tx.recent_events(now - RECENT_ACTIVITY_WINDOW),
                "pending": tx.reported_pending_count(),
            }

    def link_status(self) -> LinkStatus:
        with self._store.transaction() as tx:
            session_open = tx.session_open()
            last_contact = tx.last_station_contact()
            last_full_sync = tx.last_full_sync()
        return LinkStatus(available=earth_link_available(session_open, last_contact, self._now()),
                          last_full_sync=last_full_sync)
