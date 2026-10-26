# Space Station Inventory and Resupply – Simplified Spec

Oct 26, 2026 · @AyRidd03

# Description

The Space Station Inventory and Resupply system keeps one crewed station's inventory accurate while the Earth link is intermittent, and lets Earth teams plan, approve and track resupply missions to it. Station crew record usage, moves, condition changes and stock corrections in an onboard store shared by all station devices. Every change is queued and synchronized with the Earth service when the link is up; conflicting changes are flagged for ground mission control instead of being overwritten. Supply alerts are raised automatically when an item falls below its minimum. Logistics planners build missions that cover those shortages within mass and volume limits, and ground mission control approves, dispatches and tracks them until the crew records receipt. The system covers one station with one inventory record per supply type at one location; consumption forecasting, per-batch tracking, splitting items across locations and notifications outside the app are out of scope. All times are UTC, shown as `HH:MM UTC` for today and `YYYY-MM-DD HH:MM UTC` otherwise. The screens are S1 Dashboard, S2 Inventory, S3 Item details, S4 Resupply plan, S5 Cargo manifest, S6 Mission status and S7 Sync, and every screen has global navigation to S1, S2, S4, S6 and S7.

# Goals

1. Keep station inventory accurate and trustworthy at all times, including while the Earth link is down.
2. Make every supply shortage visible to crew and planners the moment it occurs.
3. Plan resupply missions that cover open shortages within the vehicle's mass and volume limits.
4. Make every mission and inventory change traceable, attributable to a person, and performed only by an authorized role.
5. Synchronize station and Earth records without losing an update, applying one twice, or silently overwriting a conflicting change.

# Domain Model

## Actors

- **User** – Any authenticated person. Has a `userId`, a `name` and exactly one `role`. Every role can view every screen; the client hides controls the role cannot use and the Earth service rejects them anyway.
- **Station Inventory Crew** (`StationCrew`) – Astronauts aboard the station, often working offline. They record usage, moves, condition changes and stock corrections, record receipt of shipped missions, and report unlisted delivered items.
- **Logistics Planner** (`LogisticsPlanner`) – Earth-based staff. They manage item data and storage locations, create and edit missions and manifests, submit missions for approval, and record loading review.
- **Ground Mission Control** (`GroundMissionControl`) – Earth-based authority. They approve, return, cancel and dispatch missions, and reopen approved missions only if their `canReopen` flag is set. They also correct stock from Earth and resolve discrepancies and sync conflicts.
- **Station App** (system) – The onboard application and its store, shared by all station devices. It validates and saves every change locally, works offline, and queues updates for sync.
- **Earth Service** (system) – The ground-side service. It receives updates, deduplicates them, checks versions, merges or flags conflicts, acknowledges them, and sends Earth-side changes back to the station. It enforces every permission and validation rule.

## Objects

Fields marked *server-set* are never accepted from a client.

- **Unit** – `name` (pack, kg, L…), `countable`. Countable units take whole numbers only; other units allow up to 3 decimals.
- **StorageLocation** – `locationId`, `name`. A fixed list maintained by planners (for example Store A, Store B, Store C).
- **InventoryItem** – `itemId`, `name`, `barcodes[]`, `quantity`, `unit`, `condition`, `expiryDate?`, `unitMassKg`, `unitVolumeM3`, `minimumQuantity`, `criticality`, `recordVersion` *(server-set)*.
  - One record per supply type, `storedAt` exactly one StorageLocation; `quantity` ≥ 0.
  - `condition` is Usable or Damaged and applies to the whole record; `criticality` is Critical or Standard.
  - `expiryDate` is the earliest expiry on board; barcodes are unique across items.
