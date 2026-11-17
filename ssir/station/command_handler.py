"""Station Command Handler: validate and commit each crew action as one
onboard transaction (FR-006–FR-009, FR-025–FR-027, NFR-001, K3)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Mapping, Optional, Sequence, Union
from uuid import UUID, uuid4

from ssir.domain_rules import (
    Action, AlertChange, AlertStatus, CorrectionField, Discrepancy, FieldValue,
    InventoryItem, InventoryUpdate, ReceiptUnit, ResupplyMission, SupplyAlert,
    SyncStatus, UnlistedItem, UpdateField, UpdateType, canonical_update_content,
    evaluate_alert, parse_condition, require_permission, validate_condition_change,
    validate_correction, validate_move, validate_text, validate_usage,
)
from ssir.domain_rules import (
    MissionStatus, StatusHistoryEntry, Transition, canonical_receipt_content, next_status,
    receipt_discrepancies, validate_receipt,
)
from ssir.station.clock import StationClock
from ssir.station.identity import Session, StationIdentity
from ssir.station.onboard_store import STATION_DISPLAY_PREFIX, OnboardStore, StationWriteTx


@dataclass(frozen=True)
class CommandResult:
    update: InventoryUpdate
    item: InventoryItem
    alert_change: AlertChange


@dataclass(frozen=True)
class ReceiptResult:
    receipt: ReceiptUnit
    mission: ResupplyMission
    discrepancies: tuple[Discrepancy, ...]
    alert_changes: Mapping[str, AlertChange]


class StationCommandHandler:
    def __init__(self, store: OnboardStore, identity: StationIdentity,
                 clock: StationClock) -> None:
        self._store = store
        self._identity = identity
        self._clock = clock

    def sign_in(self, user_id: str, secret: str) -> Session:
        return self._identity.sign_in(user_id, secret, self._clock.now())

    def sign_out(self, session: Session) -> None:
        self._identity.sign_out(session)

    def record_usage(self, session: Session, item_id: str, amount: Decimal,
                     reason: Optional[str]) -> CommandResult:
        require_permission(session.user, Action.RECORD_USAGE)
        with self._store.write() as tx:
            item = tx.get_item(item_id)               # current quantity, inside the write (NFR-001)
            validate_usage(item, amount, reason)
            new_item = replace(item, quantity=item.quantity - amount)
            return self._commit(tx, session, item, new_item, UpdateType.USAGE, UpdateField.QUANTITY,
                                item.quantity, new_item.quantity, -amount,
                                validate_text(reason, required=True))

    # -- one crew action = one transaction (K3, flow steps 3-8) ----------------

    def _commit(self, tx: StationWriteTx, session: Session, item: InventoryItem,
                new_item: InventoryItem, update_type: UpdateType, field: UpdateField,
                old_value: FieldValue, new_value: FieldValue,
                quantity_delta: Optional[Decimal], reason: Optional[str],
                receipt_id: Optional[UUID] = None,
                now: Optional[datetime] = None) -> CommandResult:
        now = now or self._clock.now()
        sequence = tx.next_sequence()
        update = InventoryUpdate(
            update_id=uuid4(), display_id=f"{STATION_DISPLAY_PREFIX}{sequence}",
            item_id=item.item_id, type=update_type, field=field,
            old_value=old_value, new_value=new_value, quantity_delta=quantity_delta,
            reason=reason, event_time=now,
            base_version=tx.earth_base(item.item_id).record_version,
            sync_status=SyncStatus.AWAITING_SYNC, signature=None, sequence=sequence,
            receipt_id=receipt_id, recorded_by=None, received_at=None, rejected_at=None)
        signature = self._identity.sign(session, canonical_update_content(update))
        # The station's own copy names the signer; Earth ignores this server-set
        # field and takes recordedBy from the signature (FR-032, K10).
        stored = tx.append_update(replace(update, signature=signature,
                                          recorded_by=session.user.user_id))
        tx.put_item(new_item)
        change = self._apply_alert(tx, new_item, now)
        return CommandResult(update=stored, item=new_item, alert_change=change)

    @staticmethod
    def _apply_alert(tx: StationWriteTx, item: InventoryItem, now: datetime) -> AlertChange:
        """Alert evaluated in the same transaction as the change (K20, FR-012)."""
        active = tx.get_active_alert(item.item_id)
        change = evaluate_alert(item, active)
        if change is AlertChange.RAISE:
            tx.put_alert(SupplyAlert(alert_id=uuid4().hex, item_id=item.item_id,
                                     alert_status=AlertStatus.ACTIVE, raised_at=now,
                                     resolved_at=None))
        elif change is AlertChange.RESOLVE and active is not None:
            tx.put_alert(replace(active, alert_status=AlertStatus.RESOLVED, resolved_at=now))
        return change

    def move_item(self, session: Session, item_id: str, location_id: str) -> CommandResult:
        require_permission(session.user, Action.MOVE_ITEM)
        with self._store.write() as tx:
            item = tx.get_item(item_id)
            validate_move(item, location_id, tx.list_locations())
            new_item = replace(item, stored_at=location_id)
            return self._commit(tx, session, item, new_item, UpdateType.MOVE, UpdateField.LOCATION,
                                item.stored_at, location_id, None, None)

    def set_condition(self, session: Session, item_id: str, condition: str,
                      reason: Optional[str]) -> CommandResult:
        require_permission(session.user, Action.SET_CONDITION)
        parsed = parse_condition(condition)
        with self._store.write() as tx:
            item = tx.get_item(item_id)
            validate_condition_change(item, parsed, reason)
            new_item = replace(item, condition=parsed)
            return self._commit(tx, session, item, new_item, UpdateType.CONDITION,
                                UpdateField.CONDITION, item.condition.value, parsed.value, None,
                                validate_text(reason, required=True))

    def correct_item(self, session: Session, item_id: str, field: CorrectionField,
                     new_value: Union[Decimal, date], reason: Optional[str]) -> CommandResult:
        require_permission(session.user, Action.CORRECT_ITEM)
        with self._store.write() as tx:
            item = tx.get_item(item_id)
            validate_correction(item, field, new_value, reason)
            if field is CorrectionField.QUANTITY:
                new_item = replace(item, quantity=new_value)
                update_field, old_value = UpdateField.QUANTITY, item.quantity
            else:
                new_item = replace(item, expiry_date=new_value)
                update_field, old_value = UpdateField.EXPIRY_DATE, item.expiry_date
            # A correction sets an absolute value (FR-030), so it carries no delta.
            return self._commit(tx, session, item, new_item, UpdateType.CORRECTION, update_field,
                                old_value, new_value, None, validate_text(reason, required=True))

    def record_receipt(self, session: Session, mission_id: str,
                       received: Mapping[str, Decimal],
                       unlisted: Sequence[UnlistedItem]) -> ReceiptResult:
        """One commit (FR-025, NFR-001, K3): mission Received with a new receiptId,
        one signed Receipt update per line received above 0, discrepancies and
        alert changes; then the receipt unit, signed, takes the next sequence."""
        require_permission(session.user, Action.RECORD_RECEIPT)
        with self._store.write() as tx:
            now = self._clock.now()
            tx.stamp(now)
            mission = tx.get_mission(mission_id)
            target = next_status(mission.mission_status, Transition.RECORD_RECEIPT)
            lines = tx.get_manifest(mission_id).lines
            items = {item.item_id: item for item in tx.list_items()}
            validate_receipt(lines, received, unlisted, items)
            receipt_id = uuid4()
            updates, changes = [], {}
            for line in lines:
                quantity = received[line.item_id]
                if quantity <= 0:
                    continue
                item = tx.get_item(line.item_id)
                new_item = replace(item, quantity=item.quantity + quantity)
                result = self._commit(tx, session, item, new_item, UpdateType.RECEIPT,
                                      UpdateField.QUANTITY, item.quantity, new_item.quantity,
                                      quantity, None, receipt_id=receipt_id, now=now)
                updates.append(result.update)
                changes[line.item_id] = result.alert_change
            discrepancies = receipt_discrepancies(mission_id, lines, received, unlisted)
            for discrepancy in discrepancies:
                tx.append_discrepancy(discrepancy)
            entry = StatusHistoryEntry(target, now, session.user.user_id, None)
            received_mission = replace(mission, mission_status=target, receipt_id=receipt_id,
                                       status_history=mission.status_history + (entry,))
            tx.put_mission(received_mission)
            unit = ReceiptUnit(
                receipt_id=receipt_id, mission_id=mission_id, received=dict(received),
                unlisted=tuple(unlisted), updates=tuple(updates),
                discrepancies=tuple(discrepancies), event_time=now, signature=None,
                sequence=tx.next_sequence(), sync_status=SyncStatus.AWAITING_SYNC)
            unit = replace(unit, signature=self._identity.sign(session, canonical_receipt_content(unit)))
            stored = tx.append_receipt(unit)
            return ReceiptResult(receipt=stored, mission=received_mission,
                                 discrepancies=tuple(discrepancies), alert_changes=changes)
