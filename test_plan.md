# Test Plan — David Wang

## 1. Overview

This document refines the 17 acceptance criteria in `spec.md` into concrete test cases. It uses the BDD alternative from the assignment.

Each test has a unique ID. The original ACs are retained, with additional cases where needed to cover boundaries, controls, and nonfunctional requirements.

### Test conventions

- `WTR-001` represents a water inventory item measured in packs.
- Unless stated otherwise, `WTR-001` starts with 12 usable packs, minimum stock of 10, location `Store A`, and condition `Usable`.
- Test users are authenticated users with explicitly configured permissions. This avoids assuming a role-permission mapping that the specification has not defined.
- A fixed test clock is used for timestamp checks.
- Each test begins with an independent initial state unless stated otherwise.
- A rejected operation must not create an accepted update, submission, approval, dispatch, receipt, or conflict-resolution record. The relevant business state must remain unchanged.

### Proposed HTTP status codes

The specification does not define HTTP status codes. These are proposed for the FastAPI implementation and will be used consistently in `contracts.md`.

| Result | Proposed status |
|---|---:|
| Successful operation | 200 |
| Unauthenticated request | 401 |
| Authenticated but unauthorized request | 403 |
| Operation not allowed in the current state | 409 |
| Invalid input or capacity violation | 422 |

**Skeleton note:** During this milestone, the FastAPI routes return HTTP 501 because their business logic is not implemented. The expected results below describe the eventual application behavior, not the temporary skeleton response.

---

## 2. Acceptance Criteria Tests

### AC1 — Find an Item (FR1)

**AT01-01 — Find an item within three interactions**

- Given `WTR-001` has 12 packs, location `Store A`, and condition `Usable`
- When a crew member finds the item from the dashboard within three interactions
- Then the system displays its ID, name, quantity, unit, location, and condition
- Expected result: item data is returned correctly; HTTP 200
- Side effects: none

**AT01-02 — Extra: Check the interaction limit outside the requirement**

- Given `WTR-001` exists in inventory
- When a crew member needs four interactions from the dashboard to find it
- Then the interface fails the three-interaction requirement
- Expected result: usability requirement failure
- Side effects: none

*These interaction-count tests require the user interface. An API test alone cannot verify the number of interactions.*

### AC2 — Record Usage and Flag Low Stock (FR2, FR4)

**AT02-01 — Record valid usage and trigger a low-stock warning**

- Given `WTR-001` has 12 usable packs and a minimum stock level of 10
- When a crew member records 3 packs used
- Then the remaining quantity is 9 packs
- And the system displays a low-stock warning
- And the accepted update records the user's identity and time
- Expected result: HTTP 200; quantity = 9; low-stock warning = true
- Side effects: one accepted inventory update and one history entry

**AT02-02 — Extra: Quantity reaches the minimum stock level**

- Given `WTR-001` has 12 usable packs and a minimum stock level of 10
- When a crew member records 2 packs used
- Then the remaining quantity is 10 packs
- And the item is not identified as below minimum stock
- Expected result: HTTP 200; quantity = 10; low-stock warning = false
- Side effects: one accepted inventory update

**AT02-03 — Extra: List low-stock items and their importance**

- Given `WTR-001` has 9 usable packs, minimum stock of 10, and importance `Critical`
- And another item has 12 usable packs and minimum stock of 10
- When a Logistics Planner requests resupply needs
- Then `WTR-001` appears as requiring replenishment
- And its importance is displayed as `Critical`
- And the other item is not identified as low-stock
- Expected result: HTTP 200; returned items and importance match the starting data
- Side effects: none

### AC3 — Reject Usage Above Available Quantity (FR2)

**AT03-01 — Reject usage above available quantity**

- Given `WTR-001` has 4 usable packs
- When a crew member records 5 packs used
- Then the system rejects the request with a quantity validation error
- And the available quantity remains 4 packs
- Expected result: HTTP 422; error code `invalid_quantity`
- Side effects: no accepted inventory update is created; quantity remains 4

**AT03-02 — Control: Accept usage equal to available quantity**

- Given `WTR-001` has 4 usable packs
- When a crew member records 4 packs used
- Then the system accepts the request
- And the remaining quantity becomes 0
- Expected result: HTTP 200; quantity = 0
- Side effects: one accepted inventory update

### AC4 — Reject a Negative Quantity (FR2)

