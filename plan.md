# Implementation plan: Space Station Inventory and Resupply

Based on `spec_ayden.md` (rev. Nov 2, 2026), `architecture_ayden.md`, `contracts_ayden.md`, `test_plan_ayden.md`, and the `ssir_skeleton` code and tests. No implementation code is written here.

## Baseline (Nov 16, 2026)

- `python3 tests/run_classified.py` runs 38 test methods. 37 fail and 1 is skipped (`test_AT03_6_update_signed_by_planner_rejected`). Counting subtests, there are 66 failing results.
- Every failure is `NOT IMPLEMENTED`. None is `OTHER`, so no failure comes from a broken test or broken wiring.
- The suite has tests only for **AC-001, AC-003 and AC-004**. The other 29 criteria have no test file yet (see "Leftovers").
- The skeleton has 218 functions that raise `NotImplementedError`, and they match contracts.md one for one.

## Conventions used in this plan

- **Routes.** The skeleton has no HTTP routes and nothing returns 501. In this plan, "route" means:
  - a station screen method (`StationScreens.*`);
  - an Earth screen method (`EarthScreens.*`);
  - a station action sent through `StationScreens.submit_action`;
  - an Earth Gateway `Operation`. Each Operation's real handler is registered in `ssir/earth/__main__.py` (contracts gap 1). The slice that adds the handler lists it as "Operations routed".
- **When a criterion counts as complete.** A criterion is listed in the slice where every one of its spec Gherkin scenarios can pass. Extra rows the test plan added (marked "extra") that need a later slice are named in that later slice's Goal.
- **Function ownership.** Each skeleton function is filled in exactly one slice. A later slice may *extend* a function that is already filled; that is noted, and the function is not listed again.
- **Done when.** For slices with no tests in the suite, "the listed tests pass" holds trivially. Write that slice's tests from test_plan.md before starting it.

---

## Slices

### Slice 1: Thin path: station S1 pending count
- **Goal:** A station device can render S1 showing the pending-update count, read from the Onboard Store. The count is Awaiting sync plus Conflict, never Rejected.
- **Spec sources:** FR-001 (Pending updates); FR-027; InventoryUpdate (`syncStatus`, never deleted); NFR-001 (durable, serialized writes); architecture K1, K2, K4, K6, K15.
- **Criteria:** none completed. This slice starts AC-001.
- **Tests that should turn green:** `test_AT01_5_pending_excludes_rejected`
- **Skeleton to fill in:**
  - Store setup: `OnboardStore.open`, `OnboardStore.close`, `OnboardStore.read`, `OnboardStore.write`.
  - Writes: `StationWriteTx.put_location`, `put_user`, `put_earth_base`, `put_item`, `put_alert`, `put_mission`, `append_update`, `set_sync_status`.
  - Read: `StationReadTx.pending_count`.
  - Clock and screen: `StationClock.now` (no offset yet), `screens.escape`, `StationScreens.dashboard` (pending count only, for now).
  - Route: S1 on the station.
- **Depends on:** none.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** done (Nov 16, 2026). `test_AT01_5_pending_excludes_rejected` passes; no regressions.
- *Decisions taken (Nov 16, 2026):* station sequences start at 101 and the display ID is `U{sequence}`; S1 uses one template, `"{n} pending updates"`, for every count (including 1).
- *Note:* the contract says every page shows the link banner. S1 does not show it until slice 9, which adds it.

### Slice 2: Role permissions and the Earth Gateway path
- **Goal:** One shared permission table drives both control hiding on screens and the Gateway's Forbidden check. A forbidden request never reaches a service.
- **Spec sources:** FR-003; Actors; Mission lifecycle (which controls each status allows, FR-021); NFR-003 ("every permission enforced by the Earth service"); architecture K-table "Identity".
- **Criteria:** AC-003. Spec scenarios .1–.3, plus the extra rows .4–.5. Row .6 lands in slice 34.
- **Tests that should turn green:**
  - `test_AT03_1_crew_sees_no_approve`, `test_AT03_1_control_gmc_sees_approve`
  - `test_AT03_3_planner_sees_no_receipt_or_resolve`, `test_AT03_3_control_crew_and_gmc_see_them`
  - `test_AT03_2_crew_approve_forbidden`, `test_AT03_2_control_gmc_approve_accepted`
  - `test_AT03_4_planner_resolve_conflict_forbidden`, `test_AT03_4_control_gmc_resolve_conflict_accepted`
  - `test_AT03_5_permission_matrix_with_controls`