- **InventoryUpdate** – `updateId` (a UUID made on the device), `displayId` (U101…), `type`, `field`, `oldValue`, `newValue`, `quantityDelta`, `reason?`, `eventTime`, `baseVersion`, `syncStatus`, `recordedBy` *(server-set)*, `receivedAt` *(server-set)*.
  - Each update `affectsItem` one InventoryItem.
  - `type` is Usage, Move, Condition, Correction, Receipt or Resolution.
  - `syncStatus` is Awaiting sync, Synchronized, Conflict or Rejected.
- **SupplyAlert** – `alertId`, `alertStatus` (Active or Resolved), `raisedAt`, `resolvedAt?`. Each alert is `aboutItem` one InventoryItem, and an item has at most one Active alert.
- **ResupplyMission** – `missionId` *(server-set: R1, R2…)*, `missionStatus`, `massCapacityKg`, `volumeCapacityM3`, `expectedArrival?`, `dispatchedAt?`, `statusHistory[]`.
  - Capacities are > 0.
  - Each history entry holds status, time, user and reason.
  - Each mission `hasManifest` one CargoManifest.
- **CargoManifest** – `manifestVersion`, starting at 1 when the mission is created. It `hasLine` zero or more ManifestLines. Earlier versions are kept read-only.
- **ManifestLine** – `lineQuantity` (> 0), `loadedQuantity?`, `receivedQuantity?`. Each line is `forItem` one InventoryItem; a manifest has at most one line per item.
- **LoadingIssue** – `text`, `recordedBy`, `time`. Belongs to one mission.
- **Discrepancy** – `discrepancyId`, `description`, `expected`, `received`, `status` (Open or Resolved), `resolutionNote?`. Belongs to one mission, and to one item unless it reports an unlisted item.

**Mission lifecycle (state machine).** The Earth service rejects every transition not listed here.

- Draft →(submit \[≥ 1 line; total mass and volume each ≤ capacity\])→ Submitted
- Submitted →(approve \[capacity re-checked\])→ Approved
- Submitted →(return \[reason\])→ Draft
- Approved →(reopen \[`canReopen`; reason; loading data cleared\])→ Draft
- Approved →(confirm dispatch \[every line has a loaded quantity; expected arrival set\])→ Shipped
- Shipped →(record receipt \[received quantity for every line\])→ Received
- Draft, Submitted or Approved →(cancel \[reason\])→ Cancelled

Cancelled and Received are final. Shipped missions cannot be cancelled.

# Functional Requirements

The goals each requirement supports are in brackets.

### Dashboard and status

- **FR-001:** As a user, I want a dashboard showing active supply alerts, the next resupply mission, the number of pending updates and recent activity, so that I can understand the station's supply situation at a glance. \[Goals 2, 4, 5\]
  - Alerts: Critical items first, shown as "\<item> below minimum (\<qty> / \<min> \<unit>)".
  - Next mission: the Submitted, Approved or Shipped mission with the earliest expected arrival, or the most recently changed if none has one.
  - Pending updates: Awaiting sync plus Conflict; on Earth, the count the station last reported.
  - Recent activity: the last 10 events from the past 7 days.
- **FR-002:** As a user, I want every screen to show whether the link is available and when the last synchronization fully completed, so that I know how current my data is. \[Goals 1, 5\]
  - On the station the banner says "Earth link"; on Earth it says "Station link".
- **FR-003:** As a user, I want to see only the controls my role permits, and have the Earth service reject any action my role is not allowed, so that each action is performed only by authorized people. \[Goal 4\]

### Inventory

- **FR-004:** As a station inventory crew member, I want to search items by name, ID or barcode, and filter them by All, Low stock, Damaged or Expired, so that I can find items that need attention. \[Goals 1, 2\]
  - Name and ID search is a case-insensitive substring match; barcodes must match exactly.
  - Low stock means quantity < minimum. Expired means expiry date before today.
  - Search combines with one filter.
