# Test Plan — Commercial Space Station Inventory and Resupply System

## 1. Overview

This document refines the acceptance criteria in `spec.md` into concrete test cases. It uses the BDD alternative from the assignment.

Each test has a unique ID. Tests are grouped by their original acceptance criterion or by the additional requirement they cover.

### Test conventions

- `WTR-001` represents a water inventory item measured in packs.
- Unless stated otherwise, `WTR-001` starts with 12 usable packs, a minimum stock level of 10, location `Store A`, and condition `Usable`.
- Test users are authenticated users whose permissions are explicitly configured for each test. This avoids assuming an undefined role-permission mapping.
- A fixed test clock is used for timestamp checks.
- Each test starts with an independent initial state unless otherwise stated.
- For rejected requests, no accepted business update, submission, approval, dispatch, or resolution record should be created, and the relevant business state must remain unchanged.

### Proposed HTTP status codes

The requirements do not specify HTTP status codes. These are proposed for the FastAPI implementation and should be kept consistent in `contracts.md`.

| Result | Proposed status |
|---|---:|
| Successful operation | 200 |
| Unauthenticated request | 401 |
| Authenticated but unauthorized request | 403 |
| Operation not allowed in the current state | 409 |
| Invalid input or capacity violation | 422 |

**Important:** During this milestone, the skeleton routes will return HTTP 501 because they are not implemented. The tests below describe the expected behavior of the eventual implementation, not the temporary 501 skeleton response.

---

## 2. Acceptance Criteria Tests

### AC1 — Find an Item (FR1)

**AT01-01 — Find an item within three interactions**

- Given `WTR-001` has 12 packs, location `Store A`, and condition `Usable`
- When a crew member finds the item from the dashboard within three interactions
- Then the system displays its ID, name, quantity, unit, location, and condition
- Expected result: HTTP 200; returned quantity is 12, location is `Store A`, and condition is `Usable`
- Side effects: none

**AT01-02 — Extra: Check the interaction limit outside the requirement**

- Given `WTR-001` exists in the inventory
- When a crew member needs four interactions from the dashboard to find it
- Then the interface fails the three-interaction requirement
- Expected result: usability requirement failure
- Side effects: none

*This is a user-interface test. An API test can check the returned item data but cannot verify the number of user interactions.*

### AC2 — Record Usage and Flag Low Stock (FR2, FR4)

**AT02-01 — Record valid usage and trigger a low-stock warning**

- Given `WTR-001` has 12 usable packs and a minimum stock level of 10
- When a crew member records 3 packs used
- Then the remaining quantity is 9 packs
- And the system displays a low-stock warning
- And the accepted update records the user's identity and time
- Expected result: HTTP 200; quantity = 9; low-stock warning = true
- Side effects: one accepted inventory update and corresponding history entry

**AT02-02 — Extra: Quantity reaches the minimum stock level**

- Given `WTR-001` has 12 usable packs and a minimum stock level of 10
- When a crew member records 2 packs used
- Then the remaining quantity is 10 packs
- And the item is not identified as below minimum stock
- Expected result: HTTP 200; quantity = 10; low-stock warning = false
- Side effects: one accepted inventory update

**AT02-03 — Extra: List low-stock items and their importance**

- Given `WTR-001` has 9 usable packs, a minimum stock level of 10, and importance `Critical`
- And another item has 12 usable packs and a minimum stock level of 10
- When a Logistics Planner requests the resupply needs
- Then `WTR-001` appears as requiring replenishment
- And its importance is displayed as `Critical`
- And the other item is not identified as low-stock
- Expected result: HTTP 200; returned low-stock item and importance match the starting data
- Side effects: none

### AC3 — Reject Usage Above Available Quantity (FR2)

**AT03-01 — Reject usage above available quantity**

- Given `WTR-001` has 4 usable packs
- When a crew member records 5 packs used
- Then the system rejects the request with a quantity validation error
- And the available quantity remains 4 packs
- Expected result: HTTP 422
- Side effects: no accepted inventory update is created; quantity remains 4