- **Skeleton to fill in:** `is_permitted`, `require_permission`, `screens.visible_controls`, `EarthGateway.authenticate_user`, `EarthGateway.authorize`, `EarthGateway.handle`.
- **Depends on:** none.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** done (Nov 16, 2026). All 9 AT03 tests pass; no regressions. `next_status` (from slice 24) was filled here by decision.
- *Decisions taken (Nov 16, 2026):*
  - On the Earth Gateway, station crew may only view; their corrections reach Earth as signed updates through sync (answers Design question 12).
  - `visible_controls` filters by a screen→actions table derived from the spec (S2 create item/location; S3 usage, move, condition, correct, edit; S4 create mission, save, submit; S5 loading, receipt; S6 approve, return, reopen, cancel, dispatch, receipt, resolve discrepancy; S7 resolve conflict, sync now).
  - Mission controls are gated by status through `next_status`; save manifest (Draft, Approved), record loading (Approved) and resolve discrepancy (any status) use a small status table.
- *Note:* the tests build the Gateway on an Earth Store that is never opened. `handle` must therefore not touch the store for screen operations.

### Slice 3: Inventory search and filter
- **Goal:**
  - Search is a case-insensitive substring match on name or ID; a barcode must match exactly.
  - Exactly one filter applies (All, Low stock, Damaged, Expired), using UTC "today".
  - A barcode lookup on board takes ≤ 1 s with 10,000 items.
- **Spec sources:** FR-004; InventoryItem (unique barcodes); NFR-005 (UTC date logic); NFR-007; architecture K17 and Further decisions (barcode index).
- **Criteria:** AC-004.
- **Tests that should turn green:**
  - Search: `test_AT04_1_search_by_name`, `test_AT04_2_scan_barcode`, `test_AT04_3_filters`, `test_AT04_4_case_insensitive`, `test_AT04_5_id_substring`, `test_AT04_6_barcode_prefix_matches_nothing`, `test_AT04_7_search_combined_with_filter`
  - Boundaries: `test_AT04_9_inside_quantity_equals_minimum_not_low`, `test_AT04_10_outside_quantity_below_minimum_is_low`, `test_AT04_11_inside_expiry_today_not_expired`, `test_AT04_12_outside_expiry_yesterday_expired`
  - Speed: `test_AT04_8_search_and_barcode_within_one_second`, `test_AT04_8_station_barcode_lookup_within_one_second`
- **Skeleton to fill in:** `today_utc`, `is_low_stock`, `is_expired`, `matches_query`, `filter_items`, `StationReadTx.list_items`, `StationReadTx.find_by_barcode`, `StationScreens.inventory`. Route: S2 on the station.
- **Depends on:** 1.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** done (Nov 16, 2026). All 13 AT04 tests pass; no regressions.
- *Decisions taken (Nov 16, 2026):*
  - The station keeps a unique barcode index; `StationWriteTx.put_item` raises `ValueError` for a barcode another item holds (mirrors `EarthTx.put_item`).
  - S2 lists items by name (case-insensitive, ID breaks ties), each row showing ID, name and quantity with unit.
  - Quantity text: a countable unit takes "s" unless the quantity is exactly 1; other units never do ("6 packs", "1 kit", "2.000 kg"). Kept as the private Domain Rules helper `_quantity_text` so `alert_text` (slice 4) reuses it.

### Slice 4: Alert text and Critical-first ordering
- **Goal:** Active alerts are listed with Critical items first, as "\<item> below minimum (\<qty> / \<min> \<unit>)".
- **Spec sources:** FR-001 (Alerts); SupplyAlert; InventoryItem (`criticality`).
- **Criteria:** none completed (part of AC-001).
- **Tests that should turn green:** `test_AT01_1_alert_text`, `test_AT01_2_critical_first`
- **Skeleton to fill in:** `alert_text`, `order_alerts`.
- **Depends on:** none.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 5: Next mission rule
- **Goal:** The next mission is the Submitted, Approved or Shipped mission with the earliest expected arrival. If none has an arrival, it is the most recently changed one.
- **Spec sources:** FR-001 (Next mission); Mission lifecycle.
- **Criteria:** none completed (part of AC-001).
- **Tests that should turn green:** `test_AT01_1_next_mission`, `test_AT01_3_next_mission_excludes_draft_and_cancelled`, `test_AT01_4_next_mission_most_recently_changed`
- **Skeleton to fill in:** `next_mission`.
- **Depends on:** none.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Isolated because:* the status filter, the null-arrival fallback and the meaning of "changed" are easy to get subtly wrong (see Design question 6).

### Slice 6: Recent activity window
- **Goal:** Recent activity shows at most the 10 newest events from the past 7 days.
- **Spec sources:** FR-001 (Recent activity); NFR-005.
- **Criteria:** none completed (part of AC-001).
- **Tests that should turn green:** `test_AT01_1_recent_activity_window`, `test_AT01_8_inside_ten_events_all_shown`, `test_AT01_9_outside_eleven_events_oldest_dropped`, `test_AT01_10_inside_age_just_under_seven_days`, `test_AT01_11_outside_age_just_over_seven_days`
- **Skeleton to fill in:** `recent_activity`.
- **Depends on:** none.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Isolated because:* the window edge and the limit are boundary rules. The exact-7-days case stays blocked on G-B1.

