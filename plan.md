# Implementation Plan — David Wang
  
## 1. Overview
This implementation plan divides the system into ordered implementation slices. Each slice implements a specific feature across the existing modules and REST API routes. The first two slices implement two features: inventory lookup and inventory quantity updates with audit logging. 

The remaining slices are the planned implementation order for the other requirements. All slices will implement only the functions and routes listed for that slice, follow the existing contracts, and pass its corresponding acceptance tests without failing any previous passed tests. Additionally, all slices start with the status `not started`.

## 2. Initial Test Run
The previous supplied test run was executed using: `python -m pytest -v` on Python a 3.11+, FastAPI and pytest framework. Twenty HTTP 501 route tests and one OpenAPI route-registration test were conducted in the test file `tests/test_contracts.py` and No tests were failed in the baseline run. Currently, two new test files, `tests/test_inventory_lookup.py` and `tests/test_inventory_quantity.py` are created for Slice 1 and 2.

## 3. Implementation Slices

### Slice 1 — Inventory Lookup

**Goal:** Allow an authenticated Station Inventory Crew member to retrieve an existing inventory item's current details from local storage.

**Spec sources:**
- Domain Model: `User`, `InventoryItem`
- FR1
- AC1
- NFR1, NFR5, NFR6

**Criteria:** AC1

**Tests that should turn green:**

Planned tests in `tests/test_inventory_lookup.py`:

- `test_AT01_01_find_existing_item`
- `test_AT_X01_find_item_while_earth_is_unavailable`
- `test_AT_X12_item_not_found`
- `test_AT_X07_inventory_search_meets_performance_target`

The following checks require manual or performance testing rather than an ordinary REST API test:

- AT01-02: Find an item within two interactions.
- AT01-03: Verify that four interactions exceed the requirement.
- AT-X08: Performance control with only 94 of 100 searches meeting the target.
- AT-X09: Verify clear item names and units and that warnings do not rely on color alone.

**Skeleton to fill in:**

Authentication and Authorization:
- `authenticate`
- `authorize` (initial inventory-view permission)

Local Data Storage:
- `get_user`
- `get_inventory_item`

Inventory Management:
- `find_item`

User Interface:
- `GET /inventory/{item_id}` (`get_inventory_item` route handler)

**Depends on:** None. This is the first thin end-to-end implementation path.

**Done when:**
- An authenticated request retrieves the correct stored item.
- The returned information contains the item ID, name, quantity, unit, location, and condition.
- A nonexistent item produces HTTP 404.
- The local lookup works when Earth communication is unavailable.
- The associated automated tests pass and previously passing regression tests remain passing.

**Status:** not started

---

### Slice 2 — Set Inventory Quantity and Audit the Change

**Goal:** Allow an authorized crew member to set an inventory item's quantity, reject negative quantities, save accepted changes, and record an audit entry.

**Spec sources:**
- Domain Model: `InventoryItem`, `InventoryUpdate`, `AuditRecord`, `User`
- FR2
- FR12
- AC4
- AC17

**Criteria:** AC4, AC17

**Tests that should turn green:**

Planned tests in `tests/test_inventory_quantity.py`:

- `test_AT04_01_reject_negative_quantity`
- `test_AT04_02_accept_zero_quantity`
- `test_AT17_01_record_user_time_and_changed_values`

The tests should verify that:
- Setting a quantity to -1 returns HTTP 422.
- The original inventory quantity remains unchanged after rejection.
- Setting a quantity to zero returns HTTP 200.
- An accepted quantity update creates one inventory update and one audit record.
- The audit record contains the acting user, fixed test timestamp, affected item, previous quantity, and new quantity.

**Skeleton to fill in:**

Inventory Management:
- `set_quantity`

Local Data Storage:
- `get_inventory_item` (reuse Slice 1)
- `save_inventory_item`
- `save_inventory_update`

Audit Logging:
- `record_event`
- `list_records`

Local Data Storage:
- `save_audit_record`
- `list_audit_records`

User Interface:
- `PATCH /inventory/{item_id}/quantity` (`update_inventory_quantity` route handler)
- `GET /audit/records` (`get_audit_records` route handler)

**Depends on:** Slice 1, for authentication, authorization, and inventory retrieval.

