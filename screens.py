"""Screens: render S1–S7 and send user actions to the local site (FR-001–FR-028,
FR-002 banner, FR-003 control hiding, FR-032 escaping).

StationScreens runs against the onboard host; EarthScreens runs against the
Earth Gateway. Both render the same seven screens as HTML strings.
"""
from __future__ import annotations

import html
import threading
from enum import Enum
from typing import TYPE_CHECKING, Mapping, Optional

from ssir.domain_rules import (
    Action, InventoryFilter, InvalidTransition, MissionStatus, ResupplyMission,
    Transition, User, _quantity_text, filter_items, is_permitted, next_status,
    today_utc,
)

if TYPE_CHECKING:
    from ssir.earth.gateway import EarthGateway
    from ssir.station.clock import StationClock
    from ssir.station.command_handler import StationCommandHandler
    from ssir.station.identity import Session
    from ssir.station.onboard_store import OnboardStore


class Screen(Enum):
    S1_DASHBOARD = "S1 Dashboard"
    S2_INVENTORY = "S2 Inventory"
    S3_ITEM_DETAILS = "S3 Item details"
    S4_RESUPPLY_PLAN = "S4 Resupply plan"
    S5_CARGO_MANIFEST = "S5 Cargo manifest"
    S6_MISSION_STATUS = "S6 Mission status"
    S7_SYNC = "S7 Sync"


def escape(text: str) -> str:
    return html.escape(text, quote=True)


# Decision (Nov 16, 2026): which controls each screen carries. The spec does
# not place controls on screens; this table is derived from the screen names,
# the FR wording and the contracts' screen descriptions. VIEW is not a control.
_SCREEN_ACTIONS: dict[Screen, frozenset[Action]] = {
    Screen.S1_DASHBOARD: frozenset(),
    Screen.S2_INVENTORY: frozenset({Action.CREATE_ITEM, Action.CREATE_LOCATION}),
    Screen.S3_ITEM_DETAILS: frozenset({
        Action.RECORD_USAGE, Action.MOVE_ITEM, Action.SET_CONDITION,
        Action.CORRECT_ITEM, Action.EDIT_ITEM}),
    Screen.S4_RESUPPLY_PLAN: frozenset({
        Action.CREATE_MISSION, Action.SAVE_MANIFEST, Action.SUBMIT_MISSION}),
    Screen.S5_CARGO_MANIFEST: frozenset({Action.RECORD_LOADING, Action.RECORD_RECEIPT}),
    Screen.S6_MISSION_STATUS: frozenset({
        Action.APPROVE_MISSION, Action.RETURN_MISSION, Action.REOPEN_MISSION,
        Action.CANCEL_MISSION, Action.CONFIRM_DISPATCH, Action.RECORD_RECEIPT,
        Action.RESOLVE_DISCREPANCY}),
    Screen.S7_SYNC: frozenset({Action.RESOLVE_CONFLICT, Action.SYNC_NOW}),
}

# Mission actions that are lifecycle transitions: allowed when the state
# machine (Domain Rules next_status) allows the transition from the status.
_TRANSITION_OF: dict[Action, Transition] = {
    Action.SUBMIT_MISSION: Transition.SUBMIT,
    Action.APPROVE_MISSION: Transition.APPROVE,
    Action.RETURN_MISSION: Transition.RETURN,
    Action.REOPEN_MISSION: Transition.REOPEN,
    Action.CANCEL_MISSION: Transition.CANCEL,
    Action.CONFIRM_DISPATCH: Transition.CONFIRM_DISPATCH,
    Action.RECORD_RECEIPT: Transition.RECORD_RECEIPT,
}

# Mission actions that are not transitions, with the statuses the spec allows:
# lines in Draft and expected arrival also in Approved (Lifecycle, FR-016);
# loading on an approved mission (FR-022). Discrepancies are resolved whatever
# the mission status (FR-026).
_STATUSES_OF: dict[Action, frozenset[MissionStatus]] = {
    Action.SAVE_MANIFEST: frozenset({MissionStatus.DRAFT, MissionStatus.APPROVED}),
    Action.RECORD_LOADING: frozenset({MissionStatus.APPROVED}),
    Action.RESOLVE_DISCREPANCY: frozenset(MissionStatus),
}


