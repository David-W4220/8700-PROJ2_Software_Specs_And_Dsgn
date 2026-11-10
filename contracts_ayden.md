# Contracts: Space Station Inventory and Resupply (skeleton)

Based on `spec_ayden.md` (revised Nov 2, 2026) and `architecture_ayden.md`. Every function body raises `NotImplementedError`; constructors only store what is injected.

## Conventions

- **Failure.** Errors are the classes in `ssir.domain_rules`. Each carries a list of human-readable failures in `args[0]`. `ValidationError` = input breaks a rule. `Forbidden` = role or `canReopen` does not allow it. `Unauthenticated` = no valid identity or signature. `NotFound` = unknown ID. `InvalidTransition` = not in the mission state machine. `StaleState` = based on an out-of-date version or status, or a second resolution.
- **Atomicity.** A function that fails writes nothing (NFR-001). "Commits" means one Onboard Store write transaction on the station, or one Earth Store transaction on Earth.
- **Injected.** "—" means pure: no clock, store or I/O. Time is never read inside Domain Rules; callers pass `now` or `today` (K17). On the station the clock is the injected `StationClock` (K15). On Earth it is an injected `now: Callable[[], datetime]` returning UTC.
- **Quantities** are `Decimal`; **times** are timezone-aware UTC `datetime`.

## Layout

| Architecture module | Python module |
|---|---|
| Screens | `ssir/screens.py` |
| Domain Rules | `ssir/domain_rules.py` |
| Station Identity | `ssir/station/identity.py` |
| Station Clock | `ssir/station/clock.py` |
| Station Command Handler | `ssir/station/command_handler.py` |
| Onboard Store | `ssir/station/onboard_store.py` |
| Sync Agent | `ssir/station/sync_agent.py` |
| Earth Gateway | `ssir/earth/gateway.py` |
| Sync Endpoint | `ssir/earth/sync_endpoint.py` |
| Inventory Service | `ssir/earth/inventory_service.py` |
| Mission Service | `ssir/earth/mission_service.py` |
| Earth Store | `ssir/earth/earth_store.py` |

---

## Domain Rules (`ssir.domain_rules`)

Holds the spec's Domain Model as frozen dataclasses and enums, the sync wire types (`Handshake`, `HandshakeReply`, `Outcome`, `Change`, `ChangeBatch`), the error classes, the `IdentityDirectory` interface of the external identity system, and the spec constants. All functions are pure; **Injected: — for every row.**