- **FR-005:** As a station inventory crew member, I want to view an item's ID, name, quantity, minimum, unit mass, unit volume, location, condition, expiry date and criticality, so that I have everything needed to use or manage it. \[Goal 1\]
- **FR-006:** As a station inventory crew member, I want to record how much of an item was used and why, so that the onboard quantity stays accurate. \[Goal 1\]
  - The amount must be > 0, follow the unit's countable rule, and not exceed the current local quantity.
  - A reason is required. Disposal of damaged stock is recorded as usage with reason "Disposed".
- **FR-007:** As a station inventory crew member, I want to move an item to a different existing storage location, so that its recorded location stays accurate. \[Goal 1\]
- **FR-008:** As a station inventory crew member, I want to set an item's condition to Usable or Damaged with a reason, so that its condition record stays accurate. \[Goal 1\]
- **FR-009:** As a station inventory crew member or ground mission control, I want to correct an item's quantity or expiry date to a counted value with a reason, so that recording errors can be fixed. \[Goal 1\]
- **FR-010:** As a logistics planner, I want to create items and storage locations and edit item names, barcodes, minimums, criticality, unit mass and unit volume, so that inventory data and alert thresholds stay correct. \[Goals 1, 2\]
  - These changes reach the station on the next sync.
- **FR-011:** As a user, I want to view an item's change history, newest first, so that I can trace who changed what and when. \[Goals 1, 4\]
  - Each entry shows display ID, change, event time, user and sync status.
  - History includes Earth corrections, receipts and conflict resolutions.

### Supply alerts

- **FR-012:** As a station inventory crew member, I want a supply alert raised automatically when an item's quantity falls below its minimum, and resolved automatically when it returns to at least the minimum, so that shortages are noticed immediately and the alert list stays accurate. \[Goal 2\]
  - At most one alert is Active per item.
  - A change to the minimum can raise or resolve an alert.
  - Alerts cannot be raised or resolved by hand.
- **FR-013:** As a logistics planner, I want the manifest editor to list active alerts and mark each Covered or Not covered by the manifest, so that missions close open shortages. \[Goals 2, 3\]
  - An alert is Covered when quantity + line quantity ≥ minimum.

### Resupply planning

- **FR-014:** As a logistics planner, I want to create a resupply mission with its mass and volume capacity, so that I can begin planning a delivery. \[Goal 3\]
  - The Earth service assigns the mission ID.
  - The mission starts in Draft with an empty manifest at version 1.
- **FR-015:** As a logistics planner, I want to add, change or remove manifest lines in Draft and see running mass and volume totals against capacity, so that I can build a load that fits the vehicle. \[Goal 3\]
  - Totals are rounded to 2 decimals.
  - Going over capacity is allowed while editing and is shown in red.
- **FR-016:** As a logistics planner, I want each save that changes a draft's lines, capacities or expected arrival to create a new manifest version, so that everyone knows which cargo list is current. \[Goals 3, 4\]
  - A save with no changes keeps the version.
  - A save made against an out-of-date version is rejected.
- **FR-017:** As a logistics planner, I want to submit a draft only when it has at least one line and its mass and volume are each within capacity, so that only feasible plans reach approval. \[Goal 3\]
  - When submission fails, every failing check is listed.

### Mission approval and lifecycle

- **FR-018:** As ground mission control, I want to approve a submitted mission after capacity is re-checked, so that it can proceed to loading and dispatch. \[Goal 4\]
- **FR-019:** As ground mission control, I want to return a submitted mission to Draft with a reason, so that the planner can correct it. \[Goal 4\]
- **FR-020:** As ground mission control with reopen permission, I want to reopen an approved mission to Draft with a reason, so that late changes are made in a controlled way. \[Goal 4\]
  - Reopening clears the loading data.
- **FR-021:** As ground mission control, I want to cancel a Draft, Submitted or Approved mission with a reason, so that unneeded missions stop. \[Goal 4\]
  - Shipped, Received and Cancelled missions cannot be cancelled.