**AT04-01 — Reject a negative inventory quantity**

- Given `WTR-001` has 4 usable packs
- When a crew member attempts to set its quantity to -1
- Then the system rejects the request
- And the available quantity remains 4
- Expected result: HTTP 422; error code `invalid_quantity`
- Side effects: no accepted inventory update is created; quantity remains 4

**AT04-02 — Control: Accept a quantity of zero**

- Given `WTR-001` has 4 usable packs
- When a crew member sets its quantity to 0
- Then the system accepts the request
- Expected result: HTTP 200; quantity = 0
- Side effects: one accepted inventory update

### AC5 — Keep Changes Consistent for Handovers (FR3)

**AT05-01 — Another crew member sees a saved change**

- Given `WTR-001` has 12 packs
- When Crew Member A changes the quantity to 9 and the system saves the update
- And Crew Member B opens the same item
- Then Crew Member B sees a quantity of 9
- And the update history contains the accepted change
- Expected result: HTTP 200; quantity = 9; one corresponding history entry
- Side effects: one accepted inventory update

### AC6 — Enforce Cargo Weight Capacity (FR5)

**AT06-01 — Reject the over-capacity cargo in AC6**

- Given a mission has a weight limit of 500 kg
- And its selected cargo already weighs 490 kg
- And the planner adds 20 packs weighing 1 kg each
- When the planner submits the mission
- Then the system calculates 510 kg
- And rejects the submission
- And the mission remains in Draft
- Expected result: HTTP 422; calculated weight = 510 kg
- Side effects: no submission record is created; mission remains Draft

**AT06-02 — Control: Accept cargo exactly at the weight limit**

- Given a mission has a weight limit of 500 kg
- And its selected cargo already weighs 490 kg
- And the planner adds 10 packs weighing 1 kg each
- When the planner submits the mission
- Then the system calculates 500 kg
- And accepts the submission
- Expected result: HTTP 200; calculated weight = 500 kg; status = Submitted
- Side effects: one submission is recorded

**AT06-03 — Extra: Accept cargo just inside the weight limit**

- Given a mission has a weight limit of 500 kg
- And its selected cargo already weighs 490 kg
- And the planner adds 9 packs weighing 1 kg each
- When the planner submits the mission
- Then the system calculates 499 kg
- And accepts the submission
- Expected result: HTTP 200; calculated weight = 499 kg
- Side effects: one submission is recorded

**AT06-04 — Extra: Reject cargo just outside the weight limit**

- Given a mission has a weight limit of 500 kg
- And its selected cargo already weighs 490 kg
- And the planner adds 11 packs weighing 1 kg each
- When the planner submits the mission
- Then the system calculates 501 kg
- And rejects the submission
- Expected result: HTTP 422; calculated weight = 501 kg
- Side effects: no submission record is created; mission remains Draft

### AC7 — Enforce Cargo Volume Capacity (FR5)

**AT07-01 — Reject cargo that exceeds volume capacity**

- Given a mission has a volume limit of 100 L
- And its selected cargo occupies 100 L
- And the planner adds one item with a unit volume of 1 L
- When the planner submits the mission
- Then the system calculates 101 L
- And rejects the submission
- Expected result: HTTP 422; calculated volume = 101 L
- Side effects: no submission record is created; mission remains Draft

**AT07-02 — Control: Accept cargo exactly at the volume limit**

- Given a mission has a volume limit of 100 L
- And its selected cargo occupies 99 L
- And the planner adds one item with a unit volume of 1 L
- When the planner submits the mission
- Then the system calculates 100 L
- And accepts the submission
- Expected result: HTTP 200; calculated volume = 100 L
- Side effects: one submission is recorded

**AT07-03 — Extra: Accept cargo just inside the volume limit**

- Given a mission has a volume limit of 100 L
- And its selected cargo occupies 98 L
- And the planner adds one item with a unit volume of 1 L
- When the planner submits the mission
- Then the system calculates 99 L
- And accepts the submission
- Expected result: HTTP 200; calculated volume = 99 L
- Side effects: one submission is recorded

### AC8 — Require Cargo Measurements (FR5)

**AT08-01 — Reject submission when unit weight is missing**

- Given a mission has sufficient weight and volume capacity
- And a selected item has a unit volume of 1 L but no unit weight
- And the selected quantity is 2
- When the planner submits the mission
- Then the system identifies the missing unit weight
- And rejects submission
- Expected result: HTTP 422; error code `missing_unit_weight`
- Side effects: no submission record is created; mission remains Draft