| Signature | Success result | How it fails | Spec rule |
|---|---|---|---|
| `validate_text(text: Optional[str], *, required: bool) -> Optional[str]` | Trimmed text (or `None` when not required and empty) | `ValidationError` if required and empty after trimming, or over 1,000 characters | FR-032; required reasons in FR-006, FR-008, FR-009, FR-019–FR-021, FR-031 |
| `validate_amount(amount: Decimal, unit: Unit) -> None` | Returns | `ValidationError` if ≤ 0, fractional for a countable unit, or more than 3 decimals | Unit; FR-006 |
| `validate_usage(item: InventoryItem, amount: Decimal, reason: Optional[str]) -> None` | Returns | `ValidationError` listing: bad amount, amount > current quantity, missing reason | FR-006; AC-006 |
| `validate_move(item: InventoryItem, location_id: str, locations: Sequence[StorageLocation]) -> None` | Returns | `ValidationError` if the location is unknown or is the current one | FR-007; AC-007 |
| `parse_condition(value: str) -> Condition` | `Condition.USABLE` or `Condition.DAMAGED` | `ValidationError` for any other value | FR-008; AC-008 |
| `validate_condition_change(item: InventoryItem, condition: Condition, reason: Optional[str]) -> None` | Returns | `ValidationError` if reason is missing | FR-008 |
| `validate_correction(item: InventoryItem, field: CorrectionField, new_value: Decimal \| date, reason: Optional[str]) -> None` | Returns | `ValidationError` if quantity < 0 or breaks the unit rule, value type does not fit the field, or reason missing | FR-009; InventoryItem (`quantity` ≥ 0) |
| `validate_item_data(item: InventoryItem, others: Sequence[InventoryItem], locations: Sequence[StorageLocation]) -> None` | Returns | `ValidationError` if a barcode is used by another item, quantity < 0, minimum < 0, unit mass or volume < 0, unknown location, or text too long | FR-010; InventoryItem |
| `validate_capacities(mass_capacity_kg: Decimal, volume_capacity_m3: Decimal) -> None` | Returns | `ValidationError` if either is ≤ 0 | ResupplyMission; FR-014; FR-032; AC-014 |
| `validate_event_time(event_time: datetime, now: datetime) -> None` | Returns | `ValidationError` if more than 5 minutes after `now` | FR-032; AC-032 |
| `validate_base_version(base_version: int, current_version: int) -> None` | Returns | `ValidationError` if `base_version` > `current_version` | FR-032; AC-032 |
| `validate_loaded_quantity(quantity: Decimal, unit: Unit) -> None` | Returns (may exceed planned) | `ValidationError` if < 0 or breaks the unit rule | FR-022 |
| `validate_receipt(lines: Sequence[ManifestLine], received: Mapping[str, Decimal], unlisted: Sequence[UnlistedItem], items: Mapping[str, InventoryItem]) -> None` | Returns | `ValidationError("Receipt requires actual delivered quantities")` if any line lacks a quantity; also any quantity < 0, unit rule broken, unlisted entry without text | FR-025; FR-026; AC-025 |
| `is_permitted(user: User, action: Action) -> bool` | `True` if the user's role (and `canReopen` for `REOPEN_MISSION`) allows the action | Never raises | FR-003; Actors; AC-003 |
| `require_permission(user: User, action: Action) -> None` | Returns | `Forbidden` when `is_permitted` is false | FR-003; FR-020; AC-003; AC-020 |
| `evaluate_alert(item: InventoryItem, active_alert: Optional[SupplyAlert]) -> AlertChange` | `RAISE` if quantity < minimum and no Active alert; `RESOLVE` if quantity ≥ minimum and an Active alert exists; else `NONE` | Never raises | FR-012; SupplyAlert; AC-012 |
| `alert_coverage(item: InventoryItem, line_quantity: Optional[Decimal]) -> Coverage` | `COVERED` if quantity + line quantity ≥ minimum, else `NOT_COVERED` | Never raises | FR-013; AC-013 |
| `today_utc(now: datetime) -> date` | The UTC date of `now` | `ValueError` if `now` is not timezone-aware | NFR-005 |
| `is_low_stock(item: InventoryItem) -> bool` | quantity < minimum | Never raises | FR-004 |
| `is_expired(item: InventoryItem, today: date) -> bool` | expiry date before `today` | Never raises | FR-004; NFR-005 |
| `matches_query(item: InventoryItem, query: str) -> bool` | Case-insensitive substring on name or ID, or exact barcode match; empty query matches all | Never raises | FR-004; AC-004 |
| `filter_items(items: Sequence[InventoryItem], query: str, item_filter: InventoryFilter, today: date) -> list[InventoryItem]` | Items matching the query and the one filter | Never raises | FR-004; AC-004 |
| `next_status(current: MissionStatus, transition: Transition) -> MissionStatus` | Target status of a listed transition | `InvalidTransition` for any transition not in the state machine (includes cancel from Shipped/Received/Cancelled) | Mission lifecycle; FR-021; AC-021 |
| `manifest_totals(lines: Sequence[ManifestLine], items: Mapping[str, InventoryItem], mass_capacity_kg: Decimal, volume_capacity_m3: Decimal) -> ManifestTotals` | Totals rounded to 2 decimals and over-capacity flags | `NotFound` if a line's item is missing from `items` | FR-015; AC-015 |
| `manifest_changed(current: ManifestDraft, proposed: ManifestDraft) -> bool` | `True` if lines, capacities or expected arrival differ | Never raises | FR-016; AC-016 |
| `submission_failures(lines: Sequence[ManifestLine], totals: ManifestTotals) -> list[str]` | Every failing check (no lines, mass exceeded, volume exceeded); empty list = submittable | Never raises | FR-017; AC-017 |
| `dispatch_failures(lines: Sequence[ManifestLine], expected_arrival: Optional[datetime]) -> list[str]` | Every failing check (line without loaded quantity, no expected arrival); empty = dispatchable | Never raises | FR-023; AC-023 |
| `loading_review(lines: Sequence[ManifestLine]) -> list[LoadingReviewLine]` | Planned, loaded and missing per line | Never raises | FR-022; FR-023 (shortfall warning); AC-022 |
| `receipt_discrepancies(mission_id: str, lines: Sequence[ManifestLine], received: Mapping[str, Decimal], unlisted: Sequence[UnlistedItem]) -> list[Discrepancy]` | One Open discrepancy per line where received ≠ planned, and one with `item_id=None` per unlisted item | Never raises (input already validated) | FR-026; AC-026 |
| `merge_or_conflict(update: InventoryUpdate, item: InventoryItem, earth_changes_since_base: Sequence[FieldChange]) -> MergeResult` | `APPLY` if base is current; `MERGE` if only other fields changed or the clash is Usage/Receipt deltas; `CONFLICT` if the same field changed from another source, a Correction meets any quantity change, or the result would be < 0. Changes with `from_this_station=True` are ignored | Never raises | FR-030; AC-030; Further decisions (source of every field change) |
| `canonical_update_content(update: InventoryUpdate) -> bytes` | Deterministic bytes covering every client-set field incl. `updateId`, sequence, `eventTime`, `baseVersion`; excludes signature and server-set fields | Never raises | NFR-003; architecture step 6 |
| `canonical_receipt_content(receipt: ReceiptUnit) -> bytes` | Same, for the whole receipt unit | Never raises | NFR-003; FR-025 |
| `rejected_still_listed(rejected_at: datetime, now: datetime) -> bool` | `True` within 7 days of Earth's rejection time | Never raises | FR-028; Spec issue 3 |
| `earth_link_available(session_open: bool, last_station_contact: Optional[datetime], now: datetime) -> bool` | `True` if a session is open or contact was within 60 s | Never raises | FR-002 |
| `order_alerts(alerts: Sequence[SupplyAlert], items: Mapping[str, InventoryItem]) -> list[SupplyAlert]` | Active alerts, Critical items first | `NotFound` if an alert's item is missing | FR-001; AC-001 |
| `next_mission(missions: Sequence[ResupplyMission]) -> Optional[ResupplyMission]` | Submitted/Approved/Shipped mission with earliest expected arrival, else most recently changed; `None` if none | Never raises | FR-001; AC-001 |
| `recent_activity(events: Sequence[ActivityEvent], now: datetime) -> list[ActivityEvent]` | Up to 10 newest events from the past 7 days | Never raises | FR-001 |
| `order_history(updates: Sequence[InventoryUpdate]) -> list[InventoryUpdate]` | Newest first by event time; ties by `sequence` (commit order on the showing side) | Never raises | FR-011; AC-011 |
| `alert_text(item: InventoryItem) -> str` | `"<item> below minimum (<qty> / <min> <unit>)"` | Never raises | FR-001; AC-001 |
| `format_utc(moment: datetime, now: datetime) -> str` | `HH:MM UTC` if same UTC day as `now`, else `YYYY-MM-DD HH:MM UTC` | `ValueError` if not timezone-aware | Description; AC-002 |

---

## Station Identity (`ssir.station.identity`)

`StationIdentity(store: OnboardStore)`. `Session` is a frozen dataclass (`session_id`, `user`, `started_at`).

| Signature | Success result | How it fails | Spec rule | Injected |
|---|---|---|---|---|
| `sign_in(user_id: str, secret: str, now: datetime) -> Session` | A session with the person's private key unlocked, checked offline against the last synced user record | `Unauthenticated` for unknown user, wrong secret, or all keys revoked | NFR-003; User; K9; flow step 1 | store; `now` passed in by Command Handler |
| `sign_out(session: Session) -> None` | Key locked; session ends | `Unauthenticated` if the session is not active | NFR-003; K9 | store |
| `sign(session: Session, content: bytes) -> Signature` | `Signature(key_id, value)` made with the session user's own key | `Unauthenticated` if the session has ended | NFR-003; AC-032; K9 | store |

