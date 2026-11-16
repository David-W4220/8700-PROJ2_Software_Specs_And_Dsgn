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

from ssir.domain_rules import Action, InventoryFilter, ResupplyMission, User

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


def visible_controls(user: User, screen: Screen,
                     mission: Optional[ResupplyMission] = None) -> frozenset[Action]:
    raise NotImplementedError


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
        raise NotImplementedError

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