**Done when:**
- Negative quantities are rejected without changing inventory or creating an accepted update.
- Zero is accepted.
- Accepted changes are saved and can be retrieved.
- The audit record contains the required identity, timestamp, and change details.
- All associated tests pass and previously passing regression tests remain passing.

**Status:** not started

---

### Slice 3 — Record Usage, Identify Low Stock, and Support Handovers

**Goal:** Allow crew members to record item usage, enforce available-quantity validation, identify low-stock items, and retrieve inventory update history.

**Spec sources:**
- Domain Model: `InventoryItem`, `InventoryUpdate`, `SupplyAlert`, `User`
- FR2, FR3, FR4
- AC2, AC3, AC5

**Criteria:** AC2, AC3, AC5

**Tests that should turn green:**

- `test_AT02_01_record_usage_and_flag_low_stock`
- `test_AT02_02_quantity_at_minimum_is_not_low_stock`
- `test_AT02_03_list_low_stock_items_with_importance`
- `test_AT03_01_reject_usage_above_available_quantity`
- `test_AT03_02_accept_usage_equal_to_available_quantity`
- `test_AT03_03_accept_usage_just_below_available_quantity`
- `test_AT05_01_saved_change_visible_to_next_shift`
- `test_AT05_02_apply_same_validation_to_different_crew_members`

**Skeleton to fill in:**

Inventory Management:
- `record_usage`
- `get_update_history`
- `list_inventory`

Resupply Planning:
- `get_resupply_needs`

Local Data Storage:
- `list_inventory_items`
- `list_inventory_updates`

User Interface:
- `POST /inventory/{item_id}/usage` (`record_inventory_usage` route handler)
- `GET /inventory/{item_id}/updates` (`get_inventory_updates` route handler)
- `GET /resupply/needs` (`get_resupply_needs_route` route handler)

**Depends on:** Slices 1 and 2.

**Done when:**
- Valid usage updates the stored quantity and creates an update record.
- Usage above available stock and invalid negative usage are rejected.
- Low-stock results use the configured minimum quantity and display item importance.
- A quantity equal to the minimum stock level is not flagged as below minimum.
- Another crew member can retrieve the saved quantity and update history.
- All associated tests pass and previously passing regression tests remain passing.

**Status:** not started

---

### Slice 4 — Cargo Capacity Validation and Mission Submission

**Goal:** Calculate cargo weight and volume, reject missing measurements or capacity violations, and prevent invalid mission submissions.

**Spec sources:**
- Domain Model: `InventoryItem`, `ResupplyMission`, `CargoManifest`, `ManifestLine`
- FR5, FR6
- AC6, AC7, AC8

**Criteria:** AC6, AC7, AC8

**Tests that should turn green:**

- `test_AT06_01_reject_weight_above_capacity`
- `test_AT06_02_accept_weight_just_inside_capacity`
- `test_AT06_03_accept_weight_at_capacity`
- `test_AT06_04_reject_weight_just_outside_capacity`
- `test_AT07_01_reject_volume_above_capacity`
- `test_AT07_02_accept_volume_at_capacity`
- `test_AT07_03_accept_volume_just_inside_capacity`
- `test_AT08_01_reject_missing_unit_weight`
- `test_AT08_02_accept_submission_after_unit_weight_is_supplied`
- `test_AT08_03_reject_missing_unit_volume`
- `test_AT08_04_accept_submission_after_unit_volume_is_supplied`

**Skeleton to fill in:**

Resupply Planning:
- `check_capacity`

Mission and Shipment Management:
- `submit_manifest`

Local Data Storage:
- `get_mission`
- `save_mission`
- `get_manifest`

User Interface:
- `POST /missions/{mission_id}/capacity-check` (`check_mission_capacity` route handler)
- `POST /missions/{mission_id}/submit` (`submit_mission_manifest` route handler)

**Depends on:** Slice 1, for authentication and inventory retrieval.

**Done when:**
- Total cargo weight and volume are calculated from item quantities and unit measurements.
- Cargo at the specified capacity boundary is accepted.
- Cargo exceeding either capacity is rejected.
- Missing required weight or volume measurements prevent submission.
- A rejected submission leaves the mission in Draft and creates no submission record.
- An accepted submission moves the mission to Submitted.
- All associated tests pass and previously passing regression tests remain passing.

**Status:** not started

---

### Slice 5 — Create and Update Manifests, Approve Missions, and Confirm Dispatch