## Station Clock (`ssir.station.clock`)

`StationClock(system_time: Callable[[], datetime], tolerance: timedelta = 30 s)`.

| Signature | Success result | How it fails | Spec rule | Injected |
|---|---|---|---|---|
| `now() -> datetime` | Corrected UTC time of the onboard host | Never raises | NFR-005; K15 | `system_time` |
| `apply_earth_time(earth_time: datetime, round_trip: timedelta) -> None` | Offset corrected; drift rate re-measured | `ValueError` if `earth_time` is not timezone-aware | NFR-005; K16; flow step 11 | `system_time` |
| `drift_bound() -> timedelta` | Time since last correction × measured drift rate | Never raises | NFR-005; K16 | `system_time` |
| `drift_warning() -> bool` | `True` when `drift_bound()` exceeds tolerance | Never raises | NFR-005 | `system_time` |

## Station Command Handler (`ssir.station.command_handler`)

`StationCommandHandler(store: OnboardStore, identity: StationIdentity, clock: StationClock)`. Each command is one write transaction: validate against the current quantity, stamp `eventTime` from the clock, assign sequence and `U…` display ID, set `baseVersion` to the item's last Earth version, sign, write item + update + alert change, commit (K3, flow steps 3–8). If any item in the command has an open conflict, the update is still saved and waits in the queue (FR-030).

| Signature | Success result | How it fails | Spec rule | Injected |
|---|---|---|---|---|
| `sign_in(user_id: str, secret: str) -> Session` | Session (delegates to Station Identity with `clock.now()`) | `Unauthenticated` | NFR-003 | identity, clock |
| `sign_out(session: Session) -> None` | Session ended | `Unauthenticated` | NFR-003 | identity |
| `record_usage(session: Session, item_id: str, amount: Decimal, reason: Optional[str]) -> CommandResult` | Committed Usage update (delta −amount, Awaiting sync), new item, alert change | `ValidationError` (FR-006 rules), `NotFound`, `Forbidden` (role), `Unauthenticated` | FR-006; FR-012; FR-027; AC-006; AC-027 | store, identity, clock |
| `move_item(session: Session, item_id: str, location_id: str) -> CommandResult` | Committed Move update | `ValidationError` (current or unknown location), `NotFound`, `Forbidden`, `Unauthenticated` | FR-007; AC-007 | store, identity, clock |
| `set_condition(session: Session, item_id: str, condition: str, reason: Optional[str]) -> CommandResult` | Committed Condition update | `ValidationError` (unknown condition, no reason), `NotFound`, `Forbidden`, `Unauthenticated` | FR-008; AC-008 | store, identity, clock |
| `correct_item(session: Session, item_id: str, field: CorrectionField, new_value: Decimal \| date, reason: Optional[str]) -> CommandResult` | Committed Correction update; alert raised/resolved | `ValidationError`, `NotFound`, `Forbidden`, `Unauthenticated` | FR-009; FR-012; AC-009 | store, identity, clock |
| `record_receipt(session: Session, mission_id: str, received: Mapping[str, Decimal], unlisted: Sequence[UnlistedItem]) -> ReceiptResult` | One commit: mission Received with new `receiptId`, one Receipt update per line with quantity > 0, discrepancies, alert changes, receipt unit Awaiting sync | `ValidationError` (missing/negative quantities), `InvalidTransition` (not Shipped), `NotFound`, `Forbidden`, `Unauthenticated` | FR-025; FR-026; NFR-001; AC-025; AC-026 | store, identity, clock |

## Onboard Store (`ssir.station.onboard_store`)

`OnboardStore(path: str)`. Writes are serialized across all devices (K1); `write()` commits durably on exit and rolls back on exception (K2). History content is insert-only (K18).