**AT03-02 — Control: Accept usage equal to available quantity**

- Given `WTR-001` has 4 usable packs
- When a crew member records 4 packs used
- Then the system accepts the request
- And the remaining quantity becomes 0
- Expected result: HTTP 200; quantity = 0
- Side effects: one accepted inventory update

**AT03-03 — Extra: Accept usage just below available quantity**

- Given `WTR-001` has 4 usable packs
- When a crew member records 3 packs used
- Then the system accepts the request
- And the remaining quantity becomes 1
- Expected result: HTTP 200; quantity = 1
- Side effects: one accepted inventory update

### AC4 — Reject a Negative Quantity (FR2)

**AT04-01 — Reject a negative inventory quantity**

- Given `WTR-001` has 4 usable packs
- When a crew member attempts to set its quantity to -1
- Then the system rejects the request
- And the available quantity remains 4
- Expected result: HTTP 422
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

**AT05-02 — Extra: Apply the same validation to different crew members**

- Given `WTR-001` has 4 usable packs
- When Crew Member A attempts to record 5 packs used
- And Crew Member B makes the same request using the same starting state
- Then both requests are rejected by the same quantity validation rule
- Expected result: HTTP 422 for both requests
- Side effects: neither request creates an accepted update or changes the quantity

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
- Side effects: no submission or approval record is created; mission remains Draft

**AT06-02 — Control: Accept cargo exactly at the weight limit**

- Given a mission has a weight limit of 500 kg
- And its selected cargo already weighs 490 kg
- And the planner adds 10 packs weighing 1 kg each
- When the planner submits the mission
- Then the system calculates 500 kg
- And accepts the submission
- Expected result: HTTP 200; calculated weight = 500 kg; mission status = Submitted
- Side effects: one submission is recorded

**AT06-03 — Accept cargo just inside the weight limit**

- Given a mission has a weight limit of 500 kg
- And its selected cargo already weighs 490 kg
- And the planner adds 9 packs weighing 1 kg each
- When the planner submits the mission
- Then the system calculates 499 kg
- And accepts the submission
- Expected result: HTTP 200; calculated weight = 499 kg
- Side effects: one submission is recorded

**AT06-04 — Extra: Check the closest value outside the weight limit**

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

**AT07-03 — Accept cargo just inside the volume limit**

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
- Expected result: HTTP 422; error identifies missing unit weight
- Side effects: no submission record is created; mission remains Draft

**AT08-02 — Control: Accept after unit weight is supplied**

- Given the same mission and item as AT08-01
- And the item is assigned a unit weight of 1 kg
- When the planner submits the mission
- Then the system calculates 2 kg total weight and 2 L total volume
- And accepts submission
- Expected result: HTTP 200; calculated weight = 2 kg; volume = 2 L
- Side effects: one submission is recorded

**AT08-03 — Reject submission when unit volume is missing**

- Given a mission has sufficient weight and volume capacity
- And a selected item has a unit weight of 1 kg but no unit volume
- And the selected quantity is 2
- When the planner submits the mission
- Then the system identifies the missing unit volume
- And rejects submission
- Expected result: HTTP 422; error identifies missing unit volume
- Side effects: no submission record is created; mission remains Draft

**AT08-04 — Control: Accept after unit volume is supplied**

- Given the same mission and item as AT08-03
- And the item is assigned a unit volume of 1 L
- When the planner submits the mission
- Then the system calculates 2 kg total weight and 2 L total volume
- And accepts submission
- Expected result: HTTP 200; calculated weight = 2 kg; volume = 2 L
- Side effects: one submission is recorded

### AC9 — Reapprove an Edited Manifest (FR6)

**AT09-01 — Editing an approved manifest returns the mission to Draft**