**Goal:** Manage existing missions' cargo manifests and enforce the required submission, approval, and dispatch sequence.

**Spec sources:**
- Domain Model: `ResupplyMission`, `CargoManifest`, `ManifestLine`, `AuditRecord`
- FR6, FR12
- AC9

**Criteria:** AC9

**Tests that should turn green:**

- `test_AT09_01_edit_approved_manifest_returns_mission_to_draft`
- `test_AT09_02_reject_dispatch_before_resubmission_and_reapproval`
- `test_AT09_03_allow_dispatch_after_resubmission_and_reapproval`
- `test_AT09_04_edit_submitted_manifest_returns_mission_to_draft`
- `test_AT09_05_create_manifest_for_existing_draft_mission`
- `test_AT09_06_update_draft_manifest`

**Skeleton to fill in:**

Mission and Shipment Management:
- `create_manifest`
- `update_manifest`
- `approve_mission`
- `confirm_dispatch`

Local Data Storage:
- `get_mission` (reuse existing interface)
- `save_mission`
- `get_manifest`
- `save_manifest`

User Interface:
- `POST /missions/{mission_id}/manifest` (`create_mission_manifest` route handler)
- `PATCH /missions/{mission_id}/manifest` (`update_mission_manifest` route handler)
- `POST /missions/{mission_id}/approval` (`approve_resupply_mission` route handler)
- `POST /missions/{mission_id}/dispatch` (`dispatch_resupply_mission` route handler)

**Depends on:** Slice 4, for mission submission and capacity validation.

**Done when:**
- A manifest can be created for an existing Draft mission.
- An existing Draft manifest can be updated.
- Editing a Submitted or Approved manifest before dispatch returns the mission to Draft.
- Dispatch is rejected unless the mission has been resubmitted and approved.
- The normal lifecycle is Draft → Submitted → Approved → Shipped.
- All associated tests pass and previously passing regression tests remain passing.

**Status:** not started

---

### Slice 6 — Save Inventory Changes During Communication Outages

**Goal:** Preserve inventory changes locally during communication outages and expose the pending update count and last successful synchronization time.

**Spec sources:**
- Domain Model: `InventoryItem`, `InventoryUpdate`
- FR10
- AC13
- NFR1, NFR2

**Criteria:** AC13

**Tests that should turn green:**

- `test_AT13_01_offline_update_survives_application_restart`

**Skeleton to fill in:**

Local Data Storage:
- `list_pending_updates`
- `get_last_successful_sync_time`

Synchronization:
- `get_status`

User Interface:
- `GET /sync/status` (`get_synchronization_status` route handler)

Previously implemented inventory update and usage functions must save changes locally regardless of Earth communication status.

**Depends on:** Slices 2 and 3, for saved quantity changes and update records.

**Done when:**
- A valid inventory change can be saved while Earth communication is unavailable.
- The saved quantity remains available after application restart.
- The update remains pending synchronization.
- The pending update count is correct.
- The last successful synchronization time remains unchanged during the outage.
- All associated tests pass and previously passing regression tests remain passing.

**Status:** not started

---

### Slice 7 — Ground Control Monitoring and Cargo Loading

**Goal:** Allow Ground Mission Control to view station inventory, recent changes, synchronization information, mission details, and recorded cargo-loading differences.

**Spec sources:**
- Domain Model: `InventoryItem`, `InventoryUpdate`, `ResupplyMission`, `CargoManifest`, `ManifestLine`
- FR7, FR8, FR9
- AC10, AC11

**Criteria:** AC10, AC11

**Tests that should turn green:**

- `test_AT10_01_ground_inventory_shows_records_updates_and_sync_time`
- `test_AT11_01_record_loading_shortage`
- `test_AT_X10_mission_details_include_status_arrival_and_history`

**Skeleton to fill in:**

Inventory Management:
- `list_inventory`
- `get_update_history` (reuse existing interface)

Mission and Shipment Management:
- `record_loading`
- `get_mission`

Synchronization:
- `get_status` (reuse existing interface)

Local Data Storage:
- `list_pending_updates`
- `get_last_successful_sync_time`
- `get_mission`
- `get_manifest`
- `save_mission`
- `save_manifest`

User Interface:
- `GET /ground/inventory` (`get_ground_inventory` route handler)
- `POST /missions/{mission_id}/loading` (`record_mission_loading` route handler)
- `GET /missions/{mission_id}` (`get_mission_details` route handler)