def _allowed_by_status(action: Action, mission: Optional[ResupplyMission]) -> bool:
    if action in _TRANSITION_OF:
        if mission is None:
            return False
        try:
            next_status(mission.mission_status, _TRANSITION_OF[action])
        except InvalidTransition:
            return False
        return True
    if action in _STATUSES_OF:
        return mission is not None and mission.mission_status in _STATUSES_OF[action]
    return True


def visible_controls(user: User, screen: Screen,
                     mission: Optional[ResupplyMission] = None) -> frozenset[Action]:
    return frozenset(
        action for action in _SCREEN_ACTIONS[screen]
        if is_permitted(user, action) and _allowed_by_status(action, mission))


class StationScreens:
    def __init__(self, handler: StationCommandHandler, store: OnboardStore,
                 clock: StationClock) -> None:
        self._handler = handler
        self._store = store
        self._clock = clock

    def sign_in(self, user_id: str, secret: str) -> Session:
        raise NotImplementedError

    def banner(self) -> str:
        raise NotImplementedError

    def dashboard(self, session: Session) -> str:
        # Slice 1: pending count only. Alerts, next mission, recent activity,
        # banner and navigation are added by later slices (plan.md).
        with self._store.read() as tx:
            pending = tx.pending_count()
        # Decision (Nov 16, 2026): one template for every count.
        return (f"<main><h1>{escape(Screen.S1_DASHBOARD.value)}</h1>"
                f"<p>{escape(f'{pending} pending updates')}</p></main>")

    def inventory(self, session: Session, query: str, item_filter: InventoryFilter) -> str:
        today = today_utc(self._clock.now())
        with self._store.read() as tx:
            items = filter_items(tx.list_items(), query, item_filter, today)
        # Decision (Nov 16, 2026): sorted by name, case-insensitive; ID breaks ties.
        items.sort(key=lambda item: (item.name.casefold(), item.item_id))
        rows = "".join(
            f"<tr><td>{escape(item.item_id)}</td><td>{escape(item.name)}</td>"
            f"<td>{escape(_quantity_text(item.quantity, item.unit))}</td></tr>"
            for item in items)
        return (f"<main><h1>{escape(Screen.S2_INVENTORY.value)}</h1>"
                f"<p>{escape(f'Search: {query}')} &middot; {escape(f'Filter: {item_filter.value}')}</p>"
                f"<table>{rows}</table></main>")

    def item_details(self, session: Session, item_id: str) -> str:
        raise NotImplementedError

    def item_history(self, session: Session, item_id: str) -> str:
        raise NotImplementedError

    def resupply_plan(self, session: Session, mission_id: Optional[str]) -> str:
        raise NotImplementedError

    def cargo_manifest(self, session: Session, mission_id: str,
                       version: Optional[int] = None) -> str:
        raise NotImplementedError

    def mission_status(self, session: Session, mission_id: str) -> str:
        raise NotImplementedError

    def sync(self, session: Session, page: int = 0) -> str:
        raise NotImplementedError

    def submit_action(self, session: Session, action: Action,
                      form: Mapping[str, str]) -> str:
        raise NotImplementedError

    def serve(self, host: str, port: int, stop: threading.Event) -> None:
        raise NotImplementedError


class EarthScreens:
    def __init__(self, gateway: EarthGateway) -> None:
        self._gateway = gateway

    def banner(self, token: str) -> str:
        raise NotImplementedError

    def dashboard(self, token: str) -> str:
        raise NotImplementedError

    def inventory(self, token: str, query: str, item_filter: InventoryFilter) -> str:
        raise NotImplementedError

    def item_details(self, token: str, item_id: str) -> str:
        raise NotImplementedError

    def item_history(self, token: str, item_id: str) -> str:
        raise NotImplementedError

    def resupply_plan(self, token: str, mission_id: Optional[str]) -> str:
        raise NotImplementedError

    def cargo_manifest(self, token: str, mission_id: str,
                       version: Optional[int] = None) -> str:
        raise NotImplementedError

    def mission_status(self, token: str, mission_id: str) -> str:
        raise NotImplementedError

    def sync(self, token: str) -> str:
        raise NotImplementedError

    def submit_action(self, token: str, action: Action, form: Mapping[str, str]) -> str:
        raise NotImplementedError

    def serve(self, host: str, port: int, stop: threading.Event) -> None:
        raise NotImplementedError