- **FR-022:** As a logistics planner, I want to record a loaded quantity for each line of an approved mission and note loading issues, so that missing cargo is identified before dispatch. \[Goal 4\]
  - Loaded quantities are ≥ 0 and may exceed planned.
- **FR-023:** As ground mission control, I want to confirm dispatch of an approved mission once every line has a loaded quantity and the expected arrival is set, so that it becomes Shipped. \[Goal 4\]
  - Any loading shortfall is shown as a warning but does not block dispatch.
- **FR-024:** As a user, I want to view a mission's status, expected arrival, manifest version and status history with time, user and reason for each change, so that I can track it end to end. \[Goal 4\]

### Receipt

- **FR-025:** As a station inventory crew member, I want to record receipt of a shipped mission by entering the delivered quantity for every line in one submission, even offline, so that inventory reflects what actually arrived. \[Goals 1, 4\]
  - Received quantities are ≥ 0.
  - Each line with a received quantity above 0 creates a Receipt update.
- **FR-026:** As a station inventory crew member, I want a discrepancy recorded automatically for every line where received differs from planned, and to report unlisted items, so that mismatches stay visible until mission control resolves them with a note. \[Goals 1, 4\]
  - Unlisted items do not change inventory.

### Offline operation and synchronization

- **FR-027:** As a station inventory crew member, I want every inventory change validated and saved in the onboard store before it is shown as saved, so that I can keep working without the Earth link. \[Goals 1, 5\]
  - A queued update is never deleted until Earth acknowledges it.
- **FR-028:** As a station inventory crew member, I want to see the updates that are awaiting sync or in conflict, oldest first, so that I know what has not yet reached Earth. \[Goal 5\]
- **FR-029:** As a user, I want updates to synchronize automatically when the link returns and on demand, so that none is lost or applied twice. \[Goal 5\]
  - Station updates are sent in recording order, then Earth changes since the last sync are pulled.
  - Earth deduplicates by update ID. A resend with identical content gets the original acknowledgement; a resend with different content is Rejected.
  - Each acknowledgement carries the new item version. Failures are retried with backoff.
- **FR-030:** As ground mission control, I want an update made against an out-of-date version to be merged when it touches a different field, and flagged as a conflict when the same field changed on both sides or the result would be negative, so that correct data is never silently lost. \[Goal 5\]
  - Usage and receipt quantity changes from both sides are added together rather than conflicting.
  - While a conflict is open, the station keeps its local value marked "Review required", and later updates on that item wait in the queue.
- **FR-031:** As ground mission control, I want to resolve a conflict by keeping the local or the Earth value with a reason, so that the decision is deliberate and documented. \[Goals 4, 5\]
  - The first resolution wins.
  - The result becomes a new Earth version, reaches the station on the next sync, and is recorded in history.
- **FR-032:** As ground mission control, I want the Earth service to reject malformed, stale or duplicate requests, so that a careless or malicious client cannot corrupt records. \[Goals 1, 4\]
  - Fields marked server-set are ignored if a client sends them.
  - Rejected: event times more than 5 minutes in the future, a base version newer than the current item version, required text that is empty after trimming, text over 1,000 characters, capacities ≤ 0, and a resolution for an update that is not in conflict.
  - Any action based on a stale status or version is checked against current state and rejected.
  - All text is escaped when shown.

# Acceptance Criteria

Each criterion tests the requirement with the same number. Unless a scenario says otherwise, it uses this data:

- Water packs: W01, 6 packs, minimum 10, 1.0 kg and 0.002 m3 each, Store A, Usable, expiry 2027-01-01, Critical.
- Food packets: F01, 40 packs, minimum 10, 0.25 kg and 0.0015 m3 each, Standard.
- Repair kit: K01, 1 kit, minimum 1, Store B, Usable, Critical.