**AT08-02 — Control: Accept after unit weight is supplied**

- Given the same mission and item as AT08-01
- And the item is assigned a unit weight of 1 kg
- When the planner submits the mission
- Then the system calculates 2 kg total weight and 2 L total volume
- And accepts submission
- Expected result: HTTP 200; weight = 2 kg; volume = 2 L
- Side effects: one submission is recorded

**AT08-03 — Reject submission when unit volume is missing**

- Given a mission has sufficient weight and volume capacity
- And a selected item has a unit weight of 1 kg but no unit volume
- And the selected quantity is 2
- When the planner submits the mission
- Then the system identifies the missing unit volume
- And rejects submission
- Expected result: HTTP 422; error code `missing_unit_volume`
- Side effects: no submission record is created; mission remains Draft

**AT08-04 — Control: Accept after unit volume is supplied**

- Given the same mission and item as AT08-03
- And the item is assigned a unit volume of 1 L
- When the planner submits the mission
- Then the system calculates 2 kg total weight and 2 L total volume
- And accepts submission
- Expected result: HTTP 200; weight = 2 kg; volume = 2 L
- Side effects: one submission is recorded

### AC9 — Reapprove an Edited Manifest (FR6)

**AT09-01 — Editing an approved manifest returns the mission to Draft**

- Given a mission has an approved manifest and has not been dispatched
- When the Logistics Planner changes a planned item quantity
- Then the system saves the revised manifest
- And returns the mission to Draft
- And requires resubmission and reapproval before dispatch
- Expected result: HTTP 200; status = Draft; revised quantity is saved
- Side effects: manifest version is updated

**AT09-02 — Reject dispatch before resubmission and reapproval**

- Given a mission was returned to Draft after an approved manifest was edited
- When an authorized user attempts to dispatch it without resubmission and reapproval
- Then the system rejects the dispatch operation
- And the mission remains in Draft
- Expected result: HTTP 409; error code `invalid_mission_state`
- Side effects: no dispatch record is created; mission remains Draft

**AT09-03 — Control: Allow dispatch after resubmission and reapproval**

- Given the edited manifest is in Draft
- When the planner resubmits it and an authorized user approves it
- And an authorized user confirms dispatch
- Then the system accepts the operations
- And the mission progresses to Shipped
- Expected result: HTTP 200 for each operation; final status = Shipped
- Side effects: submission, approval, and dispatch are recorded

**AT09-04 — Extra: Editing a submitted manifest before dispatch**

- Given a mission has a submitted manifest but has not been dispatched
- When the Logistics Planner edits the manifest
- Then the mission returns to Draft
- And the edited manifest must be resubmitted and approved
- Expected result: HTTP 200; status = Draft
- Side effects: manifest version is updated

### AC10 — View Inventory Updates from Ground Control (FR7)

**AT10-01 — Display current inventory, recent updates, and synchronization time**

- Given `WTR-001` has a current quantity of 9 packs
- And the latest successful synchronization time is `2026-11-09T10:00:00-06:00`
- And a recent inventory update exists
- When Ground Mission Control opens the inventory view
- Then the system displays current inventory and recent updates
- And shows the synchronization time as `2026-11-09T10:00:00-06:00`
- Expected result: HTTP 200; quantity = 9; timestamp matches the supplied value
- Side effects: none

### AC11 — Identify a Loading Difference (FR8)

**AT11-01 — Record a loading shortage**

- Given a cargo manifest lists 20 water packs
- When Ground Mission Control records that only 18 packs were loaded
- Then the system displays a difference of 2 packs
- And allows the loading problem to be recorded
- Expected result: HTTP 200; planned = 20; loaded = 18; difference = 2
- Side effects: one loading discrepancy is recorded

### AC12 — Receive a Partial Shipment (FR9)

**AT12-01 — Record a partial shipment receipt**

- Given a Shipped mission lists 20 water packs
- And station inventory initially contains 5 usable packs
- And 18 usable packs actually arrive
- When Station Inventory Crew confirms receipt of 18 packs
- Then the system adds 18 packs to inventory
- And the available quantity becomes 23 packs
- And records a shortage of 2 packs
- And changes the mission status to Received
- Expected result: HTTP 200; quantity = 23; shortage = 2; status = Received
- Side effects: one receipt is recorded and 18 usable packs are added to inventory

