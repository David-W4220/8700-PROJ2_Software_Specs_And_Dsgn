"""Screens: render S1–S7 and send user actions to the local site (FR-001–FR-028,
FR-002 banner, FR-003 control hiding, FR-032 escaping).

StationScreens runs against the onboard host; EarthScreens runs against the
Earth Gateway. Both render the same seven screens as HTML strings.
"""
from __future__ import annotations

import html
import threading
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Mapping, Optional, Sequence

from ssir.domain_rules import (
    RECENT_ACTIVITY_WINDOW, Action, ActivityEvent, CorrectionField, Criticality, DomainError,
    ManifestDraft, ManifestLine, Unit, ValidationError, InventoryFilter, InventoryItem,
    InvalidTransition, LinkStatus, MissionStatus, ResupplyMission, SupplyAlert,
    StorageLocation, Transition, User, _quantity_text, alert_text, earth_link_available, filter_items,
    InventoryUpdate, _change_text, format_utc, is_permitted, next_mission, next_status,
    REJECTED_LISTED_FOR, order_alerts, order_history, rejected_still_listed,
    recent_activity, today_utc,
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


def _decimal(value: Optional[str]) -> Decimal:
    """A form number as Decimal; anything else is a validation failure."""
    try:
        number = Decimal((value or "").strip())
    except InvalidOperation:
        raise ValidationError(["amount must be a number"]) from None
    if not number.is_finite():
        raise ValidationError(["amount must be a number"])
    return number


def _date(value: Optional[str]) -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        raise ValidationError(["date must be YYYY-MM-DD"]) from None


def _correction_field(value: str) -> CorrectionField:
    for field in CorrectionField:
        if value == field.value:
            return field
    raise ValidationError(["field must be quantity or expiryDate"])


def _int(value: Optional[str]) -> int:
    try:
        return int((value or "").strip())
    except ValueError:
        raise ValidationError(["version must be a whole number"]) from None


def _optional_decimal(form: Mapping[str, str], key: str) -> Optional[Decimal]:
    return _decimal(form[key]) if (form.get(key) or "").strip() else None


def _barcodes(value: Optional[str]) -> tuple[str, ...]:
    return tuple(code.strip() for code in (value or "").split(",") if code.strip())


def _criticality(value: Optional[str]) -> Criticality:
    for criticality in Criticality:
        if value == criticality.value:
            return criticality
    raise ValidationError(["criticality must be Critical or Standard"])


def _new_item(form: Mapping[str, str]):
    """Planner form for FR-010. Decision (Nov 16, 2026, Claude): the unit is
    given by name plus a countable flag ("true"/"false"); the spec keeps no unit list."""
    from ssir.earth.inventory_service import NewItem
    expiry = form.get("expiry_date") or ""
    return NewItem(
        item_id=form.get("item_id", ""), name=form.get("name", ""),
        barcodes=_barcodes(form.get("barcodes")), quantity=_decimal(form.get("quantity")),
        unit=Unit(form.get("unit", "").strip(), form.get("countable", "true") == "true"),
        expiry_date=_date(expiry) if expiry.strip() else None,
        unit_mass_kg=_decimal(form.get("unit_mass_kg")),
        unit_volume_m3=_decimal(form.get("unit_volume_m3")),
        minimum_quantity=_decimal(form.get("minimum_quantity")),
        criticality=_criticality(form.get("criticality")), stored_at=form.get("stored_at", ""))


def _item_edit(form: Mapping[str, str]):
    from ssir.earth.inventory_service import ItemEdit
    return ItemEdit(
        name=form.get("name") or None,
        barcodes=_barcodes(form["barcodes"]) if "barcodes" in form else None,
        minimum_quantity=_optional_decimal(form, "minimum_quantity"),
        criticality=_criticality(form["criticality"]) if form.get("criticality") else None,
        unit_mass_kg=_optional_decimal(form, "unit_mass_kg"),
        unit_volume_m3=_optional_decimal(form, "unit_volume_m3"))


def _lines(value: Optional[str]) -> tuple[ManifestLine, ...]:
    """Form lines as "W01:20,F01:40"."""
    lines = []
    for part in (value or "").split(","):
        if not part.strip():
            continue
        item_id, _, quantity = part.partition(":")
        lines.append(ManifestLine(item_id.strip(), _decimal(quantity), None, None))
    return tuple(lines)


def _moment(value: Optional[str]) -> Optional[datetime]:
    """An ISO date-time; times without an offset are UTC (Description)."""
    if not (value or "").strip():
        return None
    try:
        moment = datetime.fromisoformat(value.strip())
    except ValueError:
        raise ValidationError(["time must be YYYY-MM-DD HH:MM"]) from None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _unlisted(value: Optional[str]) -> tuple:
    """Unlisted delivered items as "Spare filter:1,Gasket:2" (FR-026)."""
    from ssir.domain_rules import UnlistedItem
    entries = []
    for part in (value or "").split(","):
        if part.strip():
            text, _, quantity = part.rpartition(":")
            entries.append(UnlistedItem(text.strip(), _decimal(quantity)))
    return tuple(entries)


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


def _banner(link_name: str, status: LinkStatus, now: datetime) -> str:
    """FR-002 banner. Decision (Nov 16, 2026): "Last sync never" before the
    first fully completed synchronization."""
    link = f"{link_name} {'available' if status.available else 'unavailable'}"
    last = ("Last sync never" if status.last_full_sync is None
            else f"Last sync {format_utc(status.last_full_sync, now)}")
    return f'<div class="banner"><span>{escape(link)}</span> <span>{escape(last)}</span></div>'


def _dashboard(banner: str, items: list[InventoryItem], alerts: list[SupplyAlert],
               missions: list[ResupplyMission], pending: int,
               events: list[ActivityEvent], now: datetime) -> str:
    """S1 body shared by both sites (FR-001)."""
    by_id = {item.item_id: item for item in items}
    alert_rows = "".join(f"<li>{escape(alert_text(by_id[a.item_id]))}</li>"
                         for a in order_alerts(alerts, by_id))
    upcoming = next_mission(missions)
    mission_line = ("No upcoming mission" if upcoming is None
                    else f"Mission {upcoming.mission_id} \u2013 {upcoming.mission_status.value}")
    activity_rows = "".join(
        f"<li><time>{escape(format_utc(e.time, now))}</time> {escape(e.description)}</li>"
        for e in recent_activity(events, now))
    return (f"<main>{banner}<h1>{escape(Screen.S1_DASHBOARD.value)}</h1>"
            f"<h2>Supply alerts</h2><ul>{alert_rows}</ul>"
            f"<h2>Next mission</h2><p>{escape(mission_line)}</p>"
            # Decision (Nov 16, 2026): one template for every count.
            f"<p>{escape(f'{pending} pending updates')}</p>"
            f"<h2>Recent activity</h2><ul>{activity_rows}</ul></main>")


def _item_rows(items: list[InventoryItem]) -> str:
    return "".join(
        f"<tr><td>{escape(item.item_id)}</td><td>{escape(item.name)}</td>"
        f"<td>{escape(_quantity_text(item.quantity, item.unit))}</td></tr>" for item in items)


def _inventory(banner: str, items: list[InventoryItem], query: str,
               item_filter: InventoryFilter) -> str:
    """S2 body shared by both sites (FR-004)."""
    return (f"<main>{banner}<h1>{escape(Screen.S2_INVENTORY.value)}</h1>"
            f"<p>{escape(f'Search: {query}')} &middot; {escape(f'Filter: {item_filter.value}')}</p>"
            f"<table>{_item_rows(items)}</table></main>")


def _item_details(banner: str, item: InventoryItem, locations: list[StorageLocation]) -> str:
    """S3 body shared by both sites: every FR-005 field."""
    names = {loc.location_id: loc.name for loc in locations}
    fields = [
        ("ID", item.item_id),
        ("Name", item.name),
        ("Quantity", _quantity_text(item.quantity, item.unit)),
        ("Minimum", _quantity_text(item.minimum_quantity, item.unit)),
        ("Unit mass", f"{item.unit_mass_kg:f} kg"),
        ("Unit volume", f"{item.unit_volume_m3:f} m3"),
        ("Location", names.get(item.stored_at, item.stored_at)),
        ("Condition", item.condition.value),
        ("Expiry date", item.expiry_date.isoformat() if item.expiry_date else "none"),
        ("Criticality", item.criticality.value),
    ]
    rows = "".join(f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in fields)
    return (f"<main>{banner}<h1>{escape(Screen.S3_ITEM_DETAILS.value)}</h1>"
            f"<table>{rows}</table><p>{escape('Back to inventory')}</p></main>")


def _history(banner: str, item: InventoryItem, updates: list[InventoryUpdate],
             users: Mapping[str, str], locations: list[StorageLocation], now: datetime) -> str:
    """S3 change history (FR-011): display ID, change, event time, user, sync status.
    `users` maps the update's display ID to the recorder's name."""
    names = {loc.location_id: loc.name for loc in locations}
    rows = "".join(
        f"<tr><td>{escape(u.display_id)}</td><td>{escape(_change_text(u, item, names))}</td>"
        f"<td>{escape(format_utc(u.event_time, now))}</td>"
        f"<td>{escape(users.get(u.display_id, 'unknown'))}</td>"
        f"<td>{escape(u.sync_status.value)}</td></tr>" for u in updates)
    return (f"<main>{banner}<h1>{escape(f'{item.name} change history')}</h1>"
            f"<table>{rows}</table></main>")


def _total(value: Decimal, capacity: Decimal, unit: str, over: bool) -> str:
    """'30.00 kg / 500 kg', shown in red when over capacity (FR-015)."""
    text = escape(f"{value:f} {unit} / {capacity:f} {unit}")
    return f'<span class="over" style="color:red">{text}</span>' if over else f"<span>{text}</span>"


def _resupply_plan(banner: str, mission: ResupplyMission, version: int,
                   lines: Sequence[ManifestLine], totals, coverage: Sequence,
                   controls: frozenset) -> str:
    """S4 manifest editor (FR-013, FR-015); `coverage` is AlertCoverage entries."""
    rows = "".join(f"<tr><td>{escape(line.item_id)}</td><td>{escape(f'{line.line_quantity:f}')}</td></tr>"
                   for line in lines)
    alerts = "".join(f"<li>{escape(c.alert.item_id)}: {escape(c.coverage.value)}</li>" for c in coverage)
    buttons = "".join(f"<p>{escape(a.value)}</p>" for a in sorted(controls, key=lambda a: a.value))
    return (f"<main>{banner}<h1>{escape(f'Mission {mission.mission_id} \u2013 {mission.mission_status.value}')}</h1>"
            f"<p>{escape(f'Manifest version {version}')}</p><table>{rows}</table>"
            f"<p>{_total(totals.mass_kg, totals.mass_capacity_kg, 'kg', totals.over_mass)}</p>"
            f"<p>{_total(totals.volume_m3, totals.volume_capacity_m3, 'm3', totals.over_volume)}</p>"
            f"<h2>Supply alerts</h2><ul>{alerts}</ul>{buttons}</main>")


def _mission_status(banner: str, mission: ResupplyMission, users: Mapping[str, str],
                    controls: frozenset, now: datetime) -> str:
    """S6 (FR-024): status, expected arrival, manifest version, status history."""
    arrival = (format_utc(mission.expected_arrival, now) if mission.expected_arrival
               else "not set")
    path = " > ".join(entry.status.value for entry in mission.status_history)
    steps = "".join(
        f"<li>{escape(e.status.value)} {escape(format_utc(e.time, now))} "
        f"{escape(users.get(e.user_id, e.user_id))}"
        + (f" \u2013 {escape(e.reason)}" if e.reason else "") + "</li>"
        for e in mission.status_history)
    buttons = "".join(f"<p>{escape(a.value)}</p>" for a in sorted(controls, key=lambda a: a.value))
    return (f"<main>{banner}<h1>{escape(f'Mission {mission.mission_id}')}</h1>"
            f"<p>{escape(f'Status {mission.mission_status.value}')}</p>"
            f"<p>{escape(f'Expected arrival {arrival}')}</p>"
            f"<p>{escape(f'Manifest version {mission.manifest_version}')}</p>"
            f"<p>{escape(path)}</p><ul>{steps}</ul>"
            f"<p>{escape('Open cargo manifest')}</p>{buttons}</main>")


def _cargo_manifest(banner: str, mission_id: str, version: int, latest: bool,
                    lines: Sequence[ManifestLine], issues: Sequence, now: datetime) -> str:
    """S5 (FR-016, FR-022): the lines of one version, with the loading review."""
    from ssir.domain_rules import loading_review
    rows = "".join(
        f"<tr><td>{escape(r.item_id)}</td><td>{escape(f'Planned {r.planned:f}, Loaded '+ (f'{r.loaded:f}' if r.loaded is not None else '-') + f', Missing {r.missing:f}')}</td></tr>"
        for r in loading_review(lines))
    notes = "".join(f"<li>{escape(format_utc(i.time, now))} {escape(i.recorded_by)}: {escape(i.text)}</li>"
                    for i in issues)
    label = f"Manifest version {version}" + ("" if latest else " (read-only)")
    return (f"<main>{banner}<h1>{escape(f'Mission {mission_id} cargo manifest')}</h1>"
            f"<p>{escape(label)}</p><table>{rows}</table><h2>Loading issues</h2><ul>{notes}</ul></main>")


# Mission transitions sent from Earth screens: Operation name, reason required.
_TRANSITION_OPERATIONS = {
    Action.SUBMIT_MISSION: ("SUBMIT_MISSION", False),
    Action.APPROVE_MISSION: ("APPROVE_MISSION", False),
    Action.RETURN_MISSION: ("RETURN_MISSION", True),
    Action.REOPEN_MISSION: ("REOPEN_MISSION", True),
    Action.CANCEL_MISSION: ("CANCEL_MISSION", True),
    Action.CONFIRM_DISPATCH: ("CONFIRM_DISPATCH", False),
}


class StationScreens:
    def __init__(self, handler: StationCommandHandler, store: OnboardStore,
                 clock: StationClock) -> None:
        self._handler = handler
        self._store = store
        self._clock = clock

    def sign_in(self, user_id: str, secret: str) -> Session:
        return self._handler.sign_in(user_id, secret)

    def banner(self) -> str:
        now = self._clock.now()
        with self._store.read() as tx:
            last_contact = tx.last_earth_contact()
            last_full_sync = tx.last_full_sync()
        # Decision (Nov 16, 2026): the station uses Earth's rule, contact within 60 s.
        status = LinkStatus(available=earth_link_available(False, last_contact, now),
                            last_full_sync=last_full_sync)
        banner = _banner("Earth link", status, now)
        if self._clock.drift_warning():                 # NFR-005: warn the crew
            banner = banner.replace("</div>", f"<span>{escape('Clock may be more than 30 s off; sync to correct it')}</span></div>")
        return banner

    def dashboard(self, session: Session) -> str:
        now = self._clock.now()
        with self._store.read() as tx:
            items = tx.list_items()
            alerts = tx.list_active_alerts()
            missions = tx.list_missions()
            pending = tx.pending_count()
            events = tx.recent_events(now - RECENT_ACTIVITY_WINDOW)
        return _dashboard(self.banner(), items, alerts, missions, pending, events, now)

    def inventory(self, session: Session, query: str, item_filter: InventoryFilter) -> str:
        today = today_utc(self._clock.now())
        with self._store.read() as tx:
            items = filter_items(tx.list_items(), query, item_filter, today)
        # Decision (Nov 16, 2026): sorted by name, case-insensitive; ID breaks ties.
        items.sort(key=lambda item: (item.name.casefold(), item.item_id))
        return _inventory(self.banner(), items, query, item_filter)

    def item_details(self, session: Session, item_id: str) -> str:
        with self._store.read() as tx:
            item = tx.get_item(item_id)
            locations = tx.list_locations()
        return _item_details(self.banner(), item, locations)

    def item_history(self, session: Session, item_id: str) -> str:
        now = self._clock.now()
        with self._store.read() as tx:
            item = tx.get_item(item_id)
            updates = order_history(tx.item_history(item_id))
            locations = tx.list_locations()
            people = {}
            for update in updates:
                people[update.display_id] = self._recorder_name(tx, update)
        return _history(self.banner(), item, updates, people, locations, now)

    @staticmethod
    def _recorder_name(tx, update: InventoryUpdate) -> str:
        if update.recorded_by is None:
            return "unknown"
        try:
            return tx.get_user(update.recorded_by).name
        except DomainError:
            return update.recorded_by

    def resupply_plan(self, session: Session, mission_id: Optional[str]) -> str:
        """S4 on the station is read-only: planning happens on Earth."""
        from ssir.domain_rules import AlertCoverage, alert_coverage, manifest_totals
        if mission_id is None:
            return f"<main>{self.banner()}<h1>{escape(Screen.S4_RESUPPLY_PLAN.value)}</h1></main>"
        with self._store.read() as tx:
            mission = tx.get_mission(mission_id)
            draft = tx.get_manifest(mission_id)
            items = {item.item_id: item for item in tx.list_items()}
            alerts = tx.list_active_alerts()
        planned = {line.item_id: line.line_quantity for line in draft.lines}
        coverage = [AlertCoverage(a, alert_coverage(items[a.item_id], planned.get(a.item_id)))
                    for a in alerts if a.item_id in items]
        totals = manifest_totals(draft.lines, items, draft.mass_capacity_kg, draft.volume_capacity_m3)
        return _resupply_plan(self.banner(), mission, mission.manifest_version, draft.lines, totals,
                              coverage, frozenset())

    def cargo_manifest(self, session: Session, mission_id: str,
                       version: Optional[int] = None) -> str:
        with self._store.read() as tx:
            mission = tx.get_mission(mission_id)
            draft = tx.get_manifest(mission_id, version)
        shown = version or mission.manifest_version
        controls = visible_controls(session.user, Screen.S5_CARGO_MANIFEST, mission)
        page = _cargo_manifest(self.banner(), mission_id, shown, shown == mission.manifest_version,
                               draft.lines, (), self._clock.now())
        if Action.RECORD_RECEIPT in controls:
            page = page.replace("</main>", f"<p>{escape('Record receipt')}</p></main>")
        return page

    def mission_status(self, session: Session, mission_id: str) -> str:
        with self._store.read() as tx:
            mission = tx.get_mission(mission_id)
            users = {}
            for entry in mission.status_history:
                try:
                    users[entry.user_id] = tx.get_user(entry.user_id).name
                except DomainError:
                    users[entry.user_id] = entry.user_id
        return _mission_status(self.banner(), mission, users,
                               visible_controls(session.user, Screen.S6_MISSION_STATUS, mission),
                               self._clock.now())

    # Decision (Nov 16, 2026, Claude): S7 shows 50 pending units per page (K8).
    SYNC_PAGE_SIZE = 50

    def sync(self, session: Session, page: int = 0) -> str:
        now = self._clock.now()
        with self._store.read() as tx:
            count = tx.pending_count()
            pending = tx.pending_page(page * self.SYNC_PAGE_SIZE, self.SYNC_PAGE_SIZE)
            rejected = [u for u in tx.rejected_since(now - REJECTED_LISTED_FOR)
                        if rejected_still_listed(u.rejected_at, now)]
            items = {item.item_id: item for item in tx.list_items()}
            names = {loc.location_id: loc.name for loc in tx.list_locations()}
            link = earth_link_available(False, tx.last_earth_contact(), now)

        def row(u: InventoryUpdate) -> str:
            item = items.get(u.item_id)
            subject = item.name if item else u.item_id
            return (f"<tr><td>{escape(u.display_id)}</td>"
                    f"<td>{escape(f'{subject}: {_change_text(u, item, names)}')}</td>"
                    f"<td>{escape(u.sync_status.value)}</td></tr>")

        lines = [f"{count} updates pending"]           # one template for every count
        if not link:
            lines.append("Inventory remains available locally")
        controls = visible_controls(session.user, Screen.S7_SYNC)
        sync_now = ("<p>Sync now</p>" if Action.SYNC_NOW in controls else "")
        return (f"<main>{self.banner()}<h1>{escape(Screen.S7_SYNC.value)}</h1>"
                + "".join(f"<p>{escape(line)}</p>" for line in lines) + sync_now
                + f"<h2>Pending</h2><table>{''.join(row(u) for u in pending)}</table>"
                + f"<h2>Rejected</h2><table>{''.join(row(u) for u in rejected)}</table></main>")

    def submit_action(self, session: Session, action: Action,
                      form: Mapping[str, str]) -> str:
        """Send a crew action to the Command Handler; show the result only after
        the commit returns (FR-027), or the errors if nothing was saved."""
        try:
            if action is Action.RECORD_USAGE:
                result = self._handler.record_usage(
                    session, form.get("item_id", ""), _decimal(form.get("amount")),
                    form.get("reason"))
                lines = [f"Usage saved. New quantity "
                         f"{_quantity_text(result.item.quantity, result.item.unit)}."]
            elif action is Action.MOVE_ITEM:
                result = self._handler.move_item(
                    session, form.get("item_id", ""), form.get("location_id", ""))
                lines = [f"Move saved. New location {self._location_name(result.item.stored_at)}."]
            elif action is Action.SET_CONDITION:
                result = self._handler.set_condition(
                    session, form.get("item_id", ""), form.get("condition", ""), form.get("reason"))
                lines = [f"Condition saved. New condition {result.item.condition.value}."]
            elif action is Action.CORRECT_ITEM:
                field = _correction_field(form.get("field", ""))
                value = (_decimal(form.get("value")) if field is CorrectionField.QUANTITY
                         else _date(form.get("value")))
                result = self._handler.correct_item(
                    session, form.get("item_id", ""), field, value, form.get("reason"))
                item = result.item
                shown = (_quantity_text(item.quantity, item.unit)
                         if field is CorrectionField.QUANTITY else item.expiry_date.isoformat())
                label = "quantity" if field is CorrectionField.QUANTITY else "expiry date"
                lines = [f"Correction saved. New {label} {shown}."]
            elif action is Action.RECORD_RECEIPT:
                received = {key[len("received:"):]: _decimal(value) for key, value in form.items()
                            if key.startswith("received:") and (value or "").strip()}
                receipt = self._handler.record_receipt(
                    session, form.get("mission_id", ""), received, _unlisted(form.get("unlisted")))
                lines = [f"Receipt saved. Mission {receipt.mission.mission_id} Received.",
                         f"{len(receipt.discrepancies)} discrepancies recorded.",
                         "Saved locally"]
                lines += [f"{u.display_id} {u.sync_status.value}" for u in receipt.receipt.updates]
                body = "".join(f"<p>{escape(line)}</p>" for line in lines)
                return f"<main>{self.banner()}{body}</main>"
            else:
                raise ValidationError([f"{action.value} is not available here"])
        except DomainError as exc:
            errors = "".join(f"<li>{escape(str(f))}</li>" for f in exc.args[0])
            return f"<main>{self.banner()}<h1>{escape('Not saved')}</h1><ul>{errors}</ul></main>"
        with self._store.read() as tx:
            low = tx.get_active_alert(result.item.item_id) is not None
        if low:
            lines[-1] += " Low stock alert active."
        lines += ["Saved locally", f"{result.update.display_id} {result.update.sync_status.value}"]
        body = "".join(f"<p>{escape(line)}</p>" for line in lines)
        return f"<main>{self.banner()}{body}</main>"

    def serve(self, host: str, port: int, stop: threading.Event) -> None:
        raise NotImplementedError

    def _location_name(self, location_id: str) -> str:
        with self._store.read() as tx:
            names = {loc.location_id: loc.name for loc in tx.list_locations()}
        return names.get(location_id, location_id)


class EarthScreens:
    def __init__(self, gateway: EarthGateway) -> None:
        self._gateway = gateway

    def banner(self, token: str) -> str:
        from ssir.earth.gateway import Operation
        user = self._gateway.authenticate_user(token)
        self._gateway.authorize(user, Operation.LINK_STATUS)
        # Contracts gap: EarthScreens has no clock of its own; it uses the
        # Gateway's injected Earth clock for "today".
        return _banner("Station link", self._gateway.link_status(), self._gateway._now())

    def dashboard(self, token: str) -> str:
        from ssir.earth.gateway import Operation
        data = self._gateway.handle(token, Operation.DASHBOARD, {})
        return _dashboard(self.banner(token), data["items"], data["alerts"],
                          data["missions"], data["pending"], data["events"], data["now"])

    def inventory(self, token: str, query: str, item_filter: InventoryFilter) -> str:
        from ssir.earth.gateway import Operation
        items = self._gateway.handle(token, Operation.SEARCH_ITEMS,
                                     {"query": query, "filter": item_filter})
        return _inventory(self.banner(token), list(items), query, item_filter)

    def item_details(self, token: str, item_id: str) -> str:
        from ssir.earth.gateway import Operation
        data = self._gateway.handle(token, Operation.GET_ITEM, {"item_id": item_id})
        return _item_details(self.banner(token), data["item"], data["locations"])

    def item_history(self, token: str, item_id: str) -> str:
        from ssir.earth.gateway import Operation
        data = self._gateway.handle(token, Operation.ITEM_HISTORY, {"item_id": item_id})
        return _history(self.banner(token), data["item"], data["updates"], data["users"],
                        data["locations"], self._gateway._now())

    def resupply_plan(self, token: str, mission_id: Optional[str]) -> str:
        from ssir.earth.gateway import Operation
        user = self._gateway.authenticate_user(token)
        if mission_id is None:
            controls = visible_controls(user, Screen.S4_RESUPPLY_PLAN)
            create = "<p>Create mission</p>" if Action.CREATE_MISSION in controls else ""
            return (f"<main>{self.banner(token)}<h1>{escape(Screen.S4_RESUPPLY_PLAN.value)}</h1>"
                    f"{create}</main>")
        view = self._gateway.handle(token, Operation.MANIFEST_EDITOR, {"mission_id": mission_id})
        return _resupply_plan(self.banner(token), view.mission, view.manifest.manifest_version,
                              view.manifest.lines, view.totals, view.alerts,
                              visible_controls(user, Screen.S4_RESUPPLY_PLAN, view.mission))

    def cargo_manifest(self, token: str, mission_id: str,
                       version: Optional[int] = None) -> str:
        from ssir.earth.gateway import Operation
        mission = self._gateway.handle(token, Operation.GET_MISSION, {"mission_id": mission_id})["mission"]
        manifest = self._gateway.handle(token, Operation.GET_MANIFEST,
                                        {"mission_id": mission_id, "version": version})
        review = self._gateway.handle(token, Operation.LOADING_REVIEW, {"mission_id": mission_id})
        latest = manifest.manifest_version == mission.manifest_version
        return _cargo_manifest(self.banner(token), mission_id, manifest.manifest_version, latest,
                               manifest.lines, review["issues"], self._gateway._now())

    def mission_status(self, token: str, mission_id: str) -> str:
        from ssir.earth.gateway import Operation
        user = self._gateway.authenticate_user(token)
        data = self._gateway.handle(token, Operation.GET_MISSION, {"mission_id": mission_id})
        return _mission_status(self.banner(token), data["mission"], data["users"],
                               visible_controls(user, Screen.S6_MISSION_STATUS, data["mission"]),
                               self._gateway._now())

    def sync(self, token: str) -> str:
        raise NotImplementedError

    def submit_action(self, token: str, action: Action, form: Mapping[str, str]) -> str:
        """Send an Earth user's action through the Gateway (FR-003); show the
        result, or every failure if nothing was saved."""
        from ssir.earth.gateway import Operation
        try:
            if action is Action.CREATE_ITEM:
                item = self._gateway.handle(token, Operation.CREATE_ITEM, {"item": _new_item(form)})
                message = f"Item {item.item_id} created."
            elif action is Action.EDIT_ITEM:
                item = self._gateway.handle(token, Operation.EDIT_ITEM, {
                    "item_id": form.get("item_id", ""), "edit": _item_edit(form),
                    "expected_version": _int(form.get("version"))})
                message = f"Item {item.item_id} saved (version {item.record_version})."
            elif action is Action.CREATE_LOCATION:
                location = self._gateway.handle(token, Operation.CREATE_LOCATION, {
                    "location_id": form.get("location_id", ""), "name": form.get("name", "")})
                message = f"Location {location.name} created."
            elif action is Action.CORRECT_ITEM:
                field = _correction_field(form.get("field", ""))
                value = (_decimal(form.get("value")) if field is CorrectionField.QUANTITY
                         else _date(form.get("value")))
                update = self._gateway.handle(token, Operation.CORRECT_ITEM, {
                    "item_id": form.get("item_id", ""), "field": field, "value": value,
                    "reason": form.get("reason", ""), "expected_version": _int(form.get("version"))})
                message = f"Correction {update.display_id} saved."
            elif action is Action.CREATE_MISSION:
                mission = self._gateway.handle(token, Operation.CREATE_MISSION, {
                    "mass_capacity_kg": _decimal(form.get("mass_capacity_kg")),
                    "volume_capacity_m3": _decimal(form.get("volume_capacity_m3"))})
                message = f"Mission {mission.mission_id} created (Draft, manifest version 1)."
            elif action is Action.SAVE_MANIFEST:
                manifest = self._gateway.handle(token, Operation.SAVE_MANIFEST, {
                    "mission_id": form.get("mission_id", ""),
                    "base_version": _int(form.get("base_version")),
                    "draft": ManifestDraft(
                        lines=_lines(form.get("lines")),
                        mass_capacity_kg=_decimal(form.get("mass_capacity_kg")),
                        volume_capacity_m3=_decimal(form.get("volume_capacity_m3")),
                        expected_arrival=_moment(form.get("expected_arrival")))})
                message = f"Manifest saved (version {manifest.manifest_version})."
            elif action in _TRANSITION_OPERATIONS:
                operation, needs_reason = _TRANSITION_OPERATIONS[action]
                payload = {"mission_id": form.get("mission_id", "")}
                if needs_reason:
                    payload["reason"] = form.get("reason", "")
                result = self._gateway.handle(token, getattr(Operation, operation), payload)
                mission = getattr(result, "mission", result)
                message = f"Mission {mission.mission_id} \u2013 {mission.mission_status.value}."
                for warning in getattr(result, "shortfall_warnings", ()):
                    message += f" Warning: {warning.item_id} missing {warning.missing:f}."
            elif action is Action.RECORD_LOADING:
                if (form.get("text") or "").strip():
                    self._gateway.handle(token, Operation.ADD_LOADING_ISSUE, {
                        "mission_id": form.get("mission_id", ""), "text": form.get("text", "")})
                    message = "Loading issue recorded."
                else:
                    self._gateway.handle(token, Operation.RECORD_LOADED_QUANTITY, {
                        "mission_id": form.get("mission_id", ""), "item_id": form.get("item_id", ""),
                        "loaded_quantity": _decimal(form.get("loaded_quantity"))})
                    message = "Loaded quantity recorded."
            else:
                raise ValidationError([f"{action.value} is not available here"])
        except DomainError as exc:
            errors = "".join(f"<li>{escape(str(f))}</li>" for f in exc.args[0])
            return f"<main>{self.banner(token)}<h1>{escape('Not saved')}</h1><ul>{errors}</ul></main>"
        return f"<main>{self.banner(token)}<p>{escape(message)}</p></main>"

    def serve(self, host: str, port: int, stop: threading.Event) -> None:
        raise NotImplementedError