```gherkin
AC-001: Dashboard summary (FR-001)
  Scenario: Dashboard shows the supply situation
    Given water packs have an active alert
    And Mission R12 is Approved with expected arrival 2026-11-02 14:00 UTC
    And there are 0 pending updates
    When I open the Dashboard
    Then I see "Water packs below minimum (6 / 10 packs)" first under supply alerts
    And I see "Mission R12 – Approved" as the next mission
    And I see "0 pending updates"
    And I see up to 10 recent activity entries from the past 7 days, each with a time and description
```

```gherkin
AC-002: Link and sync banner (FR-002)
  Scenario: Link available
    Given the Earth link is available and the last full sync was today at 10:30
    When I open any screen
    Then the banner shows "Earth link available" and "Last sync 10:30 UTC"

  Scenario: Link unavailable, last sync on an earlier day
    Given the Earth link is unavailable and the last full sync was 2026-10-25 09:50
    When I open any screen
    Then the banner shows "Earth link unavailable" and "Last sync 2026-10-25 09:50 UTC"
```

```gherkin
AC-003: Role-based controls (FR-003)
  Scenario: Crew cannot approve
    Given I am signed in as station inventory crew
    When I view a Submitted mission
    Then no "Approve" control is shown
    And an approve request sent directly is rejected as forbidden

  Scenario: Planner cannot record receipt or resolve conflicts
    Given I am signed in as a logistics planner
    When I view a Shipped mission and the Sync screen
    Then no "Record receipt" or "Keep local value" control is shown
```

```gherkin
AC-004: Search and filter inventory (FR-004)
  Scenario: Search by name and barcode
    When I search for "water"
    Then only Water packs is listed
    When I scan the barcode registered to W01
    Then only Water packs is listed

  Scenario Outline: Filters
    Given the repair kit is Damaged and food packets expired on 2026-10-01
    When I select the "<filter>" filter
    Then exactly <items> are listed
    Examples:
      | filter    | items                                |
      | All       | Water packs, Food packets, Repair kit |
      | Low stock | Water packs                          |
      | Damaged   | Repair kit                           |
      | Expired   | Food packets                         |
```

```gherkin
AC-005: View item details (FR-005)
  Scenario: Open item details
    Given I am on the Inventory screen
    When I select Water packs
    Then I see W01, 6 packs, minimum 10 packs, 1.0 kg, 0.002 m3, Store A, Usable, expiry 2027-01-01 and Critical
    And I can return to the inventory list
```

```gherkin
AC-006: Record usage (FR-006)
  Scenario: Valid usage
    Given food packets have 12 packs and a minimum of 10
    When I record usage of 3 packs with reason "Crew meal"
    Then the quantity becomes 9 packs
    And a Usage update with quantity delta -3 is recorded by me
    And I see "Usage saved. New quantity 9 packs. Low stock alert active."

  Scenario Outline: Invalid amount
    When I record usage of <amount> water packs with reason "Test"
    Then the usage is rejected
    And the quantity remains 6 packs and no update is created
    Examples:
      | amount |
      | 0      |
      | -1     |
      | 7      |
      | 1.5    |

  Scenario: Missing reason
    When I record usage of 1 water pack with no reason
    Then the usage is rejected
```

```gherkin
AC-007: Move item (FR-007)
  Scenario: Move to another location
    When I move the repair kit to Store C
    Then its location becomes Store C
    And its history shows "Store B → Store C"

  Scenario: Move to the current or an unknown location
    When I move the repair kit to Store B or to "Store Z"
    Then the move is rejected and no update is created
```

```gherkin
AC-008: Change condition (FR-008)
  Scenario: Report damage
    When I set the repair kit condition to Damaged with reason "Cracked casing"
    Then its condition becomes Damaged
    And a Condition update is recorded
    And it appears under the "Damaged" filter

  Scenario: Unknown condition
    When I set the repair kit condition to "Kinda broken"
    Then the change is rejected
```