### AC13 — Save Changes During a Communication Outage (FR10)

**AT13-01 — Preserve an offline update after application restart**

- Given `WTR-001` has 12 usable packs
- And communication with Earth is unavailable
- And the last successful synchronization time is `2026-11-09T10:00:00-06:00`
- When a crew member records 2 packs used and restarts the application
- Then the local quantity remains 10 packs
- And the update remains pending synchronization
- And the pending update count is 1
- And the last successful synchronization time remains unchanged
- Expected result: quantity = 10; pending count = 1; timestamp remains `2026-11-09T10:00:00-06:00`
- Side effects: one local inventory update and one pending synchronization update are stored

### AC14 — Do Not Apply a Duplicated Retry Update (FR11)

**AT14-01 — Do not apply an update twice when it is retried**

- Given Earth has 12 water packs
- And Earth has already accepted update `U101`, which deducts 2 packs
- And the station did not receive acknowledgement
- When the station sends update `U101` again
- Then Earth acknowledges the previously accepted update
- And Earth inventory remains at 10 packs
- Expected result: HTTP 200; quantity = 10; acknowledgement indicates the update was already accepted
- Side effects: no second deduction or duplicate accepted update

**AT14-02 — Control: Accept a different update ID**

- Given Earth has 10 water packs after accepting `U101`
- When the station sends a new valid update `U102` that deducts 1 pack
- Then Earth accepts the new update
- And inventory becomes 9 packs
- Expected result: HTTP 200; quantity = 9
- Side effects: `U102` is accepted once

**AT14-03 — Extra: Generate unique IDs for separate updates**

- Given two separate valid inventory updates are created
- When the system assigns their update IDs
- Then the two update IDs are different
- Expected result: both update IDs are unique
- Side effects: two distinct updates are recorded

### AC15 — Resolve a Synchronization Conflict (FR11, FR12)

**AT15-01 — Retain competing station and Earth values**

- Given an item's original location is `Store A`
- And the station changes its location to `Store B`
- And Earth changes its location to `Store C`
- When the changes synchronize
- Then the system identifies a conflict
- And retains both `Store B` and `Store C` for review
- Expected result: both competing values are available for review
- Side effects: neither value is silently discarded

**AT15-02 — Authorized reviewer resolves a conflict**

- Given the conflict from AT15-01 remains unresolved
- And the reviewer is authorized to resolve synchronization conflicts
- When the reviewer selects `Store B` and enters the reason `Physical inventory confirms Store B`
- Then the current location becomes `Store B`
- And the audit record contains both competing values, selected value, reviewer, time, and reason
- Expected result: HTTP 200; selected location = `Store B`; required audit fields are present
- Side effects: conflict is marked resolved and the resolution is audited

### AC16 — Deny Unauthorized Actions (FR12)

**AT16-01 — Reject an unauthorized mission approval**

- Given a mission is in Submitted status
- And the signed-in user is not authorized to approve missions
- When the user attempts to approve the mission
- Then the system denies the operation
- And the mission remains in Submitted status
- Expected result: HTTP 403; error code `permission_denied`
- Side effects: no approval record is created; status remains Submitted

**AT16-02 — Control: Allow an authorized user to approve the mission**

- Given a mission is in Submitted status
- And the signed-in user is authorized to approve missions
- When the user approves the mission
- Then the system accepts the operation
- And the mission status becomes Approved
- Expected result: HTTP 200; status = Approved
- Side effects: one approval is recorded

**AT16-03 — Extra: Reject an unauthorized inventory change**

- Given a user is authenticated but does not have permission to change inventory
- When the user submits a valid quantity update
- Then the system rejects the operation
- Expected result: HTTP 403
- Side effects: no inventory update is created; quantity remains unchanged
- Control: the same update is accepted when the user is explicitly granted permission

**AT16-04 — Extra: Reject unauthorized dispatch**

- Given a mission is Approved
- And the user is authenticated but does not have permission to confirm dispatch
- When the user attempts to confirm dispatch
- Then the system rejects the operation
- Expected result: HTTP 403
- Side effects: no dispatch record is created; status remains Approved
- Control: the same dispatch operation is accepted when the user is explicitly granted permission

**AT16-05 — Extra: Reject unauthorized cargo receipt**