### Slice 7: Earth Store bootstrap and handshake
- **Goal:** The Earth Store opens and commits atomically, and derives activity events of all six kinds. A handshake records the pending count the station reports and returns the committed sequence.
- **Spec sources:** FR-001 (event kinds; Earth pending = "the count the station last reported"); NFR-001; NFR-004; NFR-008; architecture K5, K12, K21, flow step 11.
- **Criteria:** none completed (part of AC-001).
- **Tests that should turn green:** `test_AT01_6_earth_shows_last_reported_pending_count`, `test_AT01_7_all_event_kinds_count_as_activity`
- **Skeleton to fill in:**
  - Store setup: `EarthStore.open`, `EarthStore.close`, `EarthStore.transaction`.
  - Writes: `EarthTx.put_location`, `put_item`, `append_update`, `put_mission`, `append_status_history`, `append_discrepancy`, `put_alert`.
  - Activity: `EarthTx.recent_events`.
  - Sync bookkeeping: `EarthTx.committed_station_sequence`, `set_reported_pending_count`, `reported_pending_count`, `set_session_open`.
  - Endpoint: `SyncEndpoint.handshake`.
- **Depends on:** none.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 8: Link banner and UTC formatting
- **Goal:**
  - Every screen shows link availability ("Earth link" on the station, "Station link" on Earth).
  - Every screen shows the last fully completed sync, as `HH:MM UTC` today and `YYYY-MM-DD HH:MM UTC` otherwise.
  - On Earth, the link counts as available while a session is open or within 60 s of the last station contact.
- **Spec sources:** Description (UTC format); FR-002; NFR-005; architecture K21.
- **Criteria:** AC-002. Extra row .6 (drift warning) lands in slice 32.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:**
  - Rules: `format_utc`, `earth_link_available`.
  - Screens and Gateway: `StationScreens.banner`, `EarthScreens.banner`, `EarthGateway.link_status`.
  - Station store: `StationReadTx.last_full_sync`, `StationWriteTx.record_full_sync`.
  - Earth store: `EarthTx.session_open`, `record_station_contact`, `last_station_contact`, `record_full_sync`, `last_full_sync`.
  - Operation routed: `LINK_STATUS`.
- **Depends on:** 1, 2, 7.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Blocked in part* by Design question 2: the station has no source for "link available".