| Signature | Success result | How it fails | Spec rule | Injected |
|---|---|---|---|---|
| `OnboardStore.open() -> None` | Store ready; recovers from last durable commit | `OSError` if the file cannot be opened | NFR-001 | `path` |
| `OnboardStore.close() -> None` | Store closed | Never raises | NFR-001 | — |
| `OnboardStore.read() -> ContextManager[StationReadTx]` | A consistent read view | `RuntimeError` if not open | NFR-002 | — |
| `OnboardStore.write() -> ContextManager[StationWriteTx]` | A serialized write; durable on successful exit | `RuntimeError` if not open; any exception inside aborts | NFR-001; K1; K2 | — |
| `StationReadTx.get_item(item_id: str) -> InventoryItem` | Current local item (Earth base + replay) | `NotFound` | FR-005 | — |
| `StationReadTx.list_items() -> list[InventoryItem]` | All items | Never raises | FR-004 | — |
| `StationReadTx.find_by_barcode(barcode: str) -> Optional[InventoryItem]` | Item or `None` (unique index) | Never raises | FR-004; NFR-007 | — |
| `StationReadTx.earth_base(item_id: str) -> InventoryItem` | Last Earth version received | `NotFound` | InventoryUpdate (`baseVersion`); FR-029 | — |
| `StationReadTx.list_locations() -> list[StorageLocation]` | All locations | Never raises | FR-007 | — |
| `StationReadTx.get_user(user_id: str) -> User` | Last synced user record | `NotFound` | User; NFR-003 | — |
| `StationReadTx.get_encrypted_private_key(user_id: str) -> bytes` | Private key encrypted under the sign-in secret | `NotFound` | NFR-003; K9 | — |
| `StationReadTx.get_active_alert(item_id: str) -> Optional[SupplyAlert]` | The Active alert or `None` | Never raises | FR-012 | — |
| `StationReadTx.list_active_alerts() -> list[SupplyAlert]` | All Active alerts | Never raises | FR-001 | — |
| `StationReadTx.get_mission(mission_id: str) -> ResupplyMission` | Mission | `NotFound` | FR-024; K7 | — |
| `StationReadTx.list_missions() -> list[ResupplyMission]` | Non-final missions held on board | Never raises | FR-001; K7 | — |
| `StationReadTx.get_manifest(mission_id: str, version: Optional[int] = None) -> ManifestDraft` | Latest or given version | `NotFound` | CargoManifest | — |
| `StationReadTx.list_discrepancies(mission_id: str) -> list[Discrepancy]` | Discrepancies of the mission | Never raises | FR-026 | — |
| `StationReadTx.item_history(item_id: str) -> list[InventoryUpdate]` | All updates for the item, unordered | Never raises | FR-011 | — |
| `StationReadTx.recent_events(since: datetime) -> list[ActivityEvent]` | Events since the time | Never raises | FR-001 | — |
| `StationReadTx.sendable_after(sequence: int, limit: int) -> list[InventoryUpdate \| ReceiptUnit]` | Awaiting-sync units after `sequence`, in order, skipping those held behind an open conflict | Never raises | FR-029; FR-030; NFR-004; K12 | — |
| `StationReadTx.pending_page(offset: int, limit: int) -> list[InventoryUpdate \| ReceiptUnit]` | Awaiting sync and Conflict units, oldest first | Never raises | FR-028; K8 | — |
| `StationReadTx.pending_count() -> int` | Awaiting sync + Conflict | Never raises | FR-001; FR-028 | — |
| `StationReadTx.rejected_since(since: datetime) -> list[InventoryUpdate \| ReceiptUnit]` | Units rejected by Earth at or after `since` | Never raises | FR-028 | — |
| `StationReadTx.open_conflicts() -> list[ConflictRecord]` | Unresolved conflicts with local and Earth values | Never raises | FR-030; AC-030 | — |
| `StationReadTx.pull_cursor() -> int` | Last applied Earth change cursor | Never raises | FR-029 | — |
| `StationReadTx.last_full_sync() -> Optional[datetime]` | Time of last fully completed sync | Never raises | FR-002 | — |
| `StationWriteTx.put_item(item: InventoryItem) -> None` | Local item written | `ValidationError` if quantity < 0 | InventoryItem; NFR-001 | — |
| `StationWriteTx.put_earth_base(item: InventoryItem) -> None` | Earth base replaced | Never raises | FR-029; flow step 21 | — |
| `StationWriteTx.put_location(location: StorageLocation) -> None` | Location written | Never raises | FR-010 | — |
| `StationWriteTx.put_user(user: User) -> None` | User record and public keys written | Never raises | User; NFR-003 | — |
| `StationWriteTx.append_update(update: InventoryUpdate) -> InventoryUpdate` | The update with assigned `sequence` and `U…` display ID | `ValueError` if `update_id` already exists | FR-027; K4; K6 | — |
| `StationWriteTx.append_receipt(receipt: ReceiptUnit) -> ReceiptUnit` | Receipt with assigned sequence | `ValueError` if `receipt_id` already exists | FR-025; K3 | — |
| `StationWriteTx.set_sync_status(key: UUID, status: SyncStatus, rejected_at: Optional[datetime] = None) -> None` | Status changed (the only mutable history field) | `NotFound` | NFR-006; FR-029 | — |
| `StationWriteTx.put_conflict(conflict: ConflictRecord) -> None` | Conflict recorded or marked resolved | Never raises | FR-030; FR-031 | — |
| `StationWriteTx.put_alert(alert: SupplyAlert) -> None` | Alert written | `ValueError` if a second Active alert for the item | FR-012 | — |
| `StationWriteTx.put_mission(mission: ResupplyMission) -> None` | Mission written | Never raises | FR-025; K7 | — |
| `StationWriteTx.append_status_history(mission_id: str, entry: StatusHistoryEntry) -> None` | Entry appended | `NotFound` | FR-024; NFR-006 | — |
| `StationWriteTx.append_discrepancy(discrepancy: Discrepancy) -> None` | Discrepancy appended | Never raises | FR-026 | — |
| `StationWriteTx.set_pull_cursor(cursor: int) -> None` | Cursor advanced | `ValueError` if it moves backward | FR-029 | — |
| `StationWriteTx.record_full_sync(at: datetime) -> None` | Last full sync time stored | Never raises | FR-002 | — |

## Sync Agent (`ssir.station.sync_agent`)

`SyncAgent(store: OnboardStore, clock: StationClock, transport: SyncTransport, sleep: Callable[[float], None] = time.sleep)`. `SyncTransport` is the interface of the injected K11 channel (`ping`, `handshake`, `send`, `pull`, `complete`). Constants: `LINK_CHECK_INTERVAL` = 30 s, `BACKOFF_CAP` = 60 s.

| Signature | Success result | How it fails | Spec rule | Injected |
|---|---|---|---|---|
| `run(stop: threading.Event) -> None` | Loops until `stop`: checks the link every 30 s and calls `sync_now()` when available | Never raises; transport errors are retried with backoff ≤ 60 s | FR-029; NFR-004; K14 | store, clock, transport, sleep |
| `check_link() -> bool` | `True` if the Earth Gateway answered (counts as station contact) | Never raises | NFR-004; FR-002; K14 | transport, clock |
| `sync_now() -> SyncReport` | Handshake, send all sendable units, pull; `fully_completed` per FR-002 | `ConnectionError` if the link drops (progress already committed is kept) | FR-029; FR-002; AC-029 | store, clock, transport |
| `handshake() -> HandshakeReply` | Earth time and committed sequence; clock corrected; pending count reported | `ConnectionError` | NFR-004; NFR-005; K12; K16 | store, clock, transport |
| `send_pending(committed_sequence: int) -> int` | Number of units acknowledged, conflicted or rejected | `ConnectionError` | FR-029; FR-030; FR-025; NFR-004; K13 | store, transport |
| `apply_outcome(outcome: Outcome) -> None` | One commit: sync status set, Earth version stored, conflict marked, or `rejected_at` stored | `NotFound` if the key is unknown | FR-029; FR-030; AC-029 | store |
| `pull_changes(pull_started_at: datetime) -> int` | Number of Earth changes applied, all made before `pull_started_at` | `ConnectionError` | FR-029; FR-002; FR-010; User | store, transport |
| `apply_change(change: Change) -> None` | One commit: Earth base replaced, unacknowledged non-rejected updates replayed, conflicted fields kept "Review required", alert re-evaluated, cursor advanced | `ValueError` for an unknown change kind | FR-029; FR-030; FR-031; FR-012; flow step 21 | store |
| `link_status() -> LinkStatus` | Earth link availability and last full sync | Never raises | FR-002; AC-002 | store, clock |