```gherkin
AC-009: Correct stock (FR-009)
  Scenario: Crew recount
    Given water packs have an active alert
    When I correct the water pack quantity to 11 with reason "Recount"
    Then the quantity becomes 11 packs
    And a Correction update is recorded
    And the water packs alert is resolved
```

```gherkin
AC-010: Manage item data (FR-010)
  Scenario: Lower a minimum
    Given I am signed in as a logistics planner
    And water packs have an active alert
    When I change the water packs minimum to 5
    Then the water packs alert is resolved
    And the station shows minimum 5 after the next sync
```

```gherkin
AC-011: Change history (FR-011)
  Scenario: View history
    Given water packs have updates U101 (usage) and then U104 (correction)
    When I select "View change history"
    Then U104 is listed before U101
    And each entry shows its display ID, change, event time, user and sync status
```

```gherkin
AC-012: Automatic alerts (FR-012)
  Scenario: Alert raised below minimum
    Given food packets have 12 packs and a minimum of 10
    When usage of 3 packs is recorded
    Then an Active alert is raised about food packets

  Scenario: No duplicate alert
    Given water packs have an active alert
    When usage of 1 pack is recorded
    Then water packs still have exactly one Active alert

  Scenario: Alert resolved by restock
    Given water packs have an active alert
    When received cargo raises the quantity to 26 packs
    Then the water packs alert is Resolved
```

```gherkin
AC-013: Alerts in planning (FR-013)
  Scenario: Covered and not covered
    Given water packs have an active alert
    And Mission R12 is in Draft
    When I add 4 water packs to the manifest
    Then the alert is marked "Covered"
    When I change the line to 3 water packs
    Then the alert is marked "Not covered"
```

```gherkin
AC-014: Create mission (FR-014)
  Scenario: New mission
    Given I am signed in as a logistics planner
    When I create a mission with capacity 500 kg and 4.0 m3
    Then it gets the next mission ID, for example R12
    And its status is Draft
    And its manifest is empty at version 1

  Scenario: Invalid capacity
    When I create a mission with capacity 0 kg
    Then the mission is not created
```

```gherkin
AC-015: Build manifest (FR-015)
  Scenario: Running totals
    Given Mission R12 is in Draft with capacity 500 kg and 4.0 m3
    When I add 20 water packs and 40 food packets
    Then totals show "30.00 kg / 500 kg" and "0.10 m3 / 4.0 m3"
    When I remove food packets
    Then totals show "20.00 kg / 500 kg" and "0.04 m3 / 4.0 m3"

  Scenario: Over capacity while editing
    When the total mass reaches 520 kg
    Then the mass total is shown in red and the change is kept

  Scenario: Edit outside Draft
    Given Mission R12 is Submitted
    When I try to change a manifest line
    Then the change is rejected
```

```gherkin
AC-016: Save draft and versioning (FR-016)
  Scenario: Version increments only on change
    Given Mission R12's manifest is at version 2
    When I change the water pack quantity and save
    Then the manifest version becomes 3
    And the changes are present when I reopen the mission
    When I save again with no changes
    Then the version stays 3

  Scenario: Stale save
    Given another planner saved version 3
    When I save changes made against version 2
    Then my save is rejected and version 3 is unchanged
```

```gherkin
AC-017: Submit for approval (FR-017)
  Scenario: Valid cargo
    Given Mission R12 is in Draft with 30 kg and 0.10 m3 against 500 kg and 4.0 m3
    When I select "Submit for approval"
    Then Mission R12 becomes Submitted

  Scenario Outline: Invalid cargo
    Given Mission R12 is in Draft with <mass> kg and <volume> m3 against 500 kg and 4.0 m3, and <lines> lines
    When I select "Submit for approval"
    Then the submission is rejected listing <errors>
    And Mission R12 remains in Draft
    Examples:
      | mass | volume | lines | errors                                |
      | 520  | 0.10   | 2     | mass capacity exceeded                |
      | 30   | 4.20   | 2     | volume capacity exceeded              |
      | 520  | 4.20   | 2     | mass and volume capacity exceeded     |
      | 0    | 0      | 0     | manifest has no lines                 |
```