### Slice 9: S1 Dashboard assembled
- **Goal:** S1 on both sites shows:
  - ordered alerts;
  - the next mission as "Mission R12 – Approved";
  - the pending count (Earth shows the station's last reported count);
  - recent activity;
  - the banner.
- **Spec sources:** FR-001; FR-002; Description (screens).
- **Criteria:** AC-001.
- **Tests that should turn green:** `test_AT01_1_dashboard_screen`, `test_AT01_2_dashboard_critical_first`
- **Skeleton to fill in:**
  - Station reads: `StationReadTx.list_active_alerts`, `get_item`, `list_missions`, `recent_events`.
  - Earth reads: `EarthTx.list_active_alerts`, `list_missions`, `list_items`.
  - Screen: `EarthScreens.dashboard`. Extends `StationScreens.dashboard`.
  - Operation routed: `DASHBOARD`.
- **Depends on:** 1, 4, 5, 6, 7, 8.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Partly blocked* by Design question 3: no service supplies the Earth dashboard's data.

### Slice 10: Item details and Earth inventory reads
- **Goal:** S3 shows every FR-005 field on both sites, and S2 works on Earth. Unknown IDs give NotFound.
- **Spec sources:** FR-005; FR-004 (Earth side); InventoryItem; StorageLocation.
- **Criteria:** AC-005.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:**
  - Station: `StationReadTx.earth_base`, `StationReadTx.list_locations`, `StationScreens.item_details`.
  - Earth service: `InventoryService.get_item`, `search_items`, `list_locations`.
  - Earth store: `EarthTx.get_item`, `EarthTx.list_locations`.
  - Earth screens: `EarthScreens.inventory`, `EarthScreens.item_details`.
  - Operations routed: `SEARCH_ITEMS`, `GET_ITEM`.
- **Depends on:** 2, 3, 7.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 11: Text and quantity validation
- **Goal:**
  - Required text is trimmed and rejected if empty; text over 1,000 characters is rejected.
  - Amounts are > 0. Countable units take whole numbers only; other units allow at most 3 decimals.
- **Spec sources:** FR-032 (text rules); Unit; FR-006 (amount > 0).
- **Criteria:** none completed. Every command slice uses these rules.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `validate_text`, `validate_amount`.
- **Depends on:** none.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Isolated because:* trimming, the 1,000/1,001 boundary and decimal places are classic places for off-by-one errors.

### Slice 12: Station sign-in and signing
- **Goal:** A crew member signs in on board without the Earth link, which unlocks only their own key. Content is signed over a canonical byte form.
- **Spec sources:** NFR-003; User (personal key pair); architecture K9, flow steps 1 and 6.
- **Criteria:** none completed. Extra row AC-027.4 is exercised here.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:**
  - Identity: `StationIdentity.sign_in`, `sign_out`, `sign`.
  - Command Handler: `StationCommandHandler.sign_in`, `sign_out`.
  - Screen: `StationScreens.sign_in`.
  - Signing: `canonical_update_content`.
  - Store reads: `StationReadTx.get_user`, `get_encrypted_private_key`.
- **Depends on:** 1.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Blocked* by Design questions 1, 7 and 8.

### Slice 13: Alert rule (raise and resolve)
- **Goal:** An alert is raised when quantity < minimum and resolved when quantity ≥ minimum. An item never has more than one Active alert.
- **Spec sources:** FR-012; SupplyAlert; architecture K20.
- **Criteria:** none completed (AC-012 completes in slice 31).
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `evaluate_alert`, `StationReadTx.get_active_alert`.
- **Depends on:** 1.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Isolated because:* the equality boundary and the no-duplicate rule are easy to get wrong.

### Slice 14: Record usage offline
- **Goal:** Usage is validated against the current local quantity and committed as one onboard transaction (item, signed U… update, alert). "Saved locally" appears only after the commit.
- **Spec sources:** FR-006; FR-027; NFR-001; NFR-002; architecture flow steps 1–9, K1–K4, K6.
- **Criteria:** AC-006, AC-027.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `validate_usage`, `StationCommandHandler.record_usage`, `StationScreens.submit_action`. Route: station action `RECORD_USAGE`.
- **Depends on:** 11, 12, 13.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 15: Move and condition
- **Goal:** Crew can move an item to another existing location, and set its condition to Usable or Damaged with a reason.
- **Spec sources:** FR-007; FR-008; InventoryItem.
- **Criteria:** AC-007, AC-008.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `validate_move`, `parse_condition`, `validate_condition_change`, `StationCommandHandler.move_item`, `StationCommandHandler.set_condition`. Routes: station actions `MOVE_ITEM`, `SET_CONDITION`.
- **Depends on:** 10, 14.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 16: Station stock correction
- **Goal:** Crew can correct quantity or expiry to a counted value with a reason. A correction can resolve or raise an alert.
- **Spec sources:** FR-009; FR-012.
- **Criteria:** AC-009. Extra row .3 (Earth correction) lands in slice 17.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `validate_correction`, `StationCommandHandler.correct_item`. Route: station action `CORRECT_ITEM`.
- **Depends on:** 14.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 17: Earth item data and Earth corrections
- **Goal:** Planners create items and locations and edit item data. Mission control corrects stock on Earth as E… updates.
- **What each write does:** every write is version-checked, records the source of each field it changes (needed by slice 39), and re-evaluates the alert in the same transaction.
- **Spec sources:** FR-010; FR-009 (Earth); FR-012; FR-032 (stale version); InventoryUpdate (E… IDs); architecture K20 and Further decisions (field-change source).
- **Criteria:** none completed (AC-010 needs the pull in slice 38).
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:**
  - Rule: `validate_item_data`.
  - Service: `InventoryService.create_item`, `edit_item`, `create_location`, `correct_item`.
  - Store: `EarthTx.get_active_alert`, `EarthTx.append_field_change`.
  - Screen: `EarthScreens.submit_action`.
  - Operations routed: `CREATE_ITEM`, `EDIT_ITEM`, `CREATE_LOCATION`, `CORRECT_ITEM`.
- **Depends on:** 2, 10, 13.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 18: Change history
- **Goal:** Item history is listed newest first by event time. Ties go by commit order on the side showing it. Each entry shows display ID, change, time, user and sync status.
- **Spec sources:** FR-011; NFR-006; architecture Further decisions (history ordering).
- **Criteria:** AC-011.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:**
  - Rule: `order_history`.
  - Station: `StationReadTx.item_history`, `StationScreens.item_history`.
  - Earth: `InventoryService.item_history`, `EarthTx.item_history`, `EarthScreens.item_history`.
  - Operation routed: `ITEM_HISTORY`.
- **Depends on:** 14, 16, 17.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Partly blocked* by G-B3 (tie direction).

### Slice 19: S7 Sync list
- **Goal:** S7 lists Awaiting sync and Conflict units oldest first, paged, and lists Rejected units for 7 days after Earth's rejection time.
- **Spec sources:** FR-028; NFR-002; architecture K8; Spec issue 3.
- **Criteria:** AC-028. Extra row .3 ("Waiting for conflict review") lands in slice 39.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `rejected_still_listed`, `StationReadTx.pending_page`, `StationReadTx.rejected_since`, `StationScreens.sync`. Route: S7 on the station.
- **Depends on:** 14, 15.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 20: Create mission
- **Goal:** A planner creates a Draft mission with capacities > 0, an Earth-assigned R… ID, and an empty manifest at version 1.
- **Spec sources:** FR-014; ResupplyMission; CargoManifest; FR-032 (capacities, server-set fields).
- **Criteria:** AC-014.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `validate_capacities`, `MissionService.create_mission`, `EarthTx.next_mission_id`, `EarthTx.append_manifest_version`. Operation routed: `CREATE_MISSION`.
- **Depends on:** 2, 7.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 21: Manifest totals
- **Goal:** Mass and volume totals are rounded to 2 decimals, with an over-capacity flag for each.
- **Spec sources:** FR-015; FR-017 (same totals).
- **Criteria:** none completed.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `manifest_totals`.
- **Depends on:** none.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Isolated because:* the rounding mode (G-B4) and rounded-versus-exact comparison (G-B5) decide boundary results.

### Slice 22: Manifest save and versioning
- **Goal:**
  - Lines can be edited only in Draft; expected arrival can also be set in Approved.
  - A changed save creates a new read-only version; a save with no change keeps the version.
  - A save against an out-of-date base version is rejected.
- **Spec sources:** FR-015; FR-016; CargoManifest; Mission lifecycle; NFR-001; FR-032.
- **Criteria:** AC-015, AC-016.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `manifest_changed`, `MissionService.save_manifest`, `MissionService.get_manifest`, `EarthTx.get_mission`, `EarthTx.get_manifest`, `EarthScreens.resupply_plan`. Operations routed: `SAVE_MANIFEST`, `GET_MANIFEST`.
- **Depends on:** 20, 21.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 23: Alert coverage in the manifest editor
- **Goal:** The editor marks each active alert Covered when quantity + line quantity ≥ minimum, otherwise Not covered.
- **Spec sources:** FR-013.
- **Criteria:** AC-013.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `alert_coverage`, `MissionService.manifest_editor`, `InventoryService.active_alerts`. Operation routed: `MANIFEST_EDITOR`.
- **Depends on:** 22.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 24: Mission state machine
- **Goal:** Only the listed transitions are allowed; every other transition raises InvalidTransition.
- **Spec sources:** Mission lifecycle; FR-021.
- **Criteria:** none completed.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** none left: `next_status` was filled in slice 2. This slice now only adds the lifecycle tests (AC-021 rows) and checks the services use it.
- **Depends on:** none.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Isolated because:* a single wrong row lets an illegal transition through in every lifecycle slice that follows.

### Slice 25: Submit for approval
- **Goal:** A draft is submitted only with at least one line and both totals within capacity. A failed submission lists every failing check.
- **Spec sources:** FR-017; Mission lifecycle.
- **Criteria:** AC-017.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `submission_failures`, `MissionService.submit`. Operation routed: `SUBMIT_MISSION`.
- **Depends on:** 22, 24.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 26: Approve and return
- **Goal:** Mission control approves after re-checking capacity, or returns the mission to Draft with a reason. Each transition is recorded in status history.
- **Spec sources:** FR-018; FR-019; FR-024 (history); NFR-001 (concurrent transitions).
- **Criteria:** AC-018, AC-019.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `MissionService.approve`, `MissionService.return_to_draft`. Operations routed: `APPROVE_MISSION`, `RETURN_MISSION`.
- **Depends on:** 25.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 27: Loading review
- **Goal:** On an Approved mission, planners record loaded quantities (≥ 0, may exceed planned) and loading issues, and see Planned, Loaded and Missing per line.
- **Spec sources:** FR-022; LoadingIssue; NFR-006.
- **Criteria:** AC-022.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:**
  - Rules: `validate_loaded_quantity`, `loading_review` (the Domain Rules function).
  - Service: `MissionService.record_loaded_quantity`, `add_loading_issue`, `loading_review`, `list_loading_issues`.
  - Store: `EarthTx.append_loading_issue`, `EarthTx.list_loading_issues`.
  - Screen: `EarthScreens.cargo_manifest`.
  - Operations routed: `RECORD_LOADED_QUANTITY`, `ADD_LOADING_ISSUE`, `LOADING_REVIEW`.
- **Depends on:** 26.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 28: Reopen and cancel
- **Goal:**
  - Reopen requires `canReopen` and a reason. It returns the mission to Draft and clears loaded quantities but keeps loading issues.
  - Cancel works only from Draft, Submitted or Approved, and requires a reason.
- **Spec sources:** FR-020; FR-021; Mission lifecycle; LoadingIssue.
- **Criteria:** AC-020, AC-021.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `MissionService.reopen`, `MissionService.cancel`. Operations routed: `REOPEN_MISSION`, `CANCEL_MISSION`.
- **Depends on:** 27.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 29: Confirm dispatch
- **Goal:** Dispatch requires a loaded quantity on every line and an expected arrival. A loading shortfall shows as a warning but does not block. `dispatchedAt` is recorded.
- **Spec sources:** FR-023; Mission lifecycle.
- **Criteria:** AC-023.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `dispatch_failures`, `MissionService.confirm_dispatch`. Operation routed: `CONFIRM_DISPATCH`.
- **Depends on:** 27.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 30: Mission status view (both sites)
- **Goal:** S4, S5 and S6 show status, expected arrival, manifest version and status history with time and user. Earlier manifest versions can be opened read-only.
- **Spec sources:** FR-024; CargoManifest; Description (S4–S6); architecture K7.
- **Criteria:** AC-024.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:**
  - Earth: `MissionService.get_mission`, `MissionService.list_missions`, `EarthScreens.mission_status`.
  - Station screens: `StationScreens.mission_status`, `cargo_manifest`, `resupply_plan`.
  - Station store: `StationReadTx.get_mission`, `StationReadTx.get_manifest`.
  - Operations routed: `GET_MISSION`, `LIST_MISSIONS`.
- **Depends on:** 8, 29.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 31: Station receipt and discrepancies (offline)
- **Goal:** Recording a receipt on board is one commit containing:
  - the mission moved to Received with a new `receiptId`;
  - a Receipt update per line with quantity > 0;
  - a discrepancy per line where received differs from planned, and one per unlisted item;
  - the alert changes.
- **Spec sources:** FR-025 (station side); FR-026; NFR-001; FR-012; architecture K3.
- **Criteria:** AC-012. Its scenario "resolved by restock" needs a receipt.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:**
  - Rules: `validate_receipt`, `receipt_discrepancies`, `canonical_receipt_content`.
  - Command Handler: `StationCommandHandler.record_receipt`.
  - Station store: `StationWriteTx.append_receipt`, `append_status_history`, `append_discrepancy`, `StationReadTx.list_discrepancies`.
  - Route: station action `RECORD_RECEIPT`.
- **Depends on:** 13, 14, 30.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 32: Clock correction and drift warning
- **Goal:** The station clock takes Earth time at each handshake, measures its drift rate, and warns the crew when the drift bound exceeds 30 s.
- **Spec sources:** NFR-005; architecture K15, K16; Priority note on bulk rejection after long outages.
- **Criteria:** none completed. Extra row AC-002.6 is exercised here.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `StationClock.apply_earth_time`, `StationClock.drift_bound`, `StationClock.drift_warning`.
- **Depends on:** 1.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Isolated because:* the offset arithmetic and the bound are easy to get subtly wrong, and errors cause bulk rejections later.

### Slice 33: Sync session: link check, handshake, resume point
- **Goal:** The Sync Agent checks the link every 30 s, independently of backoff. Each contact is recorded on Earth. A handshake corrects the clock and returns where to resume. Retry backoff is capped at 60 s.
- **Spec sources:** NFR-004; FR-002; NFR-003 (station credential); architecture K11, K12, K14, flow steps 10–11.
- **Criteria:** none completed.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `SyncAgent.run`, `SyncAgent.check_link`, `SyncAgent.handshake`, `SyncAgent.link_status`, `EarthGateway.handle_station`.
- **Depends on:** 7, 8, 32.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Blocked* by Design question 9 (no transport).

### Slice 34: Signature verification on Earth
- **Goal:** Earth identifies the signer from the signature. It rejects missing or invalid signatures and keys revoked before the update's event time.
- **Spec sources:** NFR-003; architecture K10, flow step 13.
- **Criteria:** none completed.
- **Tests that should turn green:** none currently failing. Unskipping `test_AT03_6_update_signed_by_planner_rejected` belongs here.
- **Skeleton to fill in:** `SyncEndpoint.verify_signer`.
- **Depends on:** 12.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Isolated because:* the revocation-versus-event-time comparison is easy to invert.

### Slice 35: Push station updates: accepted path
- **Goal:** Sendable updates go to Earth in sequence order. Earth applies each one in its own replicated transaction with `recordedBy` set to the signer, re-evaluates the alert, acknowledges with the new version, and the station marks it Synchronized.
- **Spec sources:** FR-029; NFR-001; NFR-004; NFR-008; architecture K5, K13, flow steps 12, 16–19.
- **Criteria:** none completed.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:**
  - Earth: `SyncEndpoint.receive_update`, `InventoryService.apply_station_update` (APPLY path only; slice 39 extends it).
  - Station: `SyncAgent.send_pending`, `SyncAgent.apply_outcome`, `StationReadTx.sendable_after`.
  - Earth store: `EarthTx.set_committed_station_sequence`, `put_outcome`, `set_sync_status`.
- **Depends on:** 14, 33, 34.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 36: Deduplication by updateId
- **Goal:** A resend with identical content gets the stored outcome. A resend with the same ID but different content is Rejected. A lost acknowledgement never causes a double apply.
- **Spec sources:** FR-029; architecture flow steps 14 and 18, Further decisions (content hash).
- **Criteria:** none completed.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `EarthTx.get_outcome`. Extends `SyncEndpoint.receive_update`.
- **Depends on:** 35.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Isolated because:* hash coverage and identical-versus-altered handling are the core of Goal 5.

### Slice 37: Earth request validation
- **Goal:**
  - Earth rejects an event time more than 5 minutes in the future, a base version newer than the item's, and empty or over-length text.
  - Earth ignores server-set fields sent by the client.
  - `recordedBy` always comes from the signature.
- **Spec sources:** FR-032; NFR-003.
- **Criteria:** AC-032.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `validate_event_time`, `validate_base_version`. Extends `SyncEndpoint.receive_update`.
- **Depends on:** 11, 36.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 38: Pull Earth changes, replay, full sync
- **Goal:**
  - The station pulls Earth changes made before the pull started.
  - It rebases each item on the Earth version and replays its own unacknowledged, non-rejected updates.
  - It records the full-sync time on both sides.
- **Spec sources:** FR-029 (pull; Rejected effect removed); FR-002 (fully completed); FR-010 ("reaches the station on the next sync"); User (records and keys reach the station on sync); architecture flow steps 20–22.
- **Criteria:** AC-010, AC-029.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:**
  - Station agent: `SyncAgent.sync_now`, `pull_changes`, `apply_change`.
  - Earth endpoint: `SyncEndpoint.change_feed`, `complete_sync`, `close_session`.
  - Stores: `EarthTx.change_feed`, `StationReadTx.pull_cursor`, `StationWriteTx.set_pull_cursor`.
  - Route: station action `SYNC_NOW` (blocked by Design question 4).
- **Depends on:** 17, 35, 36, 37.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 39: Conflict detection
- **Goal:**
  - An out-of-date update merges when it touches only other fields, or when the clash is Usage or Receipt deltas.
  - It is flagged Conflict when the same field changed from another source, a Correction meets any quantity change, or the result would be < 0.
  - The station keeps its local value marked "Review required" and holds later updates on that item.
- **Spec sources:** FR-030; FR-028 ("Waiting for conflict review"); FR-029 (held updates); architecture Further decisions (source of field changes; Correction rule; held updates).
- **Criteria:** AC-030.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:**
  - Rule: `merge_or_conflict`.
  - Earth: `EarthTx.field_changes_since`, `append_conflict`, `list_open_conflicts`, `InventoryService.open_conflicts`.
  - Station: `StationWriteTx.put_conflict`, `StationReadTx.open_conflicts`.
  - Operation routed: `LIST_CONFLICTS`.
  - Extends `InventoryService.apply_station_update`, `StationReadTx.sendable_after` and `SyncAgent.apply_change`.
- **Depends on:** 38.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.
- *Blocked in part* by Design question 5 (AC-030.1 needs an Earth location change that no function provides).

### Slice 40: Conflict resolution
- **Goal:** Mission control keeps the local or the Earth value, with a reason. The first resolution wins. The result is a new Earth version and an E… Resolution update, and held updates are then released in order.
- **Spec sources:** FR-031; FR-032 (resolution for an update not in conflict); NFR-001; NFR-006; Spec issue 1.
- **Criteria:** AC-031.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `InventoryService.resolve_conflict`, `EarthTx.get_conflict`, `EarthTx.append_resolution`, `EarthTx.get_update`, `EarthScreens.sync`. Operation routed: `RESOLVE_CONFLICT`.
- **Depends on:** 39.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 41: Receipt sync as one unit
- **Goal:**
  - A receipt reaches Earth as one unit deduplicated by `receiptId`: mission Received, Receipt updates applied, discrepancies stored.
  - It waits whole behind any open conflict.
  - Mission control resolves discrepancies with a note.
- **Spec sources:** FR-025; FR-026; FR-029 (resend rules); NFR-001; architecture K13; Spec issue 2.
- **Criteria:** AC-025, AC-026.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `SyncEndpoint.receive_receipt`, `MissionService.apply_receipt`, `MissionService.resolve_discrepancy`, `MissionService.list_discrepancies`, `EarthTx.get_discrepancy`, `EarthTx.list_discrepancies`. Operations routed: `RESOLVE_DISCREPANCY`, `LIST_DISCREPANCIES`.
- **Depends on:** 31, 36, 39, 40.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

### Slice 42: Serve both sites
- **Goal:** The onboard host serves S1–S7 to station devices and Earth serves them to workstations, with every `Operation` handler registered at start-up.
- **Spec sources:** Description (screens, global navigation); architecture §2 (deployment).
- **Criteria:** none completed.
- **Tests that should turn green:** none in the suite yet.
- **Skeleton to fill in:** `StationScreens.serve`, `EarthScreens.serve`. Also the `handlers` map in `ssir/earth/__main__.py` (wiring only).
- **Depends on:** all earlier slices.
- **Done when:** the listed tests pass and no previously passing test fails.
- **Status:** not started.

---

## Leftovers

**Criteria that fit no slice:** none. All 32 criteria are each assigned to exactly one slice.

**Failing tests that fit no slice:** none. All 37 failing test methods are each assigned to exactly one slice.

**Skipped test:** `test_AT03_6_update_signed_by_planner_rejected`. It is skipped, not failing, so it is assigned to no slice. Unskip it in slice 34 once Design question 8 is answered.

**Functions or routes no slice fills:** none. All 218 stubs and all 28 `Operation`s are each assigned once. The only exception is that slice 38's `SYNC_NOW` route has no legal call path (Design question 4).

**Criteria with no tests in the suite.** Write these before starting the slice that owns them: AC-002 and AC-005 through AC-032.

---

## Design questions

These need an answer before the named slice can finish. None is resolved here.

1. **Private key provisioning (slice 12).** K9 stores each private key encrypted on board, but nothing writes it. `StationReadTx.get_encrypted_private_key` exists, and there is no `put_` counterpart (contracts gap 4). The pull in slice 38 carries public keys only.
2. **Station link state on the banner (slice 8).** Station Screens may depend only on the Command Handler, Onboard Store, Clock and Domain Rules. Link availability lives in `SyncAgent.link_status`, and the Onboard Store has no last-contact field.
3. **Earth S1 data source (slice 9).** No service method returns recent activity or the reported pending count; only `EarthTx` has them. The `DASHBOARD` handler would have to read the store through the Gateway, or a service method needs to be added.
4. **"Sync on demand" (FR-029, slice 38).** Nothing that Screens may depend on can reach the Sync Agent, so the `SYNC_NOW` action has no legal path.
5. **Earth-side location change (slice 39).** AC-030.1 has mission control "correct its location to Store C on Earth". However:
   - `CorrectionField` covers only quantity and expiry;
   - `ItemEdit` has no `stored_at`;
   - there is no move `Operation`.

   So no function can produce that Earth change. Either the spec scenario changes, or Earth gets a way to set location.
6. **What "most recently changed" means (slice 5).** `ResupplyMission` has no updated-at field. `test_AT01_4` implies it is the latest status-history time, which ignores manifest saves such as an expected-arrival change on an Approved mission.
7. **Session validity on station screens (slice 12).** The AT01 station tests build a `Session` directly, without signing in. If screens start checking sessions with Station Identity (the contract lists `Unauthenticated`), those tests will regress. Contracts also provide no "is this session active" function.
8. **Signature algorithm and test keys (slices 12 and 34).** No algorithm is named, and the fixture users have `public_keys=()`. `cryptography` is installed; `nacl` is not. The choice also decides how AT03_6 builds keys.
9. **Sync transport (slices 33–41).** `SyncTransport` is an interface only (contracts gap 6). Tests need an in-process fake that calls `EarthGateway.handle_station`, and its shape is undecided.
10. **Earth Store backend versus K5 (slice 7).** The tests use `sqlite:///…` DSNs. K5 requires acknowledgement only after a commit on a synchronous replica, which SQLite cannot provide.
11. **Station versus Earth updates in the Earth Store (slice 7).** `EarthTx.append_update` assigns E… IDs to "Earth updates", but nothing defines how it tells a station update from an Earth one. AT01_7 passes a Usage update with `display_id=""`, no signature and no sequence.
12. **Crew calling Earth `CORRECT_ITEM` (slice 2 and 17).** FR-009 lets crew correct stock, so `is_permitted(crew, CORRECT_ITEM)` must be true for the station. The same shared table then lets a crew token call the Earth Operation directly and bypass signing. Should permissions depend on the site?
13. **Open spec issues that change behavior.**
    - Architecture Spec issue 1 (a held update re-checked after a resolution) affects slice 40.
    - Spec issue 2 (a Rejected receipt) affects slice 41.
    - Gaps G-B1 to G-B7 block the boundary rows in slices 6, 8, 18, 21, 27 and 37.

## Test issues

No test was changed.

1. **AT03_6 is skipped as blocked.** It cannot run until Design question 8 is answered.
2. **AT01_6 is weaker than test-plan row AC-001.6.** The plan expects Earth S1 to *show* 7. The test only reads `reported_pending_count` from the store; `EarthScreens.dashboard` is never exercised.
3. **AT01_7 checks only Earth.** Test-plan row AC-001.7 is about recent activity on S1. The test checks event kinds in the Earth Store only, so `StationReadTx.recent_events` has no all-kinds check.
4. **AT01_7 seeds an inconsistent mission.** It stores R12 as Submitted, then appends an Approved status-history entry. The fixture's own history entry may also be stored by `put_mission`. The test asserts only the set of event kinds, so this is harmless, but it is not a valid domain state.
5. **AT01_1_dashboard_screen skips a scenario line.** It does not check AC-001's "up to 10 recent activity entries, each with a time and description" on the rendered page.
6. **AT03 builds its Gateway on an unopened store.** This is a constraint, not an error: `handle` must not touch the store for screen operations. The tests also send `{"ref": "R12"}` to every operation, so the Gateway must not validate payload shape.
7. **AT04_8 times only part of NFR-007 on the station.** The station test times `find_by_barcode` only. Name search on the station is timed only through the pure `filter_items` over an in-memory list, not through the Onboard Store or `StationScreens.inventory`.

---

**Next action:** Start Slice 1 (thin path: station S1 pending count) by making `test_AT01_5_pending_excludes_rejected` pass.