---

## Earth Gateway (`ssir.earth.gateway`)

`EarthGateway(store: EarthStore, directory: IdentityDirectory, station_credential_check: Callable[[bytes], bool], handlers: Mapping[Operation, Handler], station_handler: StationHandler, now: Callable[[], datetime])`. `Operation` enumerates every Earth screen request and maps to an `Action`.

| Signature | Success result | How it fails | Spec rule | Injected |
|---|---|---|---|---|
| `authenticate_user(token: str) -> User` | User with role and `canReopen` from the identity system | `Unauthenticated` | FR-003; NFR-003 | directory |
| `authorize(user: User, operation: Operation) -> Action` | The checked `Action` | `Forbidden` | FR-003; FR-020; AC-003; AC-020 | — |
| `handle(token: str, operation: Operation, payload: Mapping[str, object]) -> object` | Result of the registered handler | `Unauthenticated`, `Forbidden`, or whatever the handler raises | FR-003; NFR-003 | directory, handlers |
| `handle_station(credential: bytes, call: str, message: object) -> object` | Station contact recorded, call forwarded to the Sync Endpoint | `Unauthenticated` if the station credential fails | NFR-003; FR-002; K11; K14 | store, station_credential_check, station_handler, now |
| `link_status() -> LinkStatus` | "Station link" availability and last full sync | Never raises | FR-002; K21 | store, now |

## Sync Endpoint (`ssir.earth.sync_endpoint`)

`SyncEndpoint(store: EarthStore, inventory: InventoryService, missions: MissionService, directory: IdentityDirectory, now: Callable[[], datetime])`.

| Signature | Success result | How it fails | Spec rule | Injected |
|---|---|---|---|---|
| `handshake(hello: Handshake) -> HandshakeReply` | Earth time and highest committed station sequence; pending count and session open recorded | Never raises | NFR-004; NFR-005; FR-001; K12; K21 | store, now |
| `receive_update(update: InventoryUpdate) -> Outcome` | Stored outcome for a resend with identical content; else verifies signer, validates, applies via Inventory Service in one transaction and returns ACKNOWLEDGED (with new version) or CONFLICT | Returns `REJECTED` outcome (not an exception) for bad signature, revoked key, altered resend, or FR-032 failure; server-set fields ignored | FR-029; FR-030; FR-032; NFR-003; AC-029; AC-032 | store, inventory, directory, now |
| `receive_receipt(receipt: ReceiptUnit) -> Outcome` | Same as above for a whole receipt, deduplicated by `receiptId`, applied via Mission Service in one transaction | `REJECTED` outcome as above | FR-025; FR-029; AC-025 | store, missions, directory, now |
| `verify_signer(content: bytes, signature: Signature, event_time: datetime) -> User` | The user whose key made the signature (becomes `recordedBy`) | `Unauthenticated` for unknown key, bad signature, or key revoked before `event_time` | NFR-003; K10; AC-032 | directory |
| `change_feed(cursor: int, before: datetime) -> ChangeBatch` | Earth changes after `cursor` made before `before`, in commit order, incl. user records and keys | Never raises | FR-029; FR-010; FR-031; User | store, directory |
| `complete_sync(pull_started_at: datetime) -> None` | Full-sync completion time recorded | Never raises | FR-002; K21 | store, now |
| `close_session() -> None` | Session marked closed | Never raises | FR-002 | store |

## Inventory Service (`ssir.earth.inventory_service`)

`InventoryService(store: EarthStore, now: Callable[[], datetime])`. `NewItem` and `ItemEdit` are input dataclasses. Every write is one Earth Store transaction that re-reads the current version and is conditional on it; every field change records its source; alerts are re-evaluated in the same transaction (K20).

| Signature | Success result | How it fails | Spec rule | Injected |
|---|---|---|---|---|
| `apply_station_update(tx: EarthTx, update: InventoryUpdate, signer: User) -> Outcome` | Inside the caller's transaction: merge or conflict, apply, set `recordedBy` = signer and `receivedAt`, new version, alert, outcome stored | Returns CONFLICT outcome on clash; raises `ValidationError` for FR-032 failures (caller turns it into REJECTED) | FR-030; FR-012; FR-032; NFR-003 | store (via `tx`), now |
| `correct_item(actor: User, item_id: str, field: CorrectionField, new_value: Decimal \| date, reason: str, expected_version: int) -> InventoryUpdate` | Committed Correction with `E…` display ID | `ValidationError`, `NotFound`, `StaleState` | FR-009; FR-032; InventoryUpdate (E…) | store, now |
| `create_item(actor: User, item: NewItem) -> InventoryItem` | New item at version 1; alert evaluated | `ValidationError` (duplicate barcode or ID, bad values) | FR-010 | store, now |
| `edit_item(actor: User, item_id: str, edit: ItemEdit, expected_version: int) -> InventoryItem` | New version; minimum change may raise or resolve the alert | `ValidationError`, `NotFound`, `StaleState` | FR-010; FR-012; AC-010 | store, now |
| `create_location(actor: User, location_id: str, name: str) -> StorageLocation` | New location | `ValidationError` (duplicate ID, bad name) | FR-010; StorageLocation | store |
| `resolve_conflict(actor: User, update_id: UUID, choice: ResolutionChoice, reason: str) -> InventoryUpdate` | Committed Resolution update (E…), new item version, conflict closed | `ValidationError` (empty reason; update not in conflict), `StaleState` (already resolved), `NotFound` | FR-031; FR-032; AC-031 | store, now |
| `get_item(item_id: str) -> InventoryItem` | Item | `NotFound` | FR-005 | store |
| `search_items(query: str, item_filter: InventoryFilter) -> list[InventoryItem]` | Matching items | Never raises | FR-004; NFR-007 | store, now |
| `item_history(item_id: str) -> list[InventoryUpdate]` | Ordered per FR-011 (Earth commit order for ties) | `NotFound` | FR-011 | store |
| `active_alerts() -> list[SupplyAlert]` | Earth-side Active alerts | Never raises | FR-001; FR-013 | store |
| `open_conflicts() -> list[ConflictRecord]` | Unresolved conflicts | Never raises | FR-030; FR-031 | store |
| `list_locations() -> list[StorageLocation]` | All locations | Never raises | FR-007; FR-010 | store |