- Given a mission has an approved manifest and has not been dispatched
- When the Logistics Planner changes a planned item quantity
- Then the system saves the revised manifest
- And returns the mission to Draft
- And requires the revised manifest to be resubmitted and approved before dispatch
- Expected result: HTTP 200; mission status = Draft; revised quantity is saved
- Side effects: manifest version is updated

**AT09-02 — Reject dispatch before resubmission and reapproval**

- Given a mission was returned to Draft after an approved manifest was edited
- When an authorized user attempts to dispatch it without resubmission and reapproval
- Then the system rejects the dispatch operation
- And the mission remains in Draft
- Expected result: HTTP 409
- Side effects: no dispatch record is created; mission status remains Draft

**AT09-03 — Control: Allow dispatch after resubmission and reapproval**

- Given the edited manifest is in Draft
- When the planner resubmits it and an authorized user approves it
- And an authorized user confirms dispatch
- Then the system accepts the operations
- And the mission progresses to Shipped
- Expected result: HTTP 200 for each accepted operation; final status = Shipped
- Side effects: submission, approval, and dispatch are recorded

**AT09-04 — Extra: Editing a submitted manifest before dispatch**

- Given a mission has a submitted manifest but has not been dispatched
- When the Logistics Planner edits the manifest
- Then the mission returns to Draft
- And the edited manifest must be resubmitted and approved
- Expected result: HTTP 200; mission status = Draft
- Side effects: manifest version is updated

### AC10 — View Inventory Updates from Ground Control (FR7)

**AT10-01 — Display current inventory, recent updates, and synchronization time**

- Given `WTR-001` has a current quantity of 9 packs
- And the latest successful synchronization time is `2026-11-09T10:00:00-06:00`
- And a recent inventory update exists
- When Ground Mission Control opens the inventory view
- Then the system displays the current inventory and recent updates
- And shows the synchronization time as `2026-11-09T10:00:00-06:00`
- Expected result: HTTP 200; returned quantity = 9; timestamp matches the supplied value
- Side effects: none

### AC11 — Identify a Loading Difference (FR8)

**AT11-01 — Record a loading shortage**

- Given a cargo manifest lists 20 water packs
- When Ground Mission Control records that only 18 packs were loaded
- Then the system displays a difference of 2 packs
- And allows the loading problem to be recorded
- Expected result: HTTP 200; planned = 20; loaded = 18; difference = 2
- Side effects: one loading discrepancy record is associated with the mission

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
- Expected result: HTTP 200; inventory quantity = 23; shortage = 2; status = Received
- Side effects: one receipt is recorded and 18 packs are added to inventory

**AT12-02 — Extra: Record a full shipment receipt**

- Given a Shipped mission lists 20 water packs
- And station inventory initially contains 5 usable packs
- When Station Inventory Crew confirms receipt of all 20 packs
- Then the system adds 20 packs to inventory
- And the available quantity becomes 25 packs
- And records no shortage
- And changes the mission status to Received
- Expected result: HTTP 200; inventory quantity = 25; shortage = 0; status = Received
- Side effects: one receipt is recorded

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
- Expected result: local quantity = 10; pending count = 1; timestamp remains `2026-11-09T10:00:00-06:00`
- Side effects: one local inventory update and one pending synchronization update are stored

### AC14 — Do Not Apply a Duplicated Retry Update (FR11)

**AT14-01 — Do not apply an update twice when it is retried**

- Given Earth has 12 water packs
- And Earth has already accepted update `U101`, which deducts 2 packs
- And the station did not receive acknowledgement
- When the station sends update `U101` again
- Then Earth acknowledges the previously accepted update
- And Earth inventory remains at 10 packs
- Expected result: HTTP 200; acknowledgement indicates the update was already accepted; quantity = 10
- Side effects: no second inventory deduction or duplicate accepted update

**AT14-02 — Control: Accept a different update ID**

