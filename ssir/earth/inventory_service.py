"""Inventory Service: authoritative item state, version checks, merge or
conflict, resolutions, alerts and item history (FR-009–FR-012, FR-030, FR-031)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from uuid import uuid4
from decimal import Decimal
from typing import Callable, Optional, Sequence, Union
from uuid import UUID

from ssir.domain_rules import (
    AlertChange, AlertStatus, Condition, FieldChange, NotFound, StaleState, SyncStatus,
    UpdateField, UpdateType, ValidationError, evaluate_alert, filter_items, order_history,
    today_utc,
    validate_correction, validate_item_data, validate_text,
)
from ssir.domain_rules import (
    ConflictRecord, CorrectionField, Criticality, InventoryFilter, InventoryItem,
    InventoryUpdate, Outcome, ResolutionChoice, StorageLocation, SupplyAlert,
    Unit, User,
)
from ssir.earth.earth_store import EarthStore, EarthTx


@dataclass(frozen=True)
class NewItem:
    item_id: str
    name: str
    barcodes: tuple[str, ...]
    quantity: Decimal
    unit: Unit
    expiry_date: Optional[date]
    unit_mass_kg: Decimal
    unit_volume_m3: Decimal
    minimum_quantity: Decimal
    criticality: Criticality
    stored_at: str


@dataclass(frozen=True)
class ItemEdit:
    """Fields a planner may edit (FR-010); None means unchanged."""
    name: Optional[str] = None
    barcodes: Optional[tuple[str, ...]] = None
    minimum_quantity: Optional[Decimal] = None
    criticality: Optional[Criticality] = None
    unit_mass_kg: Optional[Decimal] = None
    unit_volume_m3: Optional[Decimal] = None


def _check_version(item: InventoryItem, expected_version: int) -> None:
    """A change based on an out-of-date version is rejected (FR-032)."""
    if expected_version != item.record_version:
        raise StaleState([f"{item.item_id} is at version {item.record_version}, "
                          f"not {expected_version}"])


def _apply_alert(tx: EarthTx, item: InventoryItem, now: datetime) -> AlertChange:
    """Earth-side alert, evaluated in the same transaction (K20, FR-012)."""
    active = tx.get_active_alert(item.item_id)
    change = evaluate_alert(item, active)
    if change is AlertChange.RAISE:
        tx.put_alert(SupplyAlert(alert_id=uuid4().hex, item_id=item.item_id,
                                 alert_status=AlertStatus.ACTIVE, raised_at=now, resolved_at=None))
    elif change is AlertChange.RESOLVE and active is not None:
        tx.put_alert(replace(active, alert_status=AlertStatus.RESOLVED, resolved_at=now))
    return change


class InventoryService:
    def __init__(self, store: EarthStore, now: Callable[[], datetime]) -> None:
        self._store = store
        self._now = now

    # station updates (called by Sync Endpoint / Mission Service)
    def apply_station_update(self, tx: EarthTx, update: InventoryUpdate,
                             signer: User) -> Outcome:
        raise NotImplementedError

    # Earth-side changes
    def correct_item(self, actor: User, item_id: str, field: CorrectionField,
                     new_value: Union[Decimal, date], reason: str,
                     expected_version: int) -> InventoryUpdate:
        now = self._now()
        with self._store.transaction() as tx:
            item = tx.get_item(item_id, for_update=True)
            _check_version(item, expected_version)
            validate_correction(item, field, new_value, reason)
            if field is CorrectionField.QUANTITY:
                changed, update_field, old_value = replace(item, quantity=new_value), UpdateField.QUANTITY, item.quantity
            else:
                changed, update_field, old_value = replace(item, expiry_date=new_value), UpdateField.EXPIRY_DATE, item.expiry_date
            stored_item = tx.put_item(changed)
            update = tx.append_update(InventoryUpdate(
                update_id=uuid4(), display_id="", item_id=item_id, type=UpdateType.CORRECTION,
                field=update_field, old_value=old_value, new_value=new_value, quantity_delta=None,
                reason=validate_text(reason, required=True), event_time=now,
                base_version=item.record_version, sync_status=SyncStatus.SYNCHRONIZED,
                signature=None, sequence=None, receipt_id=None, recorded_by=actor.user_id,
                received_at=now, rejected_at=None))
            tx.append_field_change(FieldChange(item_id=item_id, field=update_field,
                                               version=stored_item.record_version,
                                               from_this_station=False, update_id=update.update_id))
            _apply_alert(tx, stored_item, now)
            return update

    def create_item(self, actor: User, item: NewItem) -> InventoryItem:
        now = self._now()
        candidate = InventoryItem(
            item_id=item.item_id.strip(), name=item.name.strip(), barcodes=tuple(item.barcodes),
            quantity=item.quantity, unit=item.unit, condition=Condition.USABLE,
            expiry_date=item.expiry_date, unit_mass_kg=item.unit_mass_kg,
            unit_volume_m3=item.unit_volume_m3, minimum_quantity=item.minimum_quantity,
            criticality=item.criticality, stored_at=item.stored_at, record_version=0)
        with self._store.transaction() as tx:
            others = tx.list_items()
            if any(other.item_id == candidate.item_id for other in others):
                raise ValidationError([f"item {candidate.item_id} already exists"])
            validate_item_data(candidate, others, tx.list_locations())
            stored = tx.put_item(candidate)
            _apply_alert(tx, stored, now)
            return stored

    def edit_item(self, actor: User, item_id: str, edit: ItemEdit,
                  expected_version: int) -> InventoryItem:
        now = self._now()
        with self._store.transaction() as tx:
            item = tx.get_item(item_id, for_update=True)
            _check_version(item, expected_version)
            changes = {name: value for name, value in vars(edit).items() if value is not None}
            if "name" in changes:
                changes["name"] = changes["name"].strip()
            edited = replace(item, **changes)
            if edited == item:
                return item                    # no change keeps the version (as FR-016)
            validate_item_data(edited, tx.list_items(), tx.list_locations())
            stored = tx.put_item(edited)
            _apply_alert(tx, stored, now)      # a minimum change can raise or resolve (FR-012)
            return stored

    def create_location(self, actor: User, location_id: str, name: str) -> StorageLocation:
        clean_id = location_id.strip()
        if not clean_id:
            raise ValidationError(["location ID is required"])
        location = StorageLocation(location_id=clean_id, name=validate_text(name, required=True))
        with self._store.transaction() as tx:
            if any(loc.location_id == clean_id or loc.name == location.name
                   for loc in tx.list_locations()):
                raise ValidationError([f"location {clean_id} or {location.name} already exists"])
            tx.put_location(location)
        return location

    def resolve_conflict(self, actor: User, update_id: UUID, choice: ResolutionChoice,
                         reason: str) -> InventoryUpdate:
        raise NotImplementedError

    # queries
    def get_item(self, item_id: str) -> InventoryItem:
        with self._store.transaction() as tx:
            return tx.get_item(item_id)

    def search_items(self, query: str, item_filter: InventoryFilter) -> list[InventoryItem]:
        today = today_utc(self._now())
        with self._store.transaction() as tx:
            items = tx.list_items()
        result = filter_items(items, query, item_filter, today)
        # Same order as station S2 (decision, slice 3): by name, then ID.
        result.sort(key=lambda item: (item.name.casefold(), item.item_id))
        return result

    def item_history(self, item_id: str) -> list[InventoryUpdate]:
        with self._store.transaction() as tx:
            tx.get_item(item_id)                       # NotFound for an unknown item
            return order_history(tx.item_history(item_id))

    def active_alerts(self) -> list[SupplyAlert]:
        with self._store.transaction() as tx:
            return tx.list_active_alerts()

    def open_conflicts(self) -> list[ConflictRecord]:
        raise NotImplementedError

    def list_locations(self) -> list[StorageLocation]:
        with self._store.transaction() as tx:
            return tx.list_locations()