## Mission Service (`ssir.earth.mission_service`)

`MissionService(store: EarthStore, inventory: InventoryService, now: Callable[[], datetime])`. Every write re-reads status or version in the same transaction (FR-032) and appends a status-history entry with time, user and reason for each transition.

| Signature | Success result | How it fails | Spec rule | Injected |
|---|---|---|---|---|
| `create_mission(actor: User, mass_capacity_kg: Decimal, volume_capacity_m3: Decimal) -> ResupplyMission` | Draft mission with next `R…` ID and empty manifest v1 | `ValidationError` (capacity ≤ 0) | FR-014; AC-014 | store, now |
| `save_manifest(actor: User, mission_id: str, base_version: int, draft: ManifestDraft) -> CargoManifest` | New version if changed, same version if not; lines editable in Draft only, expected arrival also in Approved | `StaleState` (base ≠ current), `InvalidTransition` (wrong status or line change outside Draft), `ValidationError` | FR-015; FR-016; AC-015; AC-016 | store, now |
| `manifest_editor(mission_id: str) -> ManifestEditorView` | Manifest, totals, alerts marked Covered/Not covered | `NotFound` | FR-013; FR-015; AC-013 | store, inventory |
| `submit(actor: User, mission_id: str) -> ResupplyMission` | Submitted | `ValidationError` listing every failure; `InvalidTransition` | FR-017; AC-017 | store, now |
| `approve(actor: User, mission_id: str) -> ResupplyMission` | Approved after capacity re-check | `ValidationError`, `InvalidTransition` | FR-018; AC-018 | store, now |
| `return_to_draft(actor: User, mission_id: str, reason: str) -> ResupplyMission` | Draft | `ValidationError` (empty reason), `InvalidTransition` | FR-019; AC-019 | store, now |
| `reopen(actor: User, mission_id: str, reason: str) -> ResupplyMission` | Draft; loaded quantities cleared; loading issues kept | `ValidationError`, `InvalidTransition`, `Forbidden` (no `canReopen`) | FR-020; AC-020 | store, now |
| `cancel(actor: User, mission_id: str, reason: str) -> ResupplyMission` | Cancelled | `ValidationError`, `InvalidTransition` (Shipped/Received/Cancelled) | FR-021; AC-021 | store, now |
| `record_loaded_quantity(actor: User, mission_id: str, item_id: str, loaded_quantity: Decimal) -> CargoManifest` | Line updated | `ValidationError` (< 0), `InvalidTransition` (not Approved), `NotFound` | FR-022; AC-022 | store, now |
| `add_loading_issue(actor: User, mission_id: str, text: str) -> LoadingIssue` | Issue appended | `ValidationError`, `InvalidTransition`, `NotFound` | FR-022; LoadingIssue | store, now |
| `loading_review(mission_id: str) -> list[LoadingReviewLine]` | Planned/loaded/missing per line | `NotFound` | FR-022; AC-022 | store |
| `confirm_dispatch(actor: User, mission_id: str) -> DispatchResult` | Shipped with `dispatchedAt`; shortfalls as warnings | `ValidationError` (missing loaded quantity or expected arrival), `InvalidTransition` | FR-023; AC-023 | store, now |
| `apply_receipt(tx: EarthTx, receipt: ReceiptUnit, signer: User) -> Outcome` | Inside the caller's transaction: mission Received, Receipt updates applied via Inventory Service, discrepancies stored | `ValidationError`, `InvalidTransition` (caller turns into REJECTED) | FR-025; FR-026; NFR-001 | inventory, now |
| `resolve_discrepancy(actor: User, discrepancy_id: str, note: str) -> Discrepancy` | Resolved with note | `ValidationError` (empty note), `StaleState` (already resolved), `NotFound` | FR-026; AC-026 | store, now |
| `get_mission(mission_id: str) -> ResupplyMission` | Mission with history | `NotFound` | FR-024; AC-024 | store |
| `list_missions() -> list[ResupplyMission]` | All missions | Never raises | FR-001; FR-024 | store |
| `get_manifest(mission_id: str, version: Optional[int] = None) -> CargoManifest` | Latest or a read-only earlier version | `NotFound` | CargoManifest; FR-024 | store |
| `list_loading_issues(mission_id: str) -> list[LoadingIssue]` | Issues | `NotFound` | FR-020; FR-022 | store |
| `list_discrepancies(mission_id: str) -> list[Discrepancy]` | Discrepancies | `NotFound` | FR-026 | store |

## Earth Store (`ssir.earth.earth_store`)

`EarthStore(dsn: str)`. `transaction()` commits on the primary and the synchronous replica before returning (K5); history tables are insert-only (K18). `for_update=True` locks the row for conditional writes. Failure for every `EarthTx` getter on a missing row is `NotFound`; store-level I/O failure aborts the transaction.