- Given Earth has 10 water packs after accepting `U101`
- When the station sends a new valid update `U102` that deducts 1 pack
- Then Earth accepts the new update
- And inventory becomes 9 packs
- Expected result: HTTP 200; quantity = 9
- Side effects: `U102` is accepted once

### AC15 — Resolve a Synchronization Conflict (FR11, FR12)

**AT15-01 — Retain competing station and Earth values**

- Given an item's original location is `Store A`
- And the station changes its location to `Store B`
- And Earth changes its location to `Store C`
- When the changes synchronize
- Then the system identifies a conflict
- And retains both `Store B` and `Store C` for review
- Expected result: conflict is identified; both values are available
- Side effects: neither competing value is silently discarded

**AT15-02 — Authorized reviewer resolves a conflict**

- Given the conflict from AT15-01 remains unresolved
- And the reviewer is authorized to resolve synchronization conflicts
- When the reviewer selects `Store B` and enters the reason `Physical inventory confirms Store B`
- Then the current location becomes `Store B`
- And the audit record contains both competing values, selected value, reviewer, time, and reason
- Expected result: HTTP 200; selected location = `Store B`; audit fields are present
- Side effects: conflict is marked resolved and the resolution is audited

**AT15-03 — Extra: Reject unauthorized conflict resolution**

- Given a synchronization conflict exists
- And the signed-in user is not authorized to resolve conflicts
- When the user attempts to select `Store B` and enter a resolution reason
- Then the system rejects the operation
- And both conflicting values remain available for review
- Expected result: HTTP 403
- Side effects: no conflict resolution is created; neither value is discarded
- Control: AT15-02 is the authorized version of the same operation

### AC16 — Deny Unauthorized Actions (FR12)

**AT16-01 — Reject an unauthorized mission approval**

- Given a mission is in Submitted status
- And the signed-in user is not authorized to approve missions
- When the user attempts to approve the mission
- Then the system denies the operation
- And the mission remains in Submitted status
- Expected result: HTTP 403
- Side effects: no approval record is created; mission status remains Submitted

**AT16-02 — Control: Allow an authorized user to approve the mission**

- Given a mission is in Submitted status
- And the signed-in user is authorized to approve missions
- When the user approves the mission
- Then the system accepts the operation
- And the mission status becomes Approved
- Expected result: HTTP 200; status = Approved
- Side effects: one approval is recorded

### AC17 — Audit an Accepted Change (FR12)

**AT17-01 — Record the user, time, and changed values**

- Given `WTR-001` has 4 packs
- And user `crew-01` is authenticated and authorized to update inventory
- And the test clock is set to `2026-11-09T10:30:00-06:00`
- When `crew-01` changes the quantity from 4 to 6
- Then the system records the accepted change
- And the audit record contains user `crew-01`, the timestamp, the affected item, previous quantity 4, and new quantity 6
- Expected result: HTTP 200; audit fields match the supplied values
- Side effects: one accepted inventory update and one corresponding audit record

---

## 3. Additional Tests for Nonfunctional Requirements

These tests are marked extra because they extend the acceptance scenarios using the NFRs in `spec.md`.

### NFR1 — Offline Availability

**AT-X01 — Extra: View inventory while offline**

- Given the station has a locally stored record for `WTR-001`
- And communication with Earth is unavailable
- When a crew member searches for `WTR-001`
- Then the system returns the locally stored inventory information
- Expected result: HTTP 200; item data matches local storage
- Side effects: none

### NFR2 — Local Data Durability

**AT-X02 — Extra: Keep pending updates until acknowledgement**

- Given an inventory update is saved locally and is pending synchronization
- When the application restarts and a synchronization attempt fails
- Then the update remains stored locally and pending
- And when Earth later acknowledges the update, it is marked as synchronized
- Expected result: update remains pending until acknowledgement
- Side effects: failed synchronization does not delete the pending update

### NFR3 — Synchronization Recovery

**AT-X03 — Extra: Start synchronization within 60 seconds**