```gherkin
AC-018: Approve mission (FR-018)
  Scenario: Authorized approval
    Given Mission R12 is Submitted
    And I am signed in as ground mission control
    When I approve Mission R12
    Then it becomes Approved
    And status history shows "Approved" with my name and the time
```

```gherkin
AC-019: Return for revision (FR-019)
  Scenario: Return with a reason
    Given Mission R12 is Submitted
    And I am signed in as ground mission control
    When I return Mission R12 with reason "Add oxygen candles"
    Then it becomes Draft and the planner can edit its manifest

  Scenario: Return without a reason
    When I return Mission R12 with no reason
    Then the action is rejected and it remains Submitted
```

```gherkin
AC-020: Reopen approved mission (FR-020)
  Scenario: Authorized reopen
    Given Mission R12 is Approved with loaded quantities recorded
    And I am ground mission control with reopen permission
    When I reopen Mission R12 with reason "Late change"
    Then it becomes Draft and its loaded quantities are cleared

  Scenario: Unauthorized reopen
    Given Mission R12 is Approved
    And I am ground mission control without reopen permission
    When I attempt to reopen Mission R12
    Then the action is rejected and it remains Approved
```

```gherkin
AC-021: Cancel mission (FR-021)
  Scenario Outline: Cancel from an allowed status
    Given Mission R12 is <status>
    And I am signed in as ground mission control
    When I cancel Mission R12 with reason "No longer needed"
    Then it becomes Cancelled
    Examples:
      | status    |
      | Draft     |
      | Submitted |
      | Approved  |

  Scenario Outline: Cancel not available
    Given Mission R12 is <status>
    Then no cancel control is shown
    And a cancel request sent directly is rejected
    Examples:
      | status    |
      | Shipped   |
      | Received  |
      | Cancelled |
```

```gherkin
AC-022: Loading review (FR-022)
  Scenario: Record a shortfall
    Given Mission R12 is Approved and plans 20 water packs
    When I record 18 water packs as loaded
    Then the loading review shows "Planned 20, Loaded 18, Missing 2"
    And I can record the loading issue "2 water packs still need to be loaded"
```

```gherkin
AC-023: Confirm dispatch (FR-023)
  Scenario: Dispatch an approved mission
    Given Mission R12 is Approved, every line has a loaded quantity, and expected arrival is set
    And I am signed in as ground mission control
    When I confirm dispatch
    Then it becomes Shipped and the dispatch time is recorded

  Scenario: Missing loaded quantity
    Given one line of Mission R12 has no loaded quantity
    When I confirm dispatch
    Then the dispatch is rejected and it remains Approved
```

```gherkin
AC-024: View mission status (FR-024)
  Scenario: Track a shipped mission
    Given Mission R12 is Shipped with expected arrival 2026-11-02 14:00 UTC and manifest version 3
    When I open the Mission status screen for Mission R12
    Then I see status "Shipped", expected arrival "2026-11-02 14:00 UTC" and "Manifest version 3"
    And I see status history "Draft > Submitted > Approved > Shipped", each step with time and user
    And I can open the cargo manifest
```

```gherkin
AC-025: Record receipt (FR-025)
  Scenario: Full receipt while offline
    Given Mission R12 is Shipped with 20 water packs and 40 food packets
    And the Earth link is unavailable
    And I am signed in as station inventory crew
    When I record received quantities of 20 and 40
    Then Mission R12 becomes Received
    And water packs and food packets increase by 20 and 40
    And two Receipt updates are Awaiting sync

  Scenario: Missing quantity
    Given Mission R12 is Shipped
    When I record receipt without a quantity for every line
    Then I see "Receipt requires actual delivered quantities"
    And Mission R12 remains Shipped

  Scenario: Receipt sent twice
    Given Mission R12 is Received
    When the same receipt is sent again
    Then the original result is returned and quantities do not change again
```