**Depends on:** Slices 3, 5, and 6.

**Done when:**
- Ground Mission Control can retrieve current inventory and recent updates.
- The latest successful synchronization time is included in the returned information.
- Planned and loaded quantities are compared correctly.
- Loading differences can be saved.
- Mission details include status, expected arrival, and status history.
- All associated tests pass and previously passing regression tests remain passing.

**Status:** not started

---

### Slice 8 — Receive Shipments and Update Inventory

**Goal:** Allow authorized Station Inventory Crew members to record actual cargo receipts, update inventory, and record shortages and damage.

**Spec sources:**
- Domain Model: `InventoryItem`, `ResupplyMission`, `CargoManifest`, `ManifestLine`, `AuditRecord`
- FR9, FR12
- AC12

**Criteria:** AC12

**Tests that should turn green:**

- `test_AT12_01_record_partial_shipment_receipt`
- `test_AT_X11_record_damaged_cargo_information`

**Skeleton to fill in:**

Mission and Shipment Management:
- `record_shipment_receipt`

Inventory Management:
- `add_received_quantity`

Local Data Storage:
- `get_mission`
- `save_mission`
- `get_manifest`
- `save_manifest`
- `save_inventory_item`
- `save_inventory_update`

Audit Logging:
- `record_event`
- `save_audit_record`

User Interface:
- `POST /missions/{mission_id}/receipt` (`receive_mission_shipment` route handler)

**Depends on:** Slices 2 and 5, for inventory update and mission status functionality.

**Done when:**
- Actual received quantities are recorded.
- Usable received quantities are added to inventory.
- Shortages are calculated from planned and received quantities.
- Damage information is recorded.
- The mission changes from Shipped to Received.
- The normal partial-receipt scenario passes.
- All associated tests pass and previously passing regression tests remain passing.

**Status:** not started

---

### Slice 9 — Synchronization and Conflict Resolution

**Goal:** Synchronize pending inventory updates without duplicate application, preserve conflicting station and Earth values, and support authorized conflict resolution.

**Spec sources:**
- Domain Model: `InventoryUpdate`, `SyncConflict`, `AuditRecord`
- FR11, FR12
- AC14, AC15
- NFR2, NFR3, NFR4

**Criteria:** AC14, AC15

**Tests that should turn green:**

- `test_AT14_01_retry_does_not_apply_update_twice`
- `test_AT14_02_accept_new_update_id`
- `test_AT14_03_assign_unique_ids_to_separate_updates`
- `test_AT15_01_retain_both_values_when_conflict_detected`
- `test_AT15_02_authorized_reviewer_resolves_conflict_and_audit`
- `test_AT15_03_reject_unauthorized_conflict_resolution`
- `test_AT_X02_pending_updates_survive_restart_and_failed_sync`

The following synchronization timing and security checks also belong to this slice:

- `test_AT_X03_start_sync_within_59_seconds`
- `test_AT_X04_start_sync_at_60_seconds`
- `test_AT_X05_detect_sync_start_after_60_seconds`
- `test_AT_X06_encryption_at_rest_and_in_transit`

**Skeleton to fill in:**

Synchronization:
- `synchronize_pending_updates`
- `list_conflicts`
- `resolve_conflict`

Local Data Storage:
- `get_inventory_update`
- `list_pending_updates`
- `mark_update_acknowledged`
- `save_sync_conflict`
- `list_sync_conflicts`

Audit Logging:
- `record_event`
- `save_audit_record`

User Interface:
- `POST /sync` (`synchronize_updates` route handler)
- `GET /sync/conflicts` (`get_synchronization_conflicts` route handler)
- `POST /sync/conflicts/{conflict_id}/resolution` (`resolve_synchronization_conflict` route handler)

**Depends on:** Slices 2, 6, and 8, for persistent inventory updates, pending records, and audit logging.

**Done when:**
- Pending updates are sent to the Earth-side integration.
- Previously accepted update IDs are not applied twice.
- New unique update IDs can be accepted.
- Failed updates remain pending.
- Both competing values are retained when a conflict is identified.
- An authorized reviewer can select a value and provide a reason.
- Conflict resolution is audited.
- Synchronization timing and encryption requirements are verified using an agreed test method.
- All associated tests pass and previously passing regression tests remain passing.

**Status:** not started