- Given pending inventory updates exist
- And communication is restored at `10:00:00`
- When the system detects the restored connection
- Then it starts a synchronization attempt no later than `10:01:00`
- Expected result: synchronization starts within 60 seconds

**AT-X04 — Extra: Check the timing limit outside the requirement**

- Given pending inventory updates exist
- And communication is restored at `10:00:00`
- When the system does not start synchronization until `10:01:01`
- Then it fails the NFR3 timing requirement
- Expected result: synchronization timing requirement failure

**AT-X05 — Extra: Keep failed synchronization updates pending**

- Given a pending update is sent to Earth
- And the synchronization attempt fails
- When the system checks the pending update list
- Then the failed update remains stored and pending
- Expected result: update remains pending
- Side effects: no pending update is deleted

### NFR4 — Security

**AT-X06 — Extra: Reject unauthenticated access**

- Given a user has not authenticated
- When the user requests current inventory records
- Then the system denies access
- Expected result: HTTP 401
- Side effects: no protected inventory data is returned

**AT-X07 — Extra: Control for authenticated access**

- Given a user has authenticated and has permission to view inventory
- When the user requests current inventory records
- Then the system returns the permitted inventory information
- Expected result: HTTP 200
- Side effects: none

**AT-X08 — Extra: Verify encryption at rest and in transit**

- Given station and Earth inventory records are stored and transferred
- When the storage and communication mechanisms are examined
- Then stored records are encrypted
- And data transmitted between the station and Earth is encrypted
- Expected result: protected records and communication payloads are not stored or transmitted as readable plaintext

*The exact verification method depends on the storage and communication technologies selected for implementation.*

### NFR5 — Search Performance

**AT-X09 — Extra: Meet the inventory search performance requirement**

- Given the system contains 10,000 inventory records
- When 100 inventory searches are performed on the team's agreed test device
- Then at least 95 searches return results within 2 seconds
- Expected result: performance requirement passes

**AT-X10 — Extra: Check performance below the required success rate**

- Given the system contains 10,000 inventory records
- When 100 inventory searches are performed and only 94 return results within 2 seconds
- Then the system fails the NFR5 performance requirement
- Expected result: performance requirement fails

### NFR6 — Usability

**AT-X11 — Extra: Display clear item names, units, and warnings**

- Given an item has a quantity and unit and is below its minimum stock level
- When the item is displayed to a crew member
- Then the item name and unit are clear
- And the low-stock warning is communicated with text or another non-color-only indicator
- Expected result: warning and item information are understandable without relying on color alone
- Side effects: none

*This test requires the user interface. It cannot be verified by a REST API test alone.*

---

## 4. Additional Functional and Gap Tests

**AT-X12 — Extra: Assign unique IDs to separate inventory updates (FR11, Domain Rules)**

- Given two separate valid inventory updates are created
- When the system assigns update IDs
- Then the two IDs are different
- Expected result: both update IDs are unique
- Side effects: two distinct updates are recorded

**AT-X13 — Extra: Return shipment status, expected arrival, and history (FR9)**

- Given a resupply mission has a recorded status, expected arrival time, and status history
- When Ground Mission Control requests the shipment details
- Then the system returns the current status, expected arrival, and status history
- Expected result: HTTP 200; returned fields match the stored mission data
- Side effects: none

**AT-X14 — Extra: Probe concurrent inventory updates (FR2, FR3, FR11)**

- Given two crew members read the same starting quantity for an inventory item
- When both submit quantity updates before either sees the other's update
- Then the test checks how the system handles the competing updates
- Expected result: not defined by the current specification
- Status: unresolved specification gap; do not automate as a pass/fail test until the expected concurrency behavior is defined

**AT-X15 — Extra: Probe unsupported quantity input types (FR2)**

- Given an inventory item has 4 packs
- When a crew member submits a fractional quantity or a non-numeric quantity
- Then the system's expected handling must be clarified
- Expected result: not defined by the current specification
- Status: unresolved specification gap; do not automate until the accepted quantity types are defined

