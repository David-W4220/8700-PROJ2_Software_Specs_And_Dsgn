"""Mission Service: mission lifecycle, manifest versions, loading, dispatch,
receipts and discrepancies (FR-013–FR-026, mission state machine)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from ssir.domain_rules import _validate_lines
from ssir.domain_rules import (
    AlertCoverage, CargoManifest, Discrepancy, InvalidTransition, LoadingIssue,
    LoadingReviewLine, ManifestDraft, ManifestLine, ManifestTotals, MissionStatus, Outcome,
    Action, ReceiptUnit, ResupplyMission, StaleState, StatusHistoryEntry, Transition, User,
    ValidationError, alert_coverage, dispatch_failures, loading_review, manifest_changed,
    manifest_totals, next_status, require_permission, submission_failures, validate_capacities,
    validate_loaded_quantity, validate_text,
)
from ssir.domain_rules import NotFound
from ssir.earth.earth_store import EarthStore, EarthTx
from ssir.earth.inventory_service import InventoryService


@dataclass(frozen=True)
class ManifestEditorView:
    mission: ResupplyMission
    manifest: CargoManifest
    totals: ManifestTotals
    alerts: tuple[AlertCoverage, ...]


@dataclass(frozen=True)
class DispatchResult:
    mission: ResupplyMission
    shortfall_warnings: tuple[LoadingReviewLine, ...]


def _capacity_failures(tx: EarthTx, mission: ResupplyMission) -> list[str]:
    """FR-017 checks against the current manifest and current item data."""
    draft = tx.get_manifest(mission.mission_id)
    items = {item.item_id: item for item in tx.list_items()}
    totals = manifest_totals(draft.lines, items, draft.mass_capacity_kg, draft.volume_capacity_m3)
    return submission_failures(draft.lines, totals)


def _reason(reason: Optional[str]) -> str:
    try:
        return validate_text(reason, required=True)
    except ValidationError as exc:
        raise ValidationError([f"reason: {f}" for f in exc.args[0]]) from None


def _require_approved(mission: ResupplyMission, what: str) -> None:
    if mission.mission_status is not MissionStatus.APPROVED:
        raise InvalidTransition([f"can only {what} on an Approved mission, "
                                 f"not a {mission.mission_status.value} one"])


class MissionService:
    def __init__(self, store: EarthStore, inventory: InventoryService,
                 now: Callable[[], datetime]) -> None:
        self._store = store
        self._inventory = inventory
        self._now = now

    def _move(self, tx: EarthTx, mission: ResupplyMission, target: MissionStatus,
              actor: User, reason: Optional[str], **changes) -> ResupplyMission:
        """One status change with its history entry (time, user, reason; FR-024)."""
        entry = StatusHistoryEntry(target, self._now(), actor.user_id, reason)
        tx.put_mission(replace(mission, mission_status=target,
                               status_history=mission.status_history + (entry,), **changes))
        return tx.get_mission(mission.mission_id)

    # planning
    def create_mission(self, actor: User, mass_capacity_kg: Decimal,
                       volume_capacity_m3: Decimal) -> ResupplyMission:
        validate_capacities(mass_capacity_kg, volume_capacity_m3)
        now = self._now()
        with self._store.transaction() as tx:
            mission_id = tx.next_mission_id()              # server-set (FR-014)
            mission = ResupplyMission(
                mission_id=mission_id, mission_status=MissionStatus.DRAFT,
                mass_capacity_kg=mass_capacity_kg, volume_capacity_m3=volume_capacity_m3,
                expected_arrival=None, dispatched_at=None, receipt_id=None, manifest_version=1,
                status_history=(StatusHistoryEntry(MissionStatus.DRAFT, now, actor.user_id, None),))
            tx.put_mission(mission)
            tx.append_manifest_version(mission_id, 1, ManifestDraft(
                lines=(), mass_capacity_kg=mass_capacity_kg,
                volume_capacity_m3=volume_capacity_m3, expected_arrival=None))
            return tx.get_mission(mission_id)

    def save_manifest(self, actor: User, mission_id: str, base_version: int,
                      draft: ManifestDraft) -> CargoManifest:
        with self._store.transaction() as tx:
            mission = tx.get_mission(mission_id, for_update=True)
            if base_version != mission.manifest_version:
                raise StaleState([f"{mission_id} manifest is at version {mission.manifest_version}, "
                                  f"not {base_version}"])
            current = tx.get_manifest(mission_id)
            status = mission.mission_status
            if status is MissionStatus.DRAFT:
                proposed = replace(draft, lines=tuple(
                    ManifestLine(line.item_id, line.line_quantity, None, None) for line in draft.lines))
                validate_capacities(proposed.mass_capacity_kg, proposed.volume_capacity_m3)
                _validate_lines(proposed.lines, {i.item_id: i for i in tx.list_items()})
            elif status is MissionStatus.APPROVED:
                # Only the expected arrival may change on an Approved mission (FR-016).
                proposed = replace(current, expected_arrival=draft.expected_arrival)
                if manifest_changed(proposed, draft):
                    raise InvalidTransition(["only the expected arrival can change on an Approved mission"])
            else:
                raise InvalidTransition([f"the manifest of a {status.value} mission cannot change"])
            if not manifest_changed(current, proposed):
                return CargoManifest(mission_id, mission.manifest_version, current.lines)
            version = mission.manifest_version + 1
            tx.append_manifest_version(mission_id, version, proposed)
            tx.put_mission(replace(mission, mass_capacity_kg=proposed.mass_capacity_kg,
                                   volume_capacity_m3=proposed.volume_capacity_m3,
                                   expected_arrival=proposed.expected_arrival,
                                   manifest_version=version))
            return CargoManifest(mission_id, version, proposed.lines)

    def manifest_editor(self, mission_id: str) -> ManifestEditorView:
        with self._store.transaction() as tx:
            mission = tx.get_mission(mission_id)
            draft = tx.get_manifest(mission_id)
            items = {item.item_id: item for item in tx.list_items()}
            alerts = tx.list_active_alerts()
        planned = {line.item_id: line.line_quantity for line in draft.lines}
        return ManifestEditorView(
            mission=mission,
            manifest=CargoManifest(mission_id, mission.manifest_version, draft.lines),
            totals=manifest_totals(draft.lines, items, draft.mass_capacity_kg, draft.volume_capacity_m3),
            alerts=tuple(AlertCoverage(a, alert_coverage(items[a.item_id], planned.get(a.item_id)))
                         for a in alerts if a.item_id in items))

    # lifecycle
    def submit(self, actor: User, mission_id: str) -> ResupplyMission:
        with self._store.transaction() as tx:
            mission = tx.get_mission(mission_id, for_update=True)
            target = next_status(mission.mission_status, Transition.SUBMIT)
            failures = _capacity_failures(tx, mission)   # every failing check (FR-017)
            if failures:
                raise ValidationError(failures)
            return self._move(tx, mission, target, actor, None)

    def approve(self, actor: User, mission_id: str) -> ResupplyMission:
        with self._store.transaction() as tx:
            mission = tx.get_mission(mission_id, for_update=True)
            target = next_status(mission.mission_status, Transition.APPROVE)
            failures = _capacity_failures(tx, mission)   # capacity re-checked (FR-018)
            if failures:
                raise ValidationError(failures)
            return self._move(tx, mission, target, actor, None)

    def return_to_draft(self, actor: User, mission_id: str, reason: str) -> ResupplyMission:
        with self._store.transaction() as tx:
            mission = tx.get_mission(mission_id, for_update=True)
            target = next_status(mission.mission_status, Transition.RETURN)
            return self._move(tx, mission, target, actor, _reason(reason))

    def reopen(self, actor: User, mission_id: str, reason: str) -> ResupplyMission:
        require_permission(actor, Action.REOPEN_MISSION)          # canReopen (FR-020)
        with self._store.transaction() as tx:
            mission = tx.get_mission(mission_id, for_update=True)
            target = next_status(mission.mission_status, Transition.REOPEN)
            text = _reason(reason)
            # Loaded quantities are cleared; loading issues are kept. Decision
            # (Nov 16, 2026, Claude): reopening creates no manifest version.
            tx.clear_loaded_quantities(mission_id)
            return self._move(tx, mission, target, actor, text)

    def cancel(self, actor: User, mission_id: str, reason: str) -> ResupplyMission:
        with self._store.transaction() as tx:
            mission = tx.get_mission(mission_id, for_update=True)
            target = next_status(mission.mission_status, Transition.CANCEL)
            return self._move(tx, mission, target, actor, _reason(reason))

    # loading and dispatch
    def record_loaded_quantity(self, actor: User, mission_id: str, item_id: str,
                               loaded_quantity: Decimal) -> CargoManifest:
        with self._store.transaction() as tx:
            mission = tx.get_mission(mission_id, for_update=True)
            _require_approved(mission, "record loaded quantities")
            draft = tx.get_manifest(mission_id)
            if item_id not in {line.item_id for line in draft.lines}:
                raise NotFound([f"{mission_id} has no line for {item_id}"])
            validate_loaded_quantity(loaded_quantity, tx.get_item(item_id).unit)
            tx.set_loaded_quantity(mission_id, item_id, loaded_quantity)
            return CargoManifest(mission_id, mission.manifest_version, tx.get_manifest(mission_id).lines)

    def add_loading_issue(self, actor: User, mission_id: str, text: str) -> LoadingIssue:
        with self._store.transaction() as tx:
            mission = tx.get_mission(mission_id, for_update=True)
            # Decision (Nov 16, 2026, Claude): issues are noted during loading review,
            # i.e. while the mission is Approved (FR-022).
            _require_approved(mission, "note loading issues")
            issue = LoadingIssue(mission_id, validate_text(text, required=True),
                                 actor.user_id, self._now())
            tx.append_loading_issue(issue)
            return issue

    def loading_review(self, mission_id: str) -> list[LoadingReviewLine]:
        with self._store.transaction() as tx:
            tx.get_mission(mission_id)
            return loading_review(tx.get_manifest(mission_id).lines)

    def confirm_dispatch(self, actor: User, mission_id: str) -> DispatchResult:
        with self._store.transaction() as tx:
            mission = tx.get_mission(mission_id, for_update=True)
            target = next_status(mission.mission_status, Transition.CONFIRM_DISPATCH)
            lines = tx.get_manifest(mission_id).lines
            failures = dispatch_failures(lines, mission.expected_arrival)
            if failures:
                raise ValidationError(failures)
            shortfalls = tuple(r for r in loading_review(lines) if r.missing > 0)  # warning only (FR-023)
            shipped = self._move(tx, mission, target, actor, None, dispatched_at=self._now())
            return DispatchResult(mission=shipped, shortfall_warnings=shortfalls)

    # receipt and discrepancies
    def apply_receipt(self, tx: EarthTx, receipt: ReceiptUnit, signer: User) -> Outcome:
        raise NotImplementedError

    def resolve_discrepancy(self, actor: User, discrepancy_id: str,
                            note: str) -> Discrepancy:
        raise NotImplementedError

    # queries
    def get_mission(self, mission_id: str) -> ResupplyMission:
        with self._store.transaction() as tx:
            return tx.get_mission(mission_id)

    def list_missions(self) -> list[ResupplyMission]:
        with self._store.transaction() as tx:
            return tx.list_missions()

    def get_manifest(self, mission_id: str, version: Optional[int] = None) -> CargoManifest:
        with self._store.transaction() as tx:
            mission = tx.get_mission(mission_id)
            draft = tx.get_manifest(mission_id, version)
            return CargoManifest(mission_id, version or mission.manifest_version, draft.lines)

    def list_loading_issues(self, mission_id: str) -> list[LoadingIssue]:
        with self._store.transaction() as tx:
            tx.get_mission(mission_id)
            return tx.list_loading_issues(mission_id)

    def list_discrepancies(self, mission_id: str) -> list[Discrepancy]:
        raise NotImplementedError