---

### Slice 10 — Authorization Enforcement Across Protected Operations

**Goal:** Enforce authentication and permission checks for all protected operations and verify that unauthorized users cannot change system records.

**Spec sources:**
- Domain Model: `User`
- FR12
- AC16
- NFR4

**Criteria:** AC16

**Tests that should turn green:**

- `test_AT16_01_reject_unauthorized_mission_approval`
- `test_AT16_02_allow_authorized_mission_approval`
- `test_AT16_03_reject_unauthorized_inventory_change`
- `test_AT16_04_reject_unauthorized_dispatch`
- `test_AT16_05_reject_unauthorized_cargo_receipt`
- `test_AT16_06_reject_unauthenticated_inventory_access`

**Skeleton to fill in:**

Authentication and Authorization:
- `authenticate` (reuse and verify the existing implementation)
- `authorize` (complete the permission checks for protected actions)

The existing protected routes must enforce the corresponding permission checks:

- `GET /inventory/{item_id}`
- `PATCH /inventory/{item_id}/quantity`
- `POST /inventory/{item_id}/usage`
- `POST /missions/{mission_id}/approval`
- `POST /missions/{mission_id}/dispatch`
- `POST /missions/{mission_id}/receipt`
- `POST /sync/conflicts/{conflict_id}/resolution`

No new route is required.

**Depends on:** Slices 1, 2, 3, 5, 8, and 9.

**Done when:**
- Missing or invalid authentication returns HTTP 401.
- Authenticated users without the required permission receive HTTP 403.
- Authorized users can perform the corresponding operations.
- Rejected operations do not modify inventory or mission state and do not create accepted operation records.
- All associated tests pass and previously passing regression tests remain passing.

**Status:** not started

## 4. Design Questions

The following questions are not fully answered by the current specification, architecture, or contracts. They should be resolved when the relevant slice is implemented. No additional public functions, modules, or API routes should be introduced without updating the contracts first.

1. **Authentication mechanism:** The contracts require an authentication verifier, but do not specify how an Authorization token maps to a user. A simple test authentication setup is needed before Slice 1 can be completed.

2. **Permission policy:** The exact mapping between the three user roles and protected operations is not defined. Tests currently assume explicitly configured permissions.

3. **Persistent storage:** The architecture requires local persistent storage, but the database technology and initialization process are unspecified.

4. **Atomic inventory updates:** The architecture says that the quantity, update history, audit record, and pending synchronization record should be saved together. The storage contracts expose separate save functions but do not explicitly define transaction behavior.

5. **Clock and ID injection:** The contracts mention an injected clock and ID generator, but do not define how they are supplied to the functions. This matters for fixed-time tests and unique update IDs.

6. **Quantity input types:** Fractional quantities and non-numeric values are not fully specified. AT-X14 should remain unresolved until this is clarified.

7. **Mission creation:** The system has no functional requirement or API for creating missions. Tests must use an existing seeded Draft mission.

8. **Mission lifecycle:** The main states are Draft, Submitted, Approved, Shipped, and Received. Other transitions, particularly cancellation, remain undefined.

9. **Shipment damage and duplicate receipts:** The specification requires damage to be recorded and received quantities to be added once, but does not define how damaged quantities affect usable inventory or how duplicate receipt requests are recognized.

10. **Earth-side integration:** The external service API, acknowledgement format, and authentication mechanism are not defined.

11. **Synchronization scheduling:** NFR3 requires synchronization to start within 60 seconds after communication recovery, but the contracts do not define an explicit connection-restored event or scheduling interface.

12. **Last successful synchronization time:** The storage contract provides a getter but does not explicitly state which operation updates this timestamp. Clarify whether successful acknowledgement processing updates it.

13. **Encryption:** NFR4 requires encryption at rest and in transit, but the encryption technology and key-management method are unspecified.

14. **Performance test environment:** The team must agree on the device and test conditions for the 10,000-record search performance requirement.

## 5. Test Issues
### 5.1 Existing HTTP 501 tests
**`test_contracts.py` expects all API routes to return HTTP 501. That was the expectation for an initial skeleton with no business functions implemented, but once a route is implemented, its old HTTP 501 assertion conflicts with the expected successful behavior. If these HTTP 501 assertions remain unchanged and are included in the full pytest run, the tests for implemented endpoints will fail because the endpoints should return their actual results instead of HTTP 501.**

