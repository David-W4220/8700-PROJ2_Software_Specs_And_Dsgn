"""Domain Rules: the business rules defined once and used by both sites.

Every function here is side-effect free. "Now" and "today" are always passed in
(K17); nothing in this module reads a clock. The data types below are the
spec's Domain Model plus the shared sync wire types, kept here because this is
the only module both sites depend on.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Mapping, Optional, Protocol, Sequence, Union
from uuid import UUID

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
    raise NotImplementedError


def validate_amount(amount: Decimal, unit: Unit) -> None:
    raise NotImplementedError


def validate_usage(item: InventoryItem, amount: Decimal, reason: Optional[str]) -> None:
    raise NotImplementedError


def validate_move(item: InventoryItem, location_id: str,
                  locations: Sequence[StorageLocation]) -> None:
    raise NotImplementedError


def parse_condition(value: str) -> Condition:
    raise NotImplementedError


def validate_condition_change(item: InventoryItem, condition: Condition,
                              reason: Optional[str]) -> None:
    raise NotImplementedError


def validate_correction(item: InventoryItem, field: CorrectionField,
                        new_value: Union[Decimal, date], reason: Optional[str]) -> None:
    raise NotImplementedError


def validate_item_data(item: InventoryItem, others: Sequence[InventoryItem],
                       locations: Sequence[StorageLocation]) -> None:
    raise NotImplementedError


def validate_capacities(mass_capacity_kg: Decimal, volume_capacity_m3: Decimal) -> None:
    raise NotImplementedError


def validate_event_time(event_time: datetime, now: datetime) -> None:
    raise NotImplementedError


def validate_base_version(base_version: int, current_version: int) -> None:
    raise NotImplementedError


def validate_loaded_quantity(quantity: Decimal, unit: Unit) -> None:
    raise NotImplementedError


def validate_receipt(lines: Sequence[ManifestLine], received: Mapping[str, Decimal],
                     unlisted: Sequence[UnlistedItem],
                     items: Mapping[str, InventoryItem]) -> None:
    raise NotImplementedError


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
    raise NotImplementedError


def alert_coverage(item: InventoryItem, line_quantity: Optional[Decimal]) -> Coverage:
    raise NotImplementedError


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
            [f"cannot {transition.value} a mission that is {current.value}"]) from None


def manifest_totals(lines: Sequence[ManifestLine], items: Mapping[str, InventoryItem],
                    mass_capacity_kg: Decimal, volume_capacity_m3: Decimal) -> ManifestTotals:
    raise NotImplementedError


def manifest_changed(current: ManifestDraft, proposed: ManifestDraft) -> bool:
    raise NotImplementedError


def submission_failures(lines: Sequence[ManifestLine], totals: ManifestTotals) -> list[str]:
    raise NotImplementedError


def dispatch_failures(lines: Sequence[ManifestLine],
                      expected_arrival: Optional[datetime]) -> list[str]:
    raise NotImplementedError


def loading_review(lines: Sequence[ManifestLine]) -> list[LoadingReviewLine]:
    raise NotImplementedError


def receipt_discrepancies(mission_id: str, lines: Sequence[ManifestLine],
                          received: Mapping[str, Decimal],
                          unlisted: Sequence[UnlistedItem]) -> list[Discrepancy]:
    raise NotImplementedError


# --------------------------------------------------------------------------
# Synchronization
# --------------------------------------------------------------------------

def merge_or_conflict(update: InventoryUpdate, item: InventoryItem,
                      earth_changes_since_base: Sequence[FieldChange]) -> MergeResult:
    raise NotImplementedError


def canonical_update_content(update: InventoryUpdate) -> bytes:
    raise NotImplementedError


def canonical_receipt_content(receipt: ReceiptUnit) -> bytes:
    raise NotImplementedError


def rejected_still_listed(rejected_at: datetime, now: datetime) -> bool:
    raise NotImplementedError


def earth_link_available(session_open: bool, last_station_contact: Optional[datetime],
                         now: datetime) -> bool:
    raise NotImplementedError


# --------------------------------------------------------------------------
# Dashboard, history and display
# --------------------------------------------------------------------------

def order_alerts(alerts: Sequence[SupplyAlert],
                 items: Mapping[str, InventoryItem]) -> list[SupplyAlert]:
    raise NotImplementedError


def next_mission(missions: Sequence[ResupplyMission]) -> Optional[ResupplyMission]:
    raise NotImplementedError


def recent_activity(events: Sequence[ActivityEvent], now: datetime) -> list[ActivityEvent]:
    raise NotImplementedError


def order_history(updates: Sequence[InventoryUpdate]) -> list[InventoryUpdate]:
    raise NotImplementedError


def alert_text(item: InventoryItem) -> str:
    raise NotImplementedError


def format_utc(moment: datetime, now: datetime) -> str:
    raise NotImplementedError