- Given a mission is Shipped
- And the user is authenticated but does not have permission to record cargo receipt
- When the user submits a valid receipt
- Then the system rejects the operation
- Expected result: HTTP 403
- Side effects: no receipt is created; inventory remains unchanged
- Control: the same receipt operation is accepted when the user is explicitly granted permission

**AT16-06 — Extra: Reject unauthenticated access**

- Given a user has not authenticated
- When the user requests current inventory records
- Then the system denies access
- Expected result: HTTP 401
- Side effects: no protected inventory data is returned
- Control: the same request succeeds with an authenticated user who has permission to view inventory

**AT16-07 — Extra: Reject unauthorized conflict resolution**

- Given a synchronization conflict exists
- And the user is authenticated but is not authorized to resolve conflicts
- When the user attempts to select a final value and provide a reason
- Then the system rejects the operation
- Expected result: HTTP 403
- Side effects: no resolution is created; both conflicting values remain available
- Control: AT15-02 is the authorized version of the same operation

### AC17 — Audit an Accepted Change (FR12)

**AT17-01 — Record the user, time, and changed values**

- Given `WTR-001` has 4 packs
- And user `crew-01` is authenticated and authorized to update inventory
- And the test clock is set to `2026-11-09T10:30:00-06:00`
- When `crew-01` changes the quantity from 4 to 6
- Then the system records the accepted change
- And the audit record contains user `crew-01`, the timestamp, affected item, previous quantity 4, and new quantity 6
- Expected result: HTTP 200; audit fields match the supplied values
- Side effects: one accepted inventory update and one corresponding audit record

---

## 3. Additional Tests for Nonfunctional Requirements

### NFR1 and NFR2 — Offline Availability and Local Data Durability

**AT-X01 — Extra: View and update inventory offline, then preserve the update**

- Given the station has a locally stored record for `WTR-001` with 12 usable packs
- And communication with Earth is unavailable
- When a crew member searches for `WTR-001` and records 2 packs used
- Then the local quantity becomes 10
- And the system displays the updated local record
- And the update is pending synchronization
- When the application restarts
- Then the quantity remains 10 and the update remains pending
- Expected result: HTTP 200 for local operations; quantity = 10; pending count = 1
- Side effects: the local update survives restart

### NFR3 — Synchronization Recovery

**AT-X02 — Extra: Start synchronization within 60 seconds**

- Given pending updates exist
- And communication is restored at `10:00:00`
- When the system detects the restored connection
- Then it starts attempting synchronization no later than `10:01:00`
- Expected result: synchronization starts within 60 seconds
- Control/boundary: starting at `10:01:01` fails the requirement

**AT-X03 — Extra: Keep failed synchronization updates pending**

- Given a pending update is sent to Earth
- And the synchronization attempt fails
- When the system checks the pending update list
- Then the failed update remains stored and pending
- Expected result: the update remains pending
- Side effects: the failed update is not deleted

### NFR4 — Security

**AT-X04 — Extra: Verify encryption at rest and in transit**

- Given station and Earth inventory records are stored and transferred
- When the storage and communication mechanisms are examined
- Then stored records are encrypted
- And data transmitted between the station and Earth is encrypted
- Expected result: protected records and communication payloads are not stored or transmitted as readable plaintext

*The exact verification method depends on the storage and communication technologies selected during implementation.*

### NFR5 — Search Performance

**AT-X05 — Extra: Meet the inventory search performance requirement**

- Given the system contains 10,000 inventory records
- When 100 inventory searches are performed on the team's agreed test device
- Then at least 95 searches return results within 2 seconds
- Expected result: performance requirement passes
- Boundary/control: 95 searches within 2 seconds passes; only 94 within 2 seconds fails

### NFR6 — Usability

**AT-X06 — Extra: Display clear item names, units, and warnings**

- Given an item has a quantity and unit and is below its minimum stock level
- When the item is displayed to a crew member
- Then the item name and unit are clear
- And the low-stock warning is communicated with text or another non-color-only indicator
- Expected result: the warning and item information are understandable without relying on color alone
- Side effects: none

*This requires a user-interface test and cannot be verified by a REST API test alone.*

### FR9 — Shipment Tracking

**AT-X07 — Extra: Return shipment status, expected arrival, and history**

