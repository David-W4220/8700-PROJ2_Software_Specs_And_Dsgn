# Implementation Plan

The slices follow the acceptance criteria in spec.md and the module boundaries in architecture.md and contracts.md. Each acceptance criterion and acceptance test is assigned once. The test_acceptance.py tests currently fail because the skeleton routes return HTTP 501.

## Slice 1: Record supply use end to end

- **Goal:** Let an authenticated crew member record a valid supply use and receive the updated quantity and audit details.
- **Spec sources:** spec.md FR-001, AC-001, NFR6; architecture.md Sections 2–3; contracts.md Inventory Manager and REST API.
- **Criteria:** AC-001.
- **Tests that should turn green:** test_AC001_record_supply_use
- **Skeleton to fill in:** Inventory Manager.record_supply_use; User Permissions.require_authenticated_user; Station Storage.get_inventory_item, Station Storage.save_offline_change, Station Storage.get_update_history; POST /inventory/items/{item_id}/usage.
- **Depends on:** None.
- **Done when:** test_AC001_record_supply_use passes and no previously passing test fails.
- **Status:** not started.

## Slice 2: Reject usage above available quantity

- **Goal:** Reject a crew member's usage when it exceeds the item's available quantity without changing inventory or creating an update.
- **Spec sources:** spec.md FR-001, AC-002, NFR2; contracts.md Inventory Manager and REST API.
- **Criteria:** AC-002.
- **Tests that should turn green:** test_AC002_reject_overuse_and_accept_limit_control
- **Skeleton to fill in:** Extend Inventory Manager.record_supply_use validation; use Station Storage.get_inventory_item and Station Storage.get_update_history; POST /inventory/items/{item_id}/usage returns the contract's HTTP 400 validation error.
- **Depends on:** Slice 1.
- **Done when:** test_AC002_reject_overuse_and_accept_limit_control passes and no previously passing test fails.
- **Status:** not started.

## Slice 3: Reject negative usage

- **Goal:** Reject negative usage without changing inventory or creating an update, while allowing zero usage.
- **Spec sources:** spec.md FR-001, AC-003, NFR2; contracts.md Inventory Manager and REST API.
- **Criteria:** AC-003.
- **Tests that should turn green:** test_AC003_reject_negative_and_accept_zero_control
- **Skeleton to fill in:** Extend Inventory Manager.record_supply_use validation; POST /inventory/items/{item_id}/usage returns the contract's HTTP 400 validation error.
- **Depends on:** Slice 2.
- **Done when:** test_AC003_reject_negative_and_accept_zero_control passes and no previously passing test fails.
- **Status:** not started.

## Slice 4: View Earth inventory and sync time

- **Goal:** Show the Earth-side item quantities, units, and last successful synchronization time.
- **Spec sources:** spec.md FR-002, AC-004, NFR7–NFR8; architecture.md Section 2; contracts.md Inventory Interface and Ground Storage.
- **Criteria:** AC-004.
- **Tests that should turn green:** test_AC004_view_inventory_from_earth
- **Skeleton to fill in:** Inventory Interface.get_earth_inventory_view; Ground Storage.get_inventory_snapshot; GET /earth/inventory.
- **Depends on:** Slice 1.
- **Done when:** test_AC004_view_inventory_from_earth passes and no previously passing test fails.
- **Status:** not started.

## Slice 5: Save offline changes and report sync status

- **Goal:** Save an inventory change locally so it remains available in a new app session with its pending count and last successful sync time.
- **Spec sources:** spec.md FR-003, AC-005, NFR1, NFR7; architecture.md Sections 2–4; contracts.md Station Storage and REST APIs.
- **Criteria:** AC-005.
- **Tests that should turn green:** test_AC005_keep_offline_change_after_restart
- **Skeleton to fill in:** Station Storage.save_offline_change, Station Storage.get_sync_status, Station Storage.get_inventory_item; POST /station/offline/updates, GET /station/sync-status, GET /station/inventory/items/{item_id}.
- **Depends on:** Slice 1.
- **Done when:** test_AC005_keep_offline_change_after_restart passes and no previously passing test fails.
- **Status:** not started.

## Slice 6: Sync pending updates when communication returns

- **Goal:** Send pending station updates to Earth and mark accepted updates as synced.
- **Spec sources:** spec.md FR-004, AC-006, NFR1, NFR3; architecture.md Sections 2–4; contracts.md Sync Manager and Ground Storage.
- **Criteria:** AC-006.
- **Tests that should turn green:** test_AC006_sync_waiting_update
- **Skeleton to fill in:** Sync Manager.sync_pending_updates; Ground Storage.get_inventory_snapshot; POST /sync.
- **Depends on:** Slice 5.
- **Done when:** test_AC006_sync_waiting_update passes and no previously passing test fails.
- **Status:** not started.

## Slice 7: Make update retries idempotent

- **Goal:** Return an already-accepted result for a repeated update ID without applying the inventory change or audit record twice.
- **Spec sources:** spec.md FR-004, AC-007, NFR3; architecture.md Sections 2–4; contracts.md Sync Manager and REST API.
- **Criteria:** AC-007.
- **Tests that should turn green:** test_AC007_duplicate_update_is_not_applied_twice
- **Skeleton to fill in:** Sync Manager.retry_update; POST /sync/updates/{update_id}/retry; use Station Storage.get_inventory_item and Station Storage.get_update_history to preserve and inspect local state.
- **Depends on:** Slice 6.
- **Done when:** test_AC007_duplicate_update_is_not_applied_twice passes and no previously passing test fails.
- **Status:** not started.

## Slice 8: Resolve conflicting inventory changes

- **Goal:** Let an authorized reviewer select a location from a retained station/Earth conflict and record the reason, reviewer, and time.
- **Spec sources:** spec.md FR-004, AC-008, NFR4–NFR6; architecture.md Sections 2–5; contracts.md User Permissions, Conflict Review, and REST API.
- **Criteria:** AC-008.
- **Tests that should turn green:** test_AC008_resolve_conflict_and_record_audit
- **Skeleton to fill in:** User Permissions.authorize_conflict_resolution; Conflict Review.resolve_conflict; POST /conflicts/{conflict_id}/resolve.
- **Depends on:** Slice 6.
- **Done when:** test_AC008_resolve_conflict_and_record_audit passes and no previously passing test fails.
- **Status:** not started.

## Coverage check

- **Acceptance criteria with no slice:** None.
- **Tests with no slice:** None of the eight tests listed in tests/test_acceptance.py are unassigned.
- **Contract functions with no slice:** None.
- **Routes with no slice:** None of the nine routes in contracts.md are unassigned.

## Test issues

- tests/test_acceptance.py does not initialize the Given-state data described in test_plan.md. For example, the tests expect an initial water item, Earth inventory, pending update U102, already accepted update U101, and conflict conflict-1, but setUp only creates a Flask test client. The suite currently fails on the 501 skeleton responses, so the missing fixture will become visible once routes are implemented. A documented fixture/reset contract is needed so these tests can be run independently and reproducibly.
- The test plan's expected test coverage includes AC-001 through AC-008, but the executable suite tests only those eight criteria; the EXTRA-* cases are not executable tests and are not assigned as slice tests.

## Design questions

- What storage adapter or test fixture should initialize the inventory and Earth/pending/conflict states? The architecture says Station Storage uses a persistence adapter, but neither the adapter nor an initialization/reset contract is specified, and adding an unlisted module or dependency is out of scope.
- Which user roles may resolve conflicts? NFR5 requires authorization, but spec.md does not define role permissions. The AC-008 test's reviewer-1 identity is not mapped to an authorized role.
