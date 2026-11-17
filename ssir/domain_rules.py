"""Domain Rules: the business rules defined once and used by both sites.

Every function here is side-effect free. "Now" and "today" are always passed in
(K17); nothing in this module reads a clock. The data types below are the
spec's Domain Model plus the shared sync wire types, kept here because this is
the only module both sites depend on.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any, Mapping, Optional, Protocol, Sequence, Union
from uuid import UUID, uuid4

# --------------------------------------------------------------------------
# Spec constants (values only, no logic)
# --------------------------------------------------------------------------

MAX_TEXT_LENGTH = 1000                                 # FR-032
MAX_FUTURE_EVENT_TIME = timedelta(minutes=5)           # FR-032
RECENT_ACTIVITY_WINDOW = timedelta(days=7)             # FR-001
RECENT_ACTIVITY_LIMIT = 10                             # FR-001
REJECTED_LISTED_FOR = timedelta(days=7)                # FR-028
EARTH_LINK_CONTACT_WINDOW = timedelta(seconds=60)      # FR-002
NON_COUNTABLE_DECIMALS = 3                             # Unit
TOTALS_DECIMALS = 2                                    # FR-015
CLOCK_TOLERANCE = timedelta(seconds=30)                # NFR-005
DISPOSED_REASON = "Disposed"                           # FR-006


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------

class Role(Enum):
    STATION_CREW = "StationCrew"
    LOGISTICS_PLANNER = "LogisticsPlanner"
    GROUND_MISSION_CONTROL = "GroundMissionControl"


class Condition(Enum):
    USABLE = "Usable"
    DAMAGED = "Damaged"


class Criticality(Enum):
    CRITICAL = "Critical"
    STANDARD = "Standard"


class UpdateType(Enum):
    USAGE = "Usage"
    MOVE = "Move"
    CONDITION = "Condition"
    CORRECTION = "Correction"
    RECEIPT = "Receipt"
    RESOLUTION = "Resolution"


class UpdateField(Enum):
    QUANTITY = "quantity"
    LOCATION = "storedAt"
    CONDITION = "condition"
    EXPIRY_DATE = "expiryDate"


class CorrectionField(Enum):
    QUANTITY = "quantity"
    EXPIRY_DATE = "expiryDate"


class SyncStatus(Enum):
    AWAITING_SYNC = "Awaiting sync"
    SYNCHRONIZED = "Synchronized"
    CONFLICT = "Conflict"
    REJECTED = "Rejected"


class AlertStatus(Enum):
    ACTIVE = "Active"
    RESOLVED = "Resolved"


class AlertChange(Enum):
    NONE = "none"
    RAISE = "raise"
    RESOLVE = "resolve"


class Coverage(Enum):
    COVERED = "Covered"
    NOT_COVERED = "Not covered"


class MissionStatus(Enum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    APPROVED = "Approved"
    SHIPPED = "Shipped"
    RECEIVED = "Received"
    CANCELLED = "Cancelled"


class Transition(Enum):
    SUBMIT = "submit"
    APPROVE = "approve"
    RETURN = "return"
    REOPEN = "reopen"
    CONFIRM_DISPATCH = "confirm dispatch"
    RECORD_RECEIPT = "record receipt"
    CANCEL = "cancel"


class DiscrepancyStatus(Enum):
    OPEN = "Open"
    RESOLVED = "Resolved"


class InventoryFilter(Enum):
    ALL = "All"
    LOW_STOCK = "Low stock"
    DAMAGED = "Damaged"
    EXPIRED = "Expired"


class MergeDecision(Enum):
    APPLY = "apply"          # base version is current
    MERGE = "merge"          # out of date, but no clash
    CONFLICT = "conflict"    # same field changed on both sides, or result < 0


class ResolutionChoice(Enum):
    KEEP_LOCAL = "Keep local value"
    KEEP_EARTH = "Keep Earth value"


class OutcomeKind(Enum):
    ACKNOWLEDGED = "acknowledged"
    CONFLICT = "conflict"
    REJECTED = "rejected"


class ChangeKind(Enum):
    ITEM = "item"
    LOCATION = "location"
    MISSION = "mission"
    USER = "user"
    OUTCOME = "outcome"
    RESOLUTION = "resolution"


class ActivityKind(Enum):
    INVENTORY_UPDATE = "inventory update"
    MISSION_STATUS = "mission status change"
    DISCREPANCY_RECORDED = "discrepancy recorded"
    DISCREPANCY_RESOLVED = "discrepancy resolved"
    ALERT_RAISED = "alert raised"
    ALERT_RESOLVED = "alert resolved"


class Action(Enum):
    """Every permission-checked action (FR-003)."""
    RECORD_USAGE = "record usage"
    MOVE_ITEM = "move item"
    SET_CONDITION = "set condition"
    CORRECT_ITEM = "correct item"
    RECORD_RECEIPT = "record receipt"
    CREATE_ITEM = "create item"
    EDIT_ITEM = "edit item"
    CREATE_LOCATION = "create location"
    CREATE_MISSION = "create mission"
    SAVE_MANIFEST = "save manifest"
    SUBMIT_MISSION = "submit mission"
    RECORD_LOADING = "record loading"
    APPROVE_MISSION = "approve mission"
    RETURN_MISSION = "return mission"
    REOPEN_MISSION = "reopen mission"
    CANCEL_MISSION = "cancel mission"
    CONFIRM_DISPATCH = "confirm dispatch"
    RESOLVE_DISCREPANCY = "resolve discrepancy"
    RESOLVE_CONFLICT = "resolve conflict"
    SYNC_NOW = "sync now"
    VIEW = "view"


# --------------------------------------------------------------------------
# Domain objects (spec Domain Model)
# --------------------------------------------------------------------------

FieldValue = Union[str, Decimal, date, None]


@dataclass(frozen=True)
class PublicKeyRecord:
    key_id: str
    public_key: bytes
    revoked_at: Optional[datetime]


@dataclass(frozen=True)
class Signature:
    key_id: str
    value: bytes


@dataclass(frozen=True)
class User:
    user_id: str
    name: str
    role: Role
    can_reopen: bool
    public_keys: tuple[PublicKeyRecord, ...]


@dataclass(frozen=True)
class Unit:
    name: str
    countable: bool


@dataclass(frozen=True)
class StorageLocation:
    location_id: str
    name: str


@dataclass(frozen=True)
class InventoryItem:
    item_id: str
    name: str
    barcodes: tuple[str, ...]
    quantity: Decimal
    unit: Unit
    condition: Condition
    expiry_date: Optional[date]
    unit_mass_kg: Decimal
    unit_volume_m3: Decimal
    minimum_quantity: Decimal
    criticality: Criticality
    stored_at: str                      # locationId
    record_version: int                 # server-set


@dataclass(frozen=True)
class InventoryUpdate:
    update_id: UUID
    display_id: str                     # U… station, E… Earth
    item_id: str
    type: UpdateType
    field: UpdateField
    old_value: FieldValue
    new_value: FieldValue
    quantity_delta: Optional[Decimal]
    reason: Optional[str]
    event_time: datetime
    base_version: int
    sync_status: SyncStatus
    signature: Optional[Signature]
    sequence: Optional[int]             # commit sequence on the recording side (K6)
    receipt_id: Optional[UUID]          # set when part of a receipt (FR-025)
    recorded_by: Optional[str]          # server-set
    received_at: Optional[datetime]     # server-set
    rejected_at: Optional[datetime]     # Earth rejection time (FR-028, Spec issue 3)


@dataclass(frozen=True)
class SupplyAlert:
    alert_id: str
    item_id: str
    alert_status: AlertStatus
    raised_at: datetime
    resolved_at: Optional[datetime]


@dataclass(frozen=True)
class StatusHistoryEntry:
    status: MissionStatus
    time: datetime
    user_id: str
    reason: Optional[str]


@dataclass(frozen=True)
class ManifestLine:
    item_id: str
    line_quantity: Decimal
    loaded_quantity: Optional[Decimal]
    received_quantity: Optional[Decimal]


@dataclass(frozen=True)
class CargoManifest:
    mission_id: str
    manifest_version: int
    lines: tuple[ManifestLine, ...]


@dataclass(frozen=True)
class ManifestDraft:
    """The editable content whose change creates a new manifest version (FR-016)."""
    lines: tuple[ManifestLine, ...]
    mass_capacity_kg: Decimal
    volume_capacity_m3: Decimal
    expected_arrival: Optional[datetime]


@dataclass(frozen=True)
class ResupplyMission:
    mission_id: str                     # server-set
    mission_status: MissionStatus
    mass_capacity_kg: Decimal
    volume_capacity_m3: Decimal
    expected_arrival: Optional[datetime]
    dispatched_at: Optional[datetime]
    receipt_id: Optional[UUID]
    manifest_version: int
    status_history: tuple[StatusHistoryEntry, ...]


@dataclass(frozen=True)
class LoadingIssue:
    mission_id: str
    text: str
    recorded_by: str
    time: datetime


@dataclass(frozen=True)
class Discrepancy:
    discrepancy_id: str
    mission_id: str
    item_id: Optional[str]              # None for an unlisted item
    description: str
    expected: Decimal
    received: Decimal
    status: DiscrepancyStatus
    resolution_note: Optional[str]


@dataclass(frozen=True)
class UnlistedItem:
    description: str
    quantity: Decimal


@dataclass(frozen=True)
class ReceiptUnit:
    """A receipt synchronized as one unit (FR-025, K13)."""
    receipt_id: UUID
    mission_id: str
    received: Mapping[str, Decimal]     # itemId -> received quantity, every line
    unlisted: tuple[UnlistedItem, ...]
    updates: tuple[InventoryUpdate, ...]
    discrepancies: tuple[Discrepancy, ...]
    event_time: datetime
    signature: Optional[Signature]
    sequence: Optional[int]
    sync_status: SyncStatus


@dataclass(frozen=True)
class ConflictRecord:
    update_id: UUID
    item_id: str
    field: UpdateField
    local_value: FieldValue
    earth_value: FieldValue
    resolved: bool
    resolution: Optional[ResolutionChoice]
    resolved_by: Optional[str]
    reason: Optional[str]


# --------------------------------------------------------------------------
# Derived / view values
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ManifestTotals:
    mass_kg: Decimal                    # rounded to 2 decimals
    volume_m3: Decimal                  # rounded to 2 decimals
    mass_capacity_kg: Decimal
    volume_capacity_m3: Decimal
    over_mass: bool
    over_volume: bool


@dataclass(frozen=True)
class AlertCoverage:
    alert: SupplyAlert
    coverage: Coverage


@dataclass(frozen=True)
class LoadingReviewLine:
    item_id: str
    planned: Decimal
    loaded: Optional[Decimal]
    missing: Decimal


@dataclass(frozen=True)
class FieldChange:
    """One Earth-side change to one field, with its source (Further decisions)."""
    item_id: str
    field: UpdateField
    version: int
    from_this_station: bool
    update_id: Optional[UUID]


@dataclass(frozen=True)
class MergeResult:
    decision: MergeDecision
    conflicting_fields: tuple[UpdateField, ...]


@dataclass(frozen=True)
class ActivityEvent:
    time: datetime
    kind: ActivityKind
    description: str


@dataclass(frozen=True)
class LinkStatus:
    available: bool
    last_full_sync: Optional[datetime]


# --------------------------------------------------------------------------
# Sync wire types (shared by Sync Agent and Sync Endpoint)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Handshake:
    station_time: datetime
    pending_count: int


@dataclass(frozen=True)
class HandshakeReply:
    earth_time: datetime
    committed_sequence: int


@dataclass(frozen=True)
class Outcome:
    kind: OutcomeKind
    key: UUID                           # updateId or receiptId
    new_versions: Mapping[str, int]     # itemId -> new recordVersion
    reason: Optional[str]
    at: datetime                        # Earth time of the outcome


@dataclass(frozen=True)
class Change:
    cursor: int
    kind: ChangeKind
    payload: object


@dataclass(frozen=True)
class ChangeBatch:
    changes: tuple[Change, ...]
    next_cursor: int
    complete: bool


# --------------------------------------------------------------------------
# External identity system (Non-goals, User) — interface only
# --------------------------------------------------------------------------

class IdentityDirectory(Protocol):
    def authenticate(self, token: str) -> User: ...
    def get_user(self, user_id: str) -> User: ...
    def users_changed_since(self, cursor: int) -> tuple[tuple[User, ...], int]: ...


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class DomainError(Exception):
    """Base error. args[0] is a list of human-readable failures."""


class ValidationError(DomainError):
    pass


class Forbidden(DomainError):
    pass


class Unauthenticated(DomainError):
    pass


class NotFound(DomainError):
    pass


class InvalidTransition(DomainError):
    pass


class StaleState(DomainError):
    """The action was based on an out-of-date status or version (FR-016, FR-031, FR-032)."""


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate_text(text: Optional[str], *, required: bool) -> Optional[str]:
    trimmed = "" if text is None else text.strip()
    if trimmed == "":
        if required:
            raise ValidationError(["text is required"])
        return None
    # The limit applies to the trimmed text, which is what is stored (FR-032).
    if len(trimmed) > MAX_TEXT_LENGTH:
        raise ValidationError([f"text is over {MAX_TEXT_LENGTH:,} characters"])
    return trimmed


def validate_amount(amount: Decimal, unit: Unit) -> None:
    failures = []
    if not isinstance(amount, Decimal) or not amount.is_finite():
        raise ValidationError(["amount must be a number"])
    if amount <= 0:
        failures.append("amount must be greater than 0")
    if unit.countable and amount != amount.to_integral_value():
        failures.append(f"{unit.name} takes whole numbers only")
    if not unit.countable and _decimal_places(amount) > NON_COUNTABLE_DECIMALS:
        failures.append(f"{unit.name} allows at most {NON_COUNTABLE_DECIMALS} decimals")
    if failures:
        raise ValidationError(failures)


def _decimal_places(value: Decimal) -> int:
    """Decimal places of the value itself: 1.500 has 1, 0.001 has 3."""
    exponent = value.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def validate_usage(item: InventoryItem, amount: Decimal, reason: Optional[str]) -> None:
    failures: list[str] = []
    try:
        validate_amount(amount, item.unit)
    except ValidationError as exc:
        failures.extend(exc.args[0])
    else:
        if amount > item.quantity:
            failures.append(f"amount is more than the {_quantity_text(item.quantity, item.unit)} on board")
    try:
        validate_text(reason, required=True)
    except ValidationError as exc:
        failures.extend(f"reason: {f}" for f in exc.args[0])
    if failures:
        raise ValidationError(failures)


def validate_move(item: InventoryItem, location_id: str,
                  locations: Sequence[StorageLocation]) -> None:
    if location_id not in {loc.location_id for loc in locations}:
        raise ValidationError([f"unknown storage location {location_id}"])
    if location_id == item.stored_at:
        raise ValidationError([f"{item.name} is already at that location"])


def parse_condition(value: str) -> Condition:
    for condition in Condition:
        if value == condition.value:
            return condition
    raise ValidationError([f"condition must be {' or '.join(c.value for c in Condition)}"])


def validate_condition_change(item: InventoryItem, condition: Condition,
                              reason: Optional[str]) -> None:
    failures: list[str] = []
    # Decision (Nov 16, 2026, Claude): setting the current condition is
    # rejected, like a move to the current location (FR-007).
    if condition is item.condition:
        failures.append(f"{item.name} is already {condition.value}")
    try:
        validate_text(reason, required=True)
    except ValidationError as exc:
        failures.extend(f"reason: {f}" for f in exc.args[0])
    if failures:
        raise ValidationError(failures)


def validate_correction(item: InventoryItem, field: CorrectionField,
                        new_value: Union[Decimal, date], reason: Optional[str]) -> None:
    failures: list[str] = []
    if field is CorrectionField.QUANTITY:
        if not isinstance(new_value, Decimal) or not new_value.is_finite():
            failures.append("quantity must be a number")
        elif new_value < 0:
            failures.append("quantity must be at least 0")
        elif item.unit.countable and new_value != new_value.to_integral_value():
            failures.append(f"{item.unit.name} takes whole numbers only")
        elif not item.unit.countable and _decimal_places(new_value) > NON_COUNTABLE_DECIMALS:
            failures.append(f"{item.unit.name} allows at most {NON_COUNTABLE_DECIMALS} decimals")
        elif new_value == item.quantity:
            # Decision (Nov 16, 2026, Claude): a correction must change the value.
            failures.append(f"quantity is already {_quantity_text(item.quantity, item.unit)}")
    else:
        if not isinstance(new_value, date) or isinstance(new_value, datetime):
            failures.append("expiry date must be a date")
        elif new_value == item.expiry_date:
            failures.append(f"expiry date is already {new_value.isoformat()}")
    try:
        validate_text(reason, required=True)
    except ValidationError as exc:
        failures.extend(f"reason: {f}" for f in exc.args[0])
    if failures:
        raise ValidationError(failures)


def validate_item_data(item: InventoryItem, others: Sequence[InventoryItem],
                       locations: Sequence[StorageLocation]) -> None:
    failures: list[str] = []
    if not item.item_id.strip():
        failures.append("item ID is required")
    try:
        validate_text(item.name, required=True)
    except ValidationError as exc:
        failures.extend(f"name: {f}" for f in exc.args[0])
    taken = {code for other in others if other.item_id != item.item_id for code in other.barcodes}
    for code in item.barcodes:
        if not code.strip():
            failures.append("barcodes cannot be empty")
        elif code in taken:
            failures.append(f"barcode {code} is used by another item")
    if len(set(item.barcodes)) != len(item.barcodes):
        failures.append("a barcode is listed twice")
    for label, value in (("quantity", item.quantity), ("minimum", item.minimum_quantity)):
        if value < 0:
            failures.append(f"{label} must be at least 0")
        elif item.unit.countable and value != value.to_integral_value():
            failures.append(f"{label}: {item.unit.name} takes whole numbers only")
        elif not item.unit.countable and _decimal_places(value) > NON_COUNTABLE_DECIMALS:
            failures.append(f"{label}: {item.unit.name} allows at most {NON_COUNTABLE_DECIMALS} decimals")
    if item.unit_mass_kg < 0:
        failures.append("unit mass must be at least 0")
    if item.unit_volume_m3 < 0:
        failures.append("unit volume must be at least 0")
    if item.stored_at not in {loc.location_id for loc in locations}:
        failures.append(f"unknown storage location {item.stored_at}")
    if failures:
        raise ValidationError(failures)


def validate_capacities(mass_capacity_kg: Decimal, volume_capacity_m3: Decimal) -> None:
    failures = []
    for label, value in (("mass capacity", mass_capacity_kg), ("volume capacity", volume_capacity_m3)):
        if not isinstance(value, Decimal) or not value.is_finite():
            failures.append(f"{label} must be a number")
        elif value <= 0:
            failures.append(f"{label} must be greater than 0")
    if failures:
        raise ValidationError(failures)


def validate_event_time(event_time: datetime, now: datetime) -> None:
    raise NotImplementedError


def validate_base_version(base_version: int, current_version: int) -> None:
    raise NotImplementedError


def validate_loaded_quantity(quantity: Decimal, unit: Unit) -> None:
    if not isinstance(quantity, Decimal) or not quantity.is_finite():
        raise ValidationError(["loaded quantity must be a number"])
    if quantity == 0:
        return                                     # 0 loaded is allowed (FR-022)
    if quantity < 0:
        raise ValidationError(["loaded quantity must be at least 0"])
    validate_amount(quantity, unit)


def validate_receipt(lines: Sequence[ManifestLine], received: Mapping[str, Decimal],
                     unlisted: Sequence[UnlistedItem], items: Mapping[str, InventoryItem]) -> None:
    if any(line.item_id not in received for line in lines):
        raise ValidationError(["Receipt requires actual delivered quantities"])
    failures: list[str] = []
    planned = {line.item_id for line in lines}
    for item_id, quantity in received.items():
        if item_id not in planned:
            failures.append(f"{item_id} is not on the manifest; report it as an unlisted item")
        elif not isinstance(quantity, Decimal) or not quantity.is_finite():
            failures.append(f"{item_id}: received quantity must be a number")
        elif quantity < 0:
            failures.append(f"{item_id}: received quantity must be at least 0")
        elif quantity > 0 and item_id in items:
            try:
                validate_amount(quantity, items[item_id].unit)
            except ValidationError as exc:
                failures.extend(f"{item_id}: {f}" for f in exc.args[0])
    for entry in unlisted:
        try:
            validate_text(entry.description, required=True)
        except ValidationError as exc:
            failures.extend(f"unlisted item: {f}" for f in exc.args[0])
        if not isinstance(entry.quantity, Decimal) or not entry.quantity > 0:
            failures.append("unlisted item: quantity must be greater than 0")
    if failures:
        raise ValidationError(failures)


# --------------------------------------------------------------------------
# Permissions
# --------------------------------------------------------------------------

# Which role may perform which action (Actors; FR-003). Every role can view
# every screen (User). Sync on demand is offered to every user (FR-029).
_ROLE_ACTIONS: Mapping[Role, frozenset[Action]] = {
    Role.STATION_CREW: frozenset({
        Action.RECORD_USAGE, Action.MOVE_ITEM, Action.SET_CONDITION,
        Action.CORRECT_ITEM,                                    # FR-009
        Action.RECORD_RECEIPT,                                  # FR-025, FR-026
        Action.SYNC_NOW, Action.VIEW,
    }),
    Role.LOGISTICS_PLANNER: frozenset({
        Action.CREATE_ITEM, Action.EDIT_ITEM, Action.CREATE_LOCATION,   # FR-010
        Action.CREATE_MISSION, Action.SAVE_MANIFEST, Action.SUBMIT_MISSION,
        Action.RECORD_LOADING,                                  # FR-022
        Action.SYNC_NOW, Action.VIEW,
    }),
    Role.GROUND_MISSION_CONTROL: frozenset({
        Action.APPROVE_MISSION, Action.RETURN_MISSION, Action.REOPEN_MISSION,
        Action.CANCEL_MISSION, Action.CONFIRM_DISPATCH,
        Action.CORRECT_ITEM,                                    # FR-009
        Action.RESOLVE_DISCREPANCY, Action.RESOLVE_CONFLICT,    # FR-026, FR-031
        Action.SYNC_NOW, Action.VIEW,
    }),
}


def is_permitted(user: User, action: Action) -> bool:
    if action not in _ROLE_ACTIONS.get(user.role, frozenset()):
        return False
    if action is Action.REOPEN_MISSION:
        return user.can_reopen                                  # FR-020
    return True


def require_permission(user: User, action: Action) -> None:
    if is_permitted(user, action):
        return
    if action is Action.REOPEN_MISSION and action in _ROLE_ACTIONS.get(user.role, frozenset()):
        raise Forbidden([f"{user.name} does not have reopen permission"])
    raise Forbidden([f"{user.role.value} may not {action.value}"])


# --------------------------------------------------------------------------
# Alerts
# --------------------------------------------------------------------------

def evaluate_alert(item: InventoryItem, active_alert: Optional[SupplyAlert]) -> AlertChange:
    below = item.quantity < item.minimum_quantity
    if below and active_alert is None:
        return AlertChange.RAISE
    if not below and active_alert is not None:
        return AlertChange.RESOLVE
    return AlertChange.NONE


def alert_coverage(item: InventoryItem, line_quantity: Optional[Decimal]) -> Coverage:
    planned = line_quantity if line_quantity is not None else Decimal(0)
    return Coverage.COVERED if item.quantity + planned >= item.minimum_quantity else Coverage.NOT_COVERED


# --------------------------------------------------------------------------
# Inventory search and filters
# --------------------------------------------------------------------------

def today_utc(now: datetime) -> date:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(timezone.utc).date()


def is_low_stock(item: InventoryItem) -> bool:
    return item.quantity < item.minimum_quantity


def is_expired(item: InventoryItem, today: date) -> bool:
    return item.expiry_date is not None and item.expiry_date < today


def matches_query(item: InventoryItem, query: str) -> bool:
    if query == "":
        return True
    needle = query.casefold()
    return (needle in item.name.casefold()
            or needle in item.item_id.casefold()
            or query in item.barcodes)


def filter_items(items: Sequence[InventoryItem], query: str,
                 item_filter: InventoryFilter, today: date) -> list[InventoryItem]:
    def passes(item: InventoryItem) -> bool:
        if item_filter is InventoryFilter.LOW_STOCK:
            return is_low_stock(item)
        if item_filter is InventoryFilter.DAMAGED:
            return item.condition is Condition.DAMAGED
        if item_filter is InventoryFilter.EXPIRED:
            return is_expired(item, today)
        return True
    return [item for item in items if passes(item) and matches_query(item, query)]


# Recent-activity descriptions (FR-001), shared by both sites. Decision
# (Nov 16, 2026, taken by Claude, no preference given): "<subject>: <what happened>".

def _value_text(value: FieldValue, item: Optional[InventoryItem], field: UpdateField,
                location_names: Optional[Mapping[str, str]] = None) -> str:
    if value is None:
        return "none"
    if field is UpdateField.QUANTITY and item is not None and isinstance(value, Decimal):
        return _quantity_text(value, item.unit)
    if field is UpdateField.LOCATION and location_names is not None:
        return location_names.get(str(value), str(value))
    if isinstance(value, Decimal):
        return f"{value:f}"
    return str(value)


def _change_text(update: InventoryUpdate, item: Optional[InventoryItem],
                 location_names: Optional[Mapping[str, str]] = None) -> str:
    """What an update changed, e.g. "Usage \u22122 packs", "Move Store B \u2192 Store C"."""
    if update.quantity_delta is not None and item is not None:
        sign = "+" if update.quantity_delta >= 0 else "\u2212"
        return f"{update.type.value} {sign}{_quantity_text(abs(update.quantity_delta), item.unit)}"
    return (f"{update.type.value} "
            f"{_value_text(update.old_value, item, update.field, location_names)}"
            f" \u2192 {_value_text(update.new_value, item, update.field, location_names)}")


def _describe_update(update: InventoryUpdate, item: Optional[InventoryItem],
                     location_names: Optional[Mapping[str, str]] = None) -> str:
    subject = item.name if item is not None else update.item_id
    return f"{subject}: {_change_text(update, item, location_names)} ({update.display_id})"


def _describe_mission_status(mission_id: str, entry: StatusHistoryEntry) -> str:
    return f"Mission {mission_id}: {entry.status.value}"


def _describe_discrepancy(discrepancy: Discrepancy, item: Optional[InventoryItem]) -> str:
    about = item.name if item is not None else (discrepancy.item_id or discrepancy.description)
    verb = "resolved" if discrepancy.status is DiscrepancyStatus.RESOLVED else "recorded"
    return f"Mission {discrepancy.mission_id}: discrepancy {verb} ({about})"


def _describe_alert(item: Optional[InventoryItem], item_id: str, raised: bool) -> str:
    subject = item.name if item is not None else item_id
    return f"{subject}: alert {'raised' if raised else 'resolved'}"


def _quantity_text(quantity: Decimal, unit: Unit) -> str:
    """'6 packs', '1 kit', '2.000 kg'. Decision (Nov 16, 2026): a countable
    unit takes a plural 's' unless the quantity is exactly 1; other units never do."""
    name = unit.name + "s" if unit.countable and quantity != 1 else unit.name
    return f"{quantity:f} {name}"


# --------------------------------------------------------------------------
# Missions and manifests
# --------------------------------------------------------------------------

# The mission state machine (spec, Mission lifecycle). Guards such as
# "at least one line" or canReopen are checked by the callers.
_TRANSITIONS: Mapping[tuple[MissionStatus, Transition], MissionStatus] = {
    (MissionStatus.DRAFT, Transition.SUBMIT): MissionStatus.SUBMITTED,
    (MissionStatus.SUBMITTED, Transition.APPROVE): MissionStatus.APPROVED,
    (MissionStatus.SUBMITTED, Transition.RETURN): MissionStatus.DRAFT,
    (MissionStatus.APPROVED, Transition.REOPEN): MissionStatus.DRAFT,
    (MissionStatus.APPROVED, Transition.CONFIRM_DISPATCH): MissionStatus.SHIPPED,
    (MissionStatus.SHIPPED, Transition.RECORD_RECEIPT): MissionStatus.RECEIVED,
    (MissionStatus.DRAFT, Transition.CANCEL): MissionStatus.CANCELLED,
    (MissionStatus.SUBMITTED, Transition.CANCEL): MissionStatus.CANCELLED,
    (MissionStatus.APPROVED, Transition.CANCEL): MissionStatus.CANCELLED,
}


def next_status(current: MissionStatus, transition: Transition) -> MissionStatus:
    try:
        return _TRANSITIONS[(current, transition)]
    except KeyError:
        raise InvalidTransition(
            [f"'{transition.value}' is not allowed for a {current.value} mission"]) from None


def _validate_lines(lines: Sequence[ManifestLine], items: Mapping[str, InventoryItem]) -> None:
    """ManifestLine: one line per item, quantity > 0, known item; decision
    (Nov 16, 2026, Claude): line quantities follow the unit rule."""
    failures: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if line.item_id in seen:
            failures.append(f"{line.item_id} has more than one line")
        seen.add(line.item_id)
        item = items.get(line.item_id)
        if item is None:
            failures.append(f"no item {line.item_id}")
            continue
        try:
            validate_amount(line.line_quantity, item.unit)
        except ValidationError as exc:
            failures.extend(f"{line.item_id}: {f}" for f in exc.args[0])
    if failures:
        raise ValidationError(failures)


def manifest_totals(lines: Sequence[ManifestLine], items: Mapping[str, InventoryItem],
                    mass_capacity_kg: Decimal, volume_capacity_m3: Decimal) -> ManifestTotals:
    missing = sorted({line.item_id for line in lines if line.item_id not in items})
    if missing:
        raise NotFound([f"no item {item_id}" for item_id in missing])
    mass = sum((line.line_quantity * items[line.item_id].unit_mass_kg for line in lines), Decimal(0))
    volume = sum((line.line_quantity * items[line.item_id].unit_volume_m3 for line in lines), Decimal(0))
    # Decisions (Nov 16, 2026, Claude): totals are shown rounded half-up to 2
    # decimals (G-B4); over-capacity is judged on the exact totals (G-B5).
    step = Decimal(1).scaleb(-TOTALS_DECIMALS)
    return ManifestTotals(
        mass_kg=mass.quantize(step, rounding=ROUND_HALF_UP),
        volume_m3=volume.quantize(step, rounding=ROUND_HALF_UP),
        mass_capacity_kg=mass_capacity_kg, volume_capacity_m3=volume_capacity_m3,
        over_mass=mass > mass_capacity_kg, over_volume=volume > volume_capacity_m3)


def manifest_changed(current: ManifestDraft, proposed: ManifestDraft) -> bool:
    """Lines (item and planned quantity), capacities or expected arrival differ
    (FR-016). Loaded and received quantities are not part of a version."""
    def lines(draft: ManifestDraft) -> dict[str, Decimal]:
        return {line.item_id: line.line_quantity for line in draft.lines}
    return (lines(current) != lines(proposed)
            or current.mass_capacity_kg != proposed.mass_capacity_kg
            or current.volume_capacity_m3 != proposed.volume_capacity_m3
            or current.expected_arrival != proposed.expected_arrival)


def submission_failures(lines: Sequence[ManifestLine], totals: ManifestTotals) -> list[str]:
    failures = []
    if not lines:
        failures.append("manifest has no lines")
    if totals.over_mass:
        failures.append("mass capacity exceeded")
    if totals.over_volume:
        failures.append("volume capacity exceeded")
    return failures


def dispatch_failures(lines: Sequence[ManifestLine],
                      expected_arrival: Optional[datetime]) -> list[str]:
    failures = [f"{line.item_id} has no loaded quantity"
                for line in lines if line.loaded_quantity is None]
    if expected_arrival is None:
        failures.append("expected arrival is not set")
    return failures


def loading_review(lines: Sequence[ManifestLine]) -> list[LoadingReviewLine]:
    """Planned, loaded and missing per line (FR-022). Decision (Nov 16, 2026,
    Claude; gap G-B6): loading more than planned shows Missing 0."""
    review = []
    for line in lines:
        loaded = line.loaded_quantity
        missing = line.line_quantity if loaded is None else max(line.line_quantity - loaded, Decimal(0))
        review.append(LoadingReviewLine(line.item_id, line.line_quantity, loaded, missing))
    return review


def receipt_discrepancies(mission_id: str, lines: Sequence[ManifestLine],
                          received: Mapping[str, Decimal],
                          unlisted: Sequence[UnlistedItem]) -> list[Discrepancy]:
    """One Open discrepancy per line where received differs from planned, and
    one per unlisted item (FR-026). IDs are made on the device, like receiptId."""
    found = [Discrepancy(discrepancy_id=uuid4().hex, mission_id=mission_id, item_id=line.item_id,
                         description="received differs from planned",
                         expected=line.line_quantity, received=received[line.item_id],
                         status=DiscrepancyStatus.OPEN, resolution_note=None)
             for line in lines if received[line.item_id] != line.line_quantity]
    found += [Discrepancy(discrepancy_id=uuid4().hex, mission_id=mission_id, item_id=None,
                          description=entry.description.strip(), expected=Decimal(0),
                          received=entry.quantity, status=DiscrepancyStatus.OPEN,
                          resolution_note=None)
              for entry in unlisted]
    return found


# --------------------------------------------------------------------------
# Synchronization
# --------------------------------------------------------------------------

def merge_or_conflict(update: InventoryUpdate, item: InventoryItem,
                      earth_changes_since_base: Sequence[FieldChange]) -> MergeResult:
    raise NotImplementedError


def canonical_update_content(update: InventoryUpdate) -> bytes:
    """Deterministic bytes the recorder signs (NFR-003): every client-set field,
    including updateId, sequence, eventTime and baseVersion. Excluded: the
    signature, server-set fields (recordedBy, receivedAt) and the mutable
    sync status and Earth rejection time."""
    excluded = {"signature", "recorded_by", "received_at", "sync_status", "rejected_at"}
    fields = {f.name: _encode(getattr(update, f.name))
              for f in dataclasses.fields(update) if f.name not in excluded}
    return b"ssir.update.v1\n" + json.dumps(
        fields, separators=(",", ":"), sort_keys=True).encode("utf-8")


def canonical_receipt_content(receipt: ReceiptUnit) -> bytes:
    """Deterministic bytes the recorder signs for a whole receipt unit (FR-025):
    every client-set field, each update by its own canonical content."""
    fields = {f.name: _encode(getattr(receipt, f.name)) for f in dataclasses.fields(receipt)
              if f.name not in {"signature", "sync_status", "updates"}}
    fields["updates"] = [canonical_update_content(u).decode("utf-8") for u in receipt.updates]
    return b"ssir.receipt.v1\n" + json.dumps(
        fields, separators=(",", ":"), sort_keys=True).encode("utf-8")


def rejected_still_listed(rejected_at: datetime, now: datetime) -> bool:
    # Same inclusive 7-day edge as FR-001 (decision Nov 16, 2026).
    return now - rejected_at <= REJECTED_LISTED_FOR


def earth_link_available(session_open: bool, last_station_contact: Optional[datetime],
                         now: datetime) -> bool:
    # Decision (Nov 16, 2026): the 60-second edge is inclusive (gap G-B2).
    if session_open:
        return True
    return (last_station_contact is not None
            and now - last_station_contact <= EARTH_LINK_CONTACT_WINDOW)


# --------------------------------------------------------------------------
# Dashboard, history and display
# --------------------------------------------------------------------------

def order_alerts(alerts: Sequence[SupplyAlert],
                 items: Mapping[str, InventoryItem]) -> list[SupplyAlert]:
    active = [a for a in alerts if a.alert_status is AlertStatus.ACTIVE]
    missing = sorted({a.item_id for a in active if a.item_id not in items})
    if missing:
        raise NotFound([f"no item {item_id}" for item_id in missing])
    # Critical items first (FR-001). Decision (Nov 16, 2026): within the same
    # criticality, newest raisedAt first; item ID breaks exact ties.
    ordered = sorted(active, key=lambda a: a.item_id)
    ordered.sort(key=lambda a: a.raised_at, reverse=True)
    ordered.sort(key=lambda a: items[a.item_id].criticality is not Criticality.CRITICAL)
    return ordered


# Missions that can be "next" (FR-001), ranked by how far along they are.
# Decision (Nov 16, 2026): ties go to the more advanced status.
_NEXT_MISSION_RANK: Mapping[MissionStatus, int] = {
    MissionStatus.SHIPPED: 0,
    MissionStatus.APPROVED: 1,
    MissionStatus.SUBMITTED: 2,
}


def _mission_number(mission: ResupplyMission) -> tuple[int, str]:
    """Numeric order of R… IDs (R9 before R10); non-numeric IDs sort after."""
    digits = mission.mission_id[1:]
    return (int(digits), "") if digits.isdigit() else (2**63, mission.mission_id)


def _last_changed(mission: ResupplyMission) -> Optional[datetime]:
    """Decision (Nov 16, 2026): a mission last changed at its latest
    status-history entry; manifest saves leave no time on the mission."""
    return max((entry.time for entry in mission.status_history), default=None)


def next_mission(missions: Sequence[ResupplyMission]) -> Optional[ResupplyMission]:
    candidates = [m for m in missions if m.mission_status in _NEXT_MISSION_RANK]
    if not candidates:
        return None

    def tie_break(m: ResupplyMission) -> tuple:
        return (_NEXT_MISSION_RANK[m.mission_status], _mission_number(m))

    with_arrival = [m for m in candidates if m.expected_arrival is not None]
    if with_arrival:
        return min(with_arrival, key=lambda m: (m.expected_arrival, tie_break(m)))
    # Most recently changed first; a mission with no history counts as oldest.
    newest = max((_last_changed(m) for m in candidates if _last_changed(m) is not None),
                 default=None)
    tied = [m for m in candidates if _last_changed(m) == newest]
    return min(tied, key=tie_break)


def recent_activity(events: Sequence[ActivityEvent], now: datetime) -> list[ActivityEvent]:
    # Decisions (Nov 16, 2026): the 7-day edge is inclusive; an event later
    # than "now" is kept (no upper bound); equal times keep the input order.
    since = now - RECENT_ACTIVITY_WINDOW
    recent = [event for event in events if event.time >= since]
    recent.sort(key=lambda event: event.time, reverse=True)   # stable sort
    return recent[:RECENT_ACTIVITY_LIMIT]


def order_history(updates: Sequence[InventoryUpdate]) -> list[InventoryUpdate]:
    """Newest event time first (FR-011). Updates must be given in commit order
    on the side showing the history; equal event times keep that order
    reversed, so the later commit comes first (decision Nov 16, 2026, gap G-B3).
    On the station commit order is the sequence; on Earth it is Earth's own
    commit order, which station sequences do not reflect."""
    ordered = list(reversed(updates))
    ordered.sort(key=lambda update: update.event_time, reverse=True)   # stable
    return ordered


def alert_text(item: InventoryItem) -> str:
    # The unit follows the minimum, so the plural rule applies to the minimum.
    return (f"{item.name} below minimum "
            f"({item.quantity:f} / {_quantity_text(item.minimum_quantity, item.unit)})")


def format_utc(moment: datetime, now: datetime) -> str:
    if moment.tzinfo is None or now.tzinfo is None:
        raise ValueError("times must be timezone-aware")
    utc = moment.astimezone(timezone.utc)
    if utc.date() == today_utc(now):
        return utc.strftime("%H:%M UTC")
    return utc.strftime("%Y-%m-%d %H:%M UTC")


# --------------------------------------------------------------------------
# Storage encoding (private): tagged JSON for the types above, shared by
# the Onboard Store and the Earth Store so both read and write one format
# --------------------------------------------------------------------------

def _encode(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Enum):
        return {"$enum": type(value).__name__, "v": value.value}
    if isinstance(value, Decimal):
        return {"$dec": str(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("times must be timezone-aware UTC")
        return {"$dt": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, UUID):
        return {"$uuid": str(value)}
    if isinstance(value, bytes):
        return {"$bytes": value.hex()}
    if isinstance(value, (tuple, list)):
        return {"$tuple": [_encode(v) for v in value]}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {"$dc": type(value).__name__,
                "f": {f.name: _encode(getattr(value, f.name)) for f in dataclasses.fields(value)}}
    if isinstance(value, dict) or hasattr(value, "items"):
        return {"$map": [[_encode(k), _encode(v)] for k, v in value.items()]}
    raise TypeError(f"cannot store value of type {type(value).__name__}")


def _domain_type(name: str) -> type:
    cls = globals().get(name)
    if not isinstance(cls, type):
        raise TypeError(f"unknown stored type {name!r}")
    return cls


def _decode(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    if "$enum" in value:
        return _domain_type(value["$enum"])(value["v"])
    if "$dec" in value:
        return Decimal(value["$dec"])
    if "$dt" in value:
        return datetime.fromisoformat(value["$dt"])
    if "$date" in value:
        return date.fromisoformat(value["$date"])
    if "$uuid" in value:
        return UUID(value["$uuid"])
    if "$bytes" in value:
        return bytes.fromhex(value["$bytes"])
    if "$tuple" in value:
        return tuple(_decode(v) for v in value["$tuple"])
    if "$dc" in value:
        cls = _domain_type(value["$dc"])
        return cls(**{k: _decode(v) for k, v in value["f"].items()})
    if "$map" in value:
        return {_decode(k): _decode(v) for k, v in value["$map"]}
    raise TypeError("unrecognized stored value")


def _dumps(obj: Any) -> str:
    return json.dumps(_encode(obj), separators=(",", ":"), sort_keys=True)


def _loads(text: str) -> Any:
    return _decode(json.loads(text))