- Given a resupply mission has a recorded status, expected arrival time, and status history
- When Ground Mission Control requests the shipment details
- Then the system returns the current status, expected arrival, and status history
- Expected result: HTTP 200; returned fields match the stored mission data
- Side effects: none

---

## 4. Gap Checklist

- **Boundaries:** Covered for three interactions, minimum stock, available quantity, zero and negative quantities, cargo weight and volume, and synchronization timing.
- **Time:** Update timestamps, last successful sync time, and the 60-second synchronization requirement are covered. Clock synchronization and timezone handling remain unspecified.
- **Identity:** Authentication and permission checks are covered. The role-to-permission mapping remains unspecified.
- **State:** Tests cover Draft, Submitted, Approved, Shipped, and Received where the specification defines behavior. Other transitions remain unclear.
- **Concurrency:** Simultaneous updates to the same item have no defined expected behavior.
- **Input types:** Fractional quantities, text, and null values have no defined expected behavior.
- **Errors and precedence:** Individual rejection conditions are tested separately. The specification does not define which error takes precedence when multiple rules are violated at once.
- **Listing:** Low-stock items and update history are covered. Sorting, filtering, and pagination are not specified.
- **Returned data:** Tests check item details, quantities, location, condition, history, synchronization status, capacity totals, mission status, receipt information, conflict values, and audit details. Exact response structures are defined in `contracts.md`.

---

## 5. Spec Gaps

### Functional requirements without acceptance criteria

None. Every functional requirement maps to at least one acceptance criterion.

| Functional requirement | Acceptance criteria |
|---|---|
| FR1 | AC1 |
| FR2 | AC2, AC3, AC4 |
| FR3 | AC5 |
| FR4 | AC2 |
| FR5 | AC6, AC7, AC8 |
| FR6 | AC9 |
| FR7 | AC10 |
| FR8 | AC11 |
| FR9 | AC12 |
| FR10 | AC13 |
| FR11 | AC14, AC15 |
| FR12 | AC15, AC16, AC17 |

### Acceptance criteria without functional requirements

None. AC1 through AC17 each map to at least one functional requirement.

### Nonfunctional requirements without separate numbered acceptance criteria

NFR1 through NFR6 do not have separate numbered Gherkin acceptance criteria in `spec.md`. They are covered by AT-X01 through AT-X06 in this test plan.

### Other unresolved specification issues

1. **Role permissions (FR12):** The specification does not define which named roles can approve missions, confirm dispatch, receive cargo, or resolve conflicts. Tests use explicit permission settings rather than inventing a role-permission matrix.

2. **Earth-side interface (FR7, FR11):** The API, message format, acknowledgement format, and authentication mechanism between the station and Earth are not defined.

3. **Conflict identification (FR11):** The specification requires conflicting values to be retained, but does not define the version or comparison rules used to identify a conflict.

4. **Concurrent updates (FR2, FR3, FR11):** The expected behavior when two crew members update the same inventory item at nearly the same time is not defined.

5. **Quantity input types (FR2):** The specification does not state whether quantities may be fractional or must be whole numbers, or how text and null values should be handled.

6. **Mission status transitions (FR6, FR9):** The mission statuses are listed, but not every permitted transition or cancellation condition is defined.

7. **Duplicate shipment receipts (FR9, AC12):** AC12 says the received quantity is added once, but the specification does not define how repeated receipt submissions are identified or handled.

8. **Damaged cargo (FR9):** The system must record damage, but it is not specified whether damaged quantities are included in inventory quantity, excluded from usable stock, or stored separately.

9. **Audit details (FR12):** The requirement mentions the user, time, reviewer, changed value, and reason, but does not clarify whether an ordinary inventory change requires a reason or whether a reason is required only for conflict resolution.

10. **Encryption details (NFR4):** Encryption at rest and in transit is required, but the technology, key management, and verification method are not defined.

11. **Clock handling (FR2, FR12, NFR3):** The specification does not define how station and Earth timestamps are synchronized or how clock differences are handled.

12. **Inventory item creation (Domain Rules):** The domain model requires unique item IDs, but no functional requirement defines creation of inventory items.

13. **Performance environment (NFR5):** The team must agree on the test device and test conditions before the 10,000-record performance test can be reproduced.

14. **User-interface interaction count (FR1):** FR1 requires finding an item within three interactions, but the specification does not precisely define what counts as one interaction. A backend API test cannot verify this by itself.