| Signature | Success result | How it fails | Spec rule | Injected |
|---|---|---|---|---|
| `EarthStore.open() -> None` | Connected | `ConnectionError` | NFR-008 | `dsn` |
| `EarthStore.close() -> None` | Closed | Never raises | — | — |
| `EarthStore.transaction() -> ContextManager[EarthTx]` | Atomic replicated commit on exit; rollback on exception | `ConnectionError`; any exception aborts | NFR-001; NFR-008; K5 | — |
| `EarthTx.get_item(item_id: str, for_update: bool = False) -> InventoryItem` | Item | `NotFound` | FR-030 | — |
| `EarthTx.list_items() -> list[InventoryItem]` | Items | Never raises | FR-004 | — |
| `EarthTx.put_item(item: InventoryItem) -> InventoryItem` | Item with next `recordVersion` | `ValueError` if quantity < 0 or barcode not unique | InventoryItem | — |
| `EarthTx.list_locations() -> list[StorageLocation]` | Locations | Never raises | FR-007 | — |
| `EarthTx.put_location(location: StorageLocation) -> None` | Stored | `ValueError` on duplicate ID | FR-010 | — |
| `EarthTx.append_field_change(change: FieldChange) -> None` | Source of a field change recorded | Never raises | FR-030 | — |
| `EarthTx.field_changes_since(item_id: str, version: int) -> list[FieldChange]` | Changes after `version` | Never raises | FR-030 | — |
| `EarthTx.append_update(update: InventoryUpdate) -> InventoryUpdate` | Stored; Earth updates get next `E…` ID | `ValueError` on duplicate `updateId` | FR-011; InventoryUpdate | — |
| `EarthTx.get_update(update_id: UUID) -> InventoryUpdate` | Update | `NotFound` | FR-031 | — |
| `EarthTx.set_sync_status(update_id: UUID, status: SyncStatus) -> None` | Status changed | `NotFound` | NFR-006 | — |
| `EarthTx.item_history(item_id: str) -> list[InventoryUpdate]` | Updates for the item | Never raises | FR-011 | — |
| `EarthTx.get_outcome(key: UUID) -> Optional[tuple[bytes, Outcome]]` | Stored content hash and outcome, or `None` | Never raises | FR-029; FR-025 | — |
| `EarthTx.put_outcome(key: UUID, content_hash: bytes, outcome: Outcome) -> None` | Stored | `ValueError` on duplicate key | FR-029; FR-025 | — |
| `EarthTx.get_conflict(update_id: UUID, for_update: bool = False) -> ConflictRecord` | Conflict | `NotFound` | FR-031 | — |
| `EarthTx.list_open_conflicts() -> list[ConflictRecord]` | Open conflicts | Never raises | FR-030 | — |
| `EarthTx.append_conflict(conflict: ConflictRecord) -> None` | Stored | Never raises | FR-030 | — |
| `EarthTx.append_resolution(conflict: ConflictRecord) -> None` | Resolution row appended | `ValueError` if already resolved | FR-031; NFR-006 | — |
| `EarthTx.get_active_alert(item_id: str) -> Optional[SupplyAlert]` | Alert or `None` | Never raises | FR-012 | — |
| `EarthTx.list_active_alerts() -> list[SupplyAlert]` | Active alerts | Never raises | FR-001 | — |
| `EarthTx.put_alert(alert: SupplyAlert) -> None` | Stored | `ValueError` on a second Active alert | FR-012 | — |
| `EarthTx.recent_events(since: datetime) -> list[ActivityEvent]` | Events since the time | Never raises | FR-001 | — |
| `EarthTx.next_mission_id() -> str` | Next `R…` ID from a sequence | Never raises | FR-014 | — |
| `EarthTx.get_mission(mission_id: str, for_update: bool = False) -> ResupplyMission` | Mission | `NotFound` | FR-032 | — |
| `EarthTx.list_missions() -> list[ResupplyMission]` | Missions | Never raises | FR-001 | — |
| `EarthTx.put_mission(mission: ResupplyMission) -> None` | Stored | Never raises | Lifecycle | — |
| `EarthTx.get_manifest(mission_id: str, version: Optional[int] = None) -> ManifestDraft` | Latest or given version | `NotFound` | CargoManifest | — |
| `EarthTx.append_manifest_version(mission_id: str, version: int, draft: ManifestDraft) -> None` | New read-only version stored | `ValueError` if version exists | FR-016; NFR-006 | — |
| `EarthTx.append_status_history(mission_id: str, entry: StatusHistoryEntry) -> None` | Appended | Never raises | FR-024; NFR-006 | — |
| `EarthTx.append_loading_issue(issue: LoadingIssue) -> None` | Appended | Never raises | FR-022; NFR-006 | — |
| `EarthTx.list_loading_issues(mission_id: str) -> list[LoadingIssue]` | Issues | Never raises | FR-020 | — |
| `EarthTx.append_discrepancy(discrepancy: Discrepancy) -> None` | Appended (resolution is a new row) | Never raises | FR-026; NFR-006 | — |
| `EarthTx.get_discrepancy(discrepancy_id: str, for_update: bool = False) -> Discrepancy` | Latest state | `NotFound` | FR-026 | — |
| `EarthTx.list_discrepancies(mission_id: str) -> list[Discrepancy]` | Discrepancies | Never raises | FR-026 | — |
| `EarthTx.committed_station_sequence() -> int` | Highest committed station sequence | Never raises | NFR-004; K12 | — |
| `EarthTx.set_committed_station_sequence(sequence: int) -> None` | Stored | `ValueError` if it moves backward | NFR-004 | — |
| `EarthTx.record_station_contact(at: datetime) -> None` | Stored | Never raises | FR-002 | — |
| `EarthTx.last_station_contact() -> Optional[datetime]` | Time or `None` | Never raises | FR-002 | — |
| `EarthTx.set_reported_pending_count(count: int) -> None` | Stored | Never raises | FR-001 | — |
| `EarthTx.reported_pending_count() -> int` | Count | Never raises | FR-001 | — |
| `EarthTx.set_session_open(is_open: bool) -> None` | Stored | Never raises | FR-002 | — |
| `EarthTx.session_open() -> bool` | Flag | Never raises | FR-002 | — |
| `EarthTx.record_full_sync(at: datetime) -> None` | Stored | Never raises | FR-002 | — |
| `EarthTx.last_full_sync() -> Optional[datetime]` | Time or `None` | Never raises | FR-002 | — |
| `EarthTx.change_feed(after_cursor: int, before: datetime, limit: int) -> ChangeBatch` | Changes in Earth commit order | Never raises | FR-029 | — |

---

## Screens (`ssir.screens`)

Every render returns HTML in which all text is escaped, shows the link banner, and has navigation to S1, S2, S4, S6 and S7. Controls come from `visible_controls` (display only; Earth Gateway is authoritative).