The affected existing tests are grouped below by their corresponding implementation slice:
| Slice | Existing test names currently expecting HTTP 501 |
|---|---|
| Slice 1 | `test_api_route_returns_501[FR1-find-item]` |
| Slice 2 | `test_api_route_returns_501[FR2-update-quantity]`, `test_api_route_returns_501[FR12-audit-records]` |
| Slice 3 | `test_api_route_returns_501[FR2-record-usage]`, `test_api_route_returns_501[FR3-update-history]`, `test_api_route_returns_501[FR4-resupply-needs]` |
| Slice 4 | `test_api_route_returns_501[FR5-capacity-check]`, `test_api_route_returns_501[FR6-submit-manifest]` |
| Slice 5 | `test_api_route_returns_501[FR6-create-manifest]`, `test_api_route_returns_501[FR6-update-manifest]`, `test_api_route_returns_501[FR12-approve-mission]`, `test_api_route_returns_501[FR12-dispatch-mission]` |
| Slice 7 | `test_api_route_returns_501[FR7-ground-inventory]`, `test_api_route_returns_501[FR8-record-loading]`, `test_api_route_returns_501[FR9-mission-details]` |
| Slice 8 | `test_api_route_returns_501[FR9-receive-shipment]` |
| Slice 6 | `test_api_route_returns_501[FR10-sync-status]` |
| Slice 9 | `test_api_route_returns_501[FR11-synchronize]`, `test_api_route_returns_501[FR11-list-conflicts]`, `test_api_route_returns_501[FR11-resolve-conflict]` |

`test_all_expected_api_operations_are_registered` should remain a route-registration regression test throughout implementation.

### 5.2 Acceptance-test and specification issues

1. **AT01-02 and AT01-03:** The interaction-count requirement is a user-interface requirement. It cannot be verified by the REST API alone.

2. **AT-X09:** The usability requirement needs a visual interface test. The current runnable application exposes REST routes and does not provide a separate browser-based dashboard.

3. **AT16-03 control:** The current control points to AT02-01, which records usage through a different request from the quantity-update operation being rejected. It is not a same-request control. This should be clarified before treating the test as conclusive.

4. **AT-X13:** Concurrent inventory updates have no specified expected behavior. Do not automate as a pass/fail test yet.

5. **AT-X14:** Fractional and non-numeric quantity handling is undefined. Do not automate as a pass/fail test yet.

6. **AT-X15:** Duplicate shipment receipt behavior is unclear. Do not automate as a pass/fail test until the expected behavior is defined.

7. **AT-X16:** Error precedence when capacity is exceeded and measurements are missing simultaneously is undefined. Do not assert a specific error order.

8. **AT-X08 and AT-X05:** These are negative controls for performance and timing limits. Their purpose is to demonstrate that an out-of-limit measurement fails the corresponding requirement, not to require the application to return a successful business response for an invalid condition.

9. **AT-X06:** Encryption verification requires an agreed method and knowledge of the selected storage and communication mechanisms.

## 6. Coverage

### Acceptance Criteria Coverage

| Acceptance Criterion | Assigned slice |
|---|---|
| AC1 — Find an Item | Slice 1 |
| AC2 — Record Usage and Flag Low Stock | Slice 3 |
| AC3 — Reject Usage Above Available Quantity | Slice 3 |
| AC4 — Reject a Negative Quantity | Slice 2 |
| AC5 — Keep Changes Consistent for Handovers | Slice 3 |
| AC6 — Enforce Cargo Weight Capacity | Slice 4 |
| AC7 — Enforce Cargo Volume Capacity | Slice 4 |
| AC8 — Require Cargo Measurements | Slice 4 |
| AC9 — Reapprove an Edited Manifest | Slice 5 |
| AC10 — View Inventory Updates from Ground Control | Slice 7 |
| AC11 — Identify a Loading Difference | Slice 7 |
| AC12 — Receive a Partial Shipment | Slice 8 |
| AC13 — Save Changes During a Communication Outage | Slice 6 |
| AC14 — Do Not Apply a Duplicated Retry Update | Slice 9 |
| AC15 — Resolve a Synchronization Conflict | Slice 9 |
| AC16 — Deny Unauthorized Actions | Slice 10 |
| AC17 — Audit an Accepted Change | Slice 2 |