---

## 5. Gap Checklist

| Category | Coverage or unresolved issue |
|---|---|
| Boundaries | Tests cover the three-interaction limit, minimum stock threshold, available quantity, zero and negative quantities, weight and volume limits, and 60-second synchronization limit. |
| Time | Tests cover update timestamps, last successful synchronization time, and synchronization recovery timing. Clock synchronization and timezone handling remain unspecified. |
| Identity | Tests cover authenticated access and authorized/unauthorized operations. The role-to-permission mapping remains unspecified. |
| State | Tests cover Draft, Submitted, Approved, Shipped, and Received where the specification defines behavior. Other transitions remain unclear. |
| Concurrency | AT-X14 identifies the missing rule for simultaneous updates to the same inventory item. |
| Input types | AT-X15 identifies missing rules for fractional, text, and other invalid quantity inputs. |
| Errors and precedence | Tests isolate quantity, measurement, capacity, mission-state, and permission failures. The specification does not define which error takes precedence when one request violates multiple rules; no combined-invalid-input behavior is assumed. |
| Listing | AT02-03 checks that low-stock results include the appropriate items and importance. Sorting, filtering, and pagination are not specified. |
| Returned data | Tests check item details, quantities, location, condition, update history, synchronization time, capacity totals, mission status, shipment receipt, conflict values, and audit details. Exact JSON response structures will be defined in `contracts.md`. |

---

## 6. Spec Gaps

### Functional requirements without acceptance criteria

None. Every functional requirement has at least one mapped acceptance criterion.

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

### Nonfunctional requirements without numbered acceptance criteria in spec.md

NFR1 through NFR6 do not currently have separate numbered Gherkin acceptance criteria in `spec.md`. They are covered by the additional test cases in Sections 3 and 4 of this test plan.

### Other unresolved specification issues

1. **Role permissions (FR12):** The specification does not define which named roles can approve missions, confirm dispatch, receive cargo, or resolve synchronization conflicts. Tests use explicit permission settings rather than inventing a role-permission matrix.

2. **Earth-side interface (FR7, FR11):** The API, message format, acknowledgement format, and authentication mechanism between the station and Earth are not defined.

3. **Conflict identification (FR11):** The specification requires conflicting values to be retained, but does not define the version or comparison rules used to identify a conflict.

4. **Concurrent updates (FR2, FR3, FR11):** The expected behavior when two crew members update the same inventory item at nearly the same time is not defined.

5. **Quantity input types (FR2):** The specification does not state whether quantities may be fractional or must be whole numbers, or how text and null values should be handled.

6. **Mission status transitions (FR6, FR9):** The mission statuses are listed, but not every permitted transition or cancellation condition is defined.

7. **Duplicate shipment receipts (FR9, AC12):** AC12 says the received quantity is added once, but the specification does not define how repeated receipt submissions are detected or handled.

8. **Damaged cargo (FR9):** The system must record damage, but it is not specified whether damaged quantities are included in inventory quantity, excluded from usable stock, or stored separately.

9. **Audit details (FR12):** The requirement mentions user, time, reviewer, changed value, and reason, but does not clarify whether an ordinary inventory change requires a reason or whether reasons are only required for conflict resolution.

10. **Encryption details (NFR4):** Encryption at rest and in transit is required, but the technology, key management, and verification method are not defined.

11. **Clock handling (FR2, FR12, NFR3):** The specification does not define how station and Earth timestamps are synchronized or how clock differences are handled.

12. **Inventory item creation (Domain Rules):** The domain model requires unique item IDs, but no functional requirement defines creation of inventory items.

13. **Performance environment (NFR5):** The team must agree on the test device and test conditions before the 10,000-record performance test can be reproduced.

14. **User-interface interaction count (FR1):** FR1 requires finding an item within three interactions, but the specification does not define precisely what counts as one interaction. A backend API test cannot verify this by itself.