| Signature | Success result | How it fails | Spec rule | Injected |
|---|---|---|---|---|
| `escape(text: str) -> str` | HTML-escaped text | Never raises | FR-032 | — |
| `visible_controls(user: User, screen: Screen, mission: Optional[ResupplyMission] = None) -> frozenset[Action]` | Actions permitted by role and allowed by the mission's status | Never raises | FR-003; FR-021; AC-003; AC-021 | — |
| `StationScreens.sign_in(user_id: str, secret: str) -> Session` | Session | `Unauthenticated` | NFR-003 | handler |
| `StationScreens.banner() -> str` | "Earth link available/unavailable" + "Last sync …" | Never raises | FR-002; AC-002 | store, clock |
| `StationScreens.dashboard(session: Session) -> str` | S1 | `Unauthenticated` | FR-001; AC-001 | store, clock |
| `StationScreens.inventory(session: Session, query: str, item_filter: InventoryFilter) -> str` | S2 | `Unauthenticated` | FR-004; AC-004 | store, clock |
| `StationScreens.item_details(session: Session, item_id: str) -> str` | S3 | `NotFound`, `Unauthenticated` | FR-005; AC-005 | store, clock |
| `StationScreens.item_history(session: Session, item_id: str) -> str` | S3 history | `NotFound`, `Unauthenticated` | FR-011; AC-011 | store, clock |
| `StationScreens.resupply_plan(session: Session, mission_id: Optional[str]) -> str` | S4 (read-only on the station) | `NotFound`, `Unauthenticated` | FR-013; FR-015 | store, clock |
| `StationScreens.cargo_manifest(session: Session, mission_id: str, version: Optional[int] = None) -> str` | S5 | `NotFound`, `Unauthenticated` | FR-016; FR-022; FR-025 | store, clock |
| `StationScreens.mission_status(session: Session, mission_id: str) -> str` | S6 | `NotFound`, `Unauthenticated` | FR-024; AC-024 | store, clock |
| `StationScreens.sync(session: Session, page: int = 0) -> str` | S7: pending (oldest first), conflicts, rejected (7 days), "Waiting for conflict review" | `Unauthenticated` | FR-028; AC-028; K8 | store, clock |
| `StationScreens.submit_action(session: Session, action: Action, form: Mapping[str, str]) -> str` | Next page after the Command Handler commits (e.g. "Saved locally") | Error messages rendered from `ValidationError`/`Forbidden`/`NotFound` | FR-006–FR-009; FR-025; FR-027 | handler |
| `StationScreens.serve(host: str, port: int, stop: threading.Event) -> None` | Serves station devices until `stop` | `OSError` if the port is unavailable | Description (screens) | handler, store, clock |
| `EarthScreens.banner(token: str) -> str` | "Station link …" + "Last sync …" | `Unauthenticated` | FR-002 | gateway |
| `EarthScreens.dashboard(token: str) -> str` | S1 with the station's last reported pending count | `Unauthenticated` | FR-001 | gateway |
| `EarthScreens.inventory(token: str, query: str, item_filter: InventoryFilter) -> str` | S2 | `Unauthenticated` | FR-004 | gateway |
| `EarthScreens.item_details(token: str, item_id: str) -> str` | S3 | `Unauthenticated`, `NotFound` | FR-005 | gateway |
| `EarthScreens.item_history(token: str, item_id: str) -> str` | S3 history | `Unauthenticated`, `NotFound` | FR-011 | gateway |
| `EarthScreens.resupply_plan(token: str, mission_id: Optional[str]) -> str` | S4 editor with totals (red when over) and alert coverage | `Unauthenticated`, `NotFound` | FR-013; FR-015 | gateway |
| `EarthScreens.cargo_manifest(token: str, mission_id: str, version: Optional[int] = None) -> str` | S5 incl. loading review | `Unauthenticated`, `NotFound` | FR-016; FR-022 | gateway |
| `EarthScreens.mission_status(token: str, mission_id: str) -> str` | S6 | `Unauthenticated`, `NotFound` | FR-024 | gateway |
| `EarthScreens.sync(token: str) -> str` | S7 with open conflicts and resolve controls | `Unauthenticated` | FR-030; FR-031 | gateway |
| `EarthScreens.submit_action(token: str, action: Action, form: Mapping[str, str]) -> str` | Next page after the Gateway call | Error messages rendered from any `DomainError` | FR-003; FR-009–FR-026; FR-031 | gateway |
| `EarthScreens.serve(host: str, port: int, stop: threading.Event) -> None` | Serves Earth workstations until `stop` | `OSError` | Description (screens) | gateway |

---

## Additions and gaps

**Additions beyond the architecture's module list.** Two start-up files, `ssir/station/__main__.py` and `ssir/earth/__main__.py`, exist only so the application can be started. They construct the modules and call `open()`, `run()` and `serve()`; they contain no rules. Delete them if you want the module list exact. No other module was added: domain types, wire types and errors live in Domain Rules, because it is the only module both sites share.

**Architecture gaps the skeleton had to settle.** Please confirm or change these.

1. **Earth Gateway cannot reach the services.** The dependency table lets Screens (Earth) depend only on the Earth Gateway, and the Gateway only on Domain Rules and the Earth Store, so no listed path reaches the Inventory Service, Mission Service or Sync Endpoint. The skeleton injects them into the Gateway as `handlers` and `station_handler` at start-up, which keeps the static dependencies as listed.
2. **Station sign-in path.** Screens (station) may not depend on Station Identity, yet sign-in happens on a device. Sign-in goes through `StationCommandHandler.sign_in`, which depends on Station Identity.
3. **No Earth clock module.** Earth time is used in several places (step 15–16, K21) but no Earth clock module is listed, so Earth modules receive `now: Callable[[], datetime]`.
4. **Private key provisioning.** K9 stores each private key encrypted on board, but neither document says how it gets there. `StationReadTx.get_encrypted_private_key` reads it; nothing writes it.
5. **Rejection time.** `InventoryUpdate.rejected_at` is not a spec field; it carries Earth's rejection time for the FR-028 window (Spec issue 3).
6. **The station transport is not built.** `SyncTransport` is the interface the Sync Agent needs; the K11 encrypted channel is left to implementation, and `__main__` passes a placeholder.