Every acceptance criterion from AC1 through AC17 is assigned to exactly one slice.

### Module Function Coverage

| Architecture module | Functions assigned |
|---|---|
| User Interface | All existing REST route handlers are assigned to the corresponding feature slices. |
| Authentication and Authorization | `authenticate`, `authorize` — Slices 1 and 10 |
| Inventory Management | `find_item` — Slice 1; `set_quantity` — Slice 2; `record_usage`, `get_update_history` — Slice 3; `list_inventory` — Slice 7; `add_received_quantity` — Slice 8 |
| Resupply Planning | `get_resupply_needs` — Slice 3; `check_capacity` — Slice 4 |
| Mission and Shipment Management | `submit_manifest` — Slice 4; `create_manifest`, `update_manifest`, `approve_mission`, `confirm_dispatch` — Slice 5; `record_loading`, `get_mission` — Slice 7; `record_shipment_receipt` — Slice 8 |
| Audit Logging | `record_event`, `list_records` — Slice 2; `record_event` reused in later audited operations |
| Local Data Storage | `get_user`, `get_inventory_item` — Slice 1; inventory save and audit functions — Slice 2; inventory listing and history functions — Slice 3; mission and manifest functions — Slice 4 onward; pending update and synchronization functions — Slices 6 and 9; `get_inventory_update`, conflict storage functions — Slice 9 |
| Synchronization | `get_status` — Slice 7; `synchronize_pending_updates`, `list_conflicts`, `resolve_conflict` — Slice 9 |

### REST API Route Coverage
| REST API route | Assigned slice |
|---|---|
| `GET /inventory/{item_id}` | Slice 1 |
| `PATCH /inventory/{item_id}/quantity` | Slice 2 |
| `GET /audit/records` | Slice 2 |
| `POST /inventory/{item_id}/usage` | Slice 3 |
| `GET /inventory/{item_id}/updates` | Slice 3 |
| `GET /resupply/needs` | Slice 3 |
| `POST /missions/{mission_id}/capacity-check` | Slice 4 |
| `POST /missions/{mission_id}/submit` | Slice 4 |
| `POST /missions/{mission_id}/manifest` | Slice 5 |
| `PATCH /missions/{mission_id}/manifest` | Slice 5 |
| `POST /missions/{mission_id}/approval` | Slice 5 |
| `POST /missions/{mission_id}/dispatch` | Slice 5 |
| `GET /sync/status` | Slice 6 |
| `GET /ground/inventory` | Slice 7 |
| `POST /missions/{mission_id}/loading` | Slice 7 |
| `GET /missions/{mission_id}` | Slice 7 |
| `POST /missions/{mission_id}/receipt` | Slice 8 |
| `POST /sync` | Slice 9 |
| `GET /sync/conflicts` | Slice 9 |
| `POST /sync/conflicts/{conflict_id}/resolution` | Slice 9 |

### Unassigned Criteria, Tests, Functions, or Routes
- **Acceptance criteria without a slice:** None.
- **Currently failing tests:** None from the initial skeleton's baseline test.
- **Functions without a slice:** None among the public functions listed in `contracts.md`.
- **REST API routes without a slice:** None.
- **Unresolved exploratory tests:** AT-X13, AT-X14, AT-X15, and AT-X16 are assigned to the relevant feature areas above but remain unresolved specification probes; they are not expected to turn green until their behavior is defined.
- The existing `_execute`, `_not_implemented_response`, and `_ground_inventory_view` helpers are already present in `user_interface.py`; they are not additional architecture modules.

## 7. Implementation Order 
1. Slice 1 — Inventory Lookup
2. Slice 2 — Set Inventory Quantity and Audit the Change
3. Slice 3 — Record Usage, Identify Low Stock, and Support Handovers
4. Slice 4 — Cargo Capacity Validation and Mission Submission
5. Slice 5 — Create and Update Manifests, Approve Missions, and Confirm Dispatch
6. Slice 6 — Save Inventory Changes During Communication Outages
7. Slice 7 — Ground Control Monitoring and Cargo Loading
8. Slice 8 — Receive Shipments and Update Inventory
9. Slice 9 — Synchronization and Conflict Resolution
10. Slice 10 — Authorization Enforcement Across Protected Operations

**Note: Each slice must be implemented on its own branch. Slice 2 should ultimately be based on the updated `david` branch after Slice 1 has been merged.**