```gherkin
AC-026: Discrepancies (FR-026)
  Scenario: Short delivery
    Given Mission R12 is Shipped with 20 water packs on the manifest
    When I record 18 water packs received
    Then water packs increase by 18
    And an Open discrepancy shows expected 20, received 18
    When ground mission control resolves it with a note
    Then it becomes Resolved

  Scenario: Unlisted item
    When I report 1 unlisted "Spare filter" during receipt
    Then an Open discrepancy is recorded with no item
    And no inventory quantity changes
```

```gherkin
AC-027: Offline save (FR-027)
  Scenario: Record usage while the link is unavailable
    Given the Earth link is unavailable
    When I record usage of 2 water packs with reason "Crew consumption"
    Then update U101 is saved in the onboard store
    And the water pack quantity shows 4 packs
    And I see "Saved locally"
    And U101 has sync status "Awaiting sync"
```

```gherkin
AC-028: Pending updates list (FR-028)
  Scenario: View pending updates
    Given the Earth link is unavailable
    And U101 (water packs used 2) and then U102 (repair kit moved to Store C) are Awaiting sync
    When I open the Sync screen
    Then I see "2 updates pending" and "Inventory remains available locally"
    And U101 is listed before U102, both "Awaiting sync"
```

```gherkin
AC-029: Synchronize (FR-029)
  Scenario: Successful sync
    Given U101 is Awaiting sync
    When the Earth link is restored
    Then U101 is sent, deduplicated and version-checked
    And Earth acknowledges U101 with the new item version
    And U101 becomes Synchronized and the pending count decreases

  Scenario: Identical resend
    Given Earth has already applied U101
    When U101 is sent again unchanged
    Then the original acknowledgement is returned and the quantity changes only once

  Scenario: Altered resend
    When U101 is sent again with a different quantity delta
    Then it is Rejected and shown on the Sync screen
```

```gherkin
AC-030: Conflict detection (FR-030)
  Scenario: Same field changed on both sides
    Given the station moved the repair kit to Store B as U103
    And ground mission control corrected its location to Store C on Earth
    When U103 is synchronized
    Then U103 is flagged as Conflict and neither value overwrites the other
    And the station still shows Store B
    And the Sync screen shows local "Store B", Earth "Store C" and "Review required"

  Scenario: Different fields
    Given the station recorded usage of water packs
    And ground mission control corrected the water packs expiry date on Earth
    When the usage is synchronized
    Then both changes apply and no conflict is raised
```

```gherkin
AC-031: Conflict resolution (FR-031)
  Scenario Outline: Resolve with a reason
    Given conflict U103 is awaiting review
    And I am signed in as ground mission control
    When I enter the reason "Verified with station crew" and select "<choice>"
    Then the repair kit location becomes <location> on Earth, and on the station after the next sync
    And the resolution and my reason appear in its history
    Examples:
      | choice           | location |
      | Keep local value | Store B  |
      | Keep Earth value | Store C  |

  Scenario: Missing reason
    When I select "Keep local value" with a reason of only spaces
    Then the resolution is rejected and U103 remains a conflict

  Scenario: Second resolution
    Given another user has already resolved U103
    When I resolve U103
    Then my resolution is rejected
```

```gherkin
AC-032: Request validation (FR-032)
  Scenario: Spoofed author
    When an update arrives with recordedBy set to another user
    Then it is stored with the signed-in user as recordedBy

  Scenario Outline: Rejected requests
    When an update arrives with <problem>
    Then it is rejected and nothing changes
    Examples:
      | problem                                      |
      | an event time 1 hour in the future           |
      | a base version newer than the item's version |
      | a 2,000-character reason                     |
```
