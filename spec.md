Project 2: SDD Specification - David Wang


# Description
Our Commercial Space Station Inventory and Resupply System plans resupplies, manages cargo manifests, and tracks deliveries for commercial a space station. Station Inventory Crew can search for items and view their quantities, conditions and locations, as well as manage inventory records. Logistics Planners can identify items needing resupply and develop feasible mission plans. Ground Mission Control can review inventory changes, cargo loading, and delivery progresses. 

The system do preserves and re-syncs inventory changes during communication with Earth. Payroll, taxes, general accounting, life support equipment and spacecraft control are outside the scope of this system.

# Goals

1. **G1 Maintain station inventory:** Keep item quantities, locations, and conditions accurate and up to date.
2. **G2 Identify resupply needs:** Help Logistics Planners identify low-stock items and confirm item importance.
3. **G3 Plan resupply missions:** Select items that fit mission cargo weight and volume limits and maintain accurate cargo manifests.
4. **G4 Monitor Station Inventory:** Allow Ground Mission Control to confirm inventory records and its recent changes, as well as synchronization status.
5. **G5 Support Resupply Operations:** Allow Ground Mission Control to review manifests, acknowledge loading problems and track delivery progress.
6. **Supporting system goal SysG4 Maintain Inventory Availability During Communication Loss:** The system must save inventory changes in station locally when losing communication with Earth, and synchronize them when communication is restored

# Domain Model

## Actors

- **Station Inventory Crew:** Searches inventory; records item usage, movement, condition, and missing items; and records received cargo.
- **Logistics Planner:** Reviews inventory and resupply needs, selects items for missions, checks cargo capacity, and prepares or updates cargo manifests.
- **Ground Mission Control:** Monitors inventory status and supply cargo loading, and tracks delivery progress.
- **Inventory and Resupply System:** The software system that stores and displays inventory data, capable of synchronizing updates, to support resupply missions between Earth and the space station.

## Objects

- **InventoryItem:** A supply or piece of equipment. Attributes include a unique item ID, name, unit, quantity, condition, expiration date, unit weight, unit volume, minimum stock, and importance. Inventory quantity can't be negative and recorded usage cannot exceed the available usable quantity.
- **StorageLocation:** Identifies where an item is stored. Each inventory record has one current location. Separate lots in different locations are represented by separate records.
- **InventoryUpdate:** Records an inventory change, including the affected item, change details, user, and time. Each update has a unique ID so it can be identified during synchronization and retries.
- **SupplyAlert:** Identifies an item that needs attention, such as an item below its minimum stock or a missing item.
- **ResupplyMission:** Represents a resupply shipment and stores its status, weight and volume limits, and expected arrival. Mission statuses are Draft, Submitted, Approved, Shipped, Received, or Cancelled.
- **CargoManifest:** Records the cargo planned for a mission, its version, and its status. Editing a submitted or approved manifest before dispatch returns the mission to Draft and requires resubmission and approval.
- **ManifestLine:** Connects a cargo manifest to an inventory item and records planned, loaded, and received quantities.
- **User** Identify a user with a role (Station Inventory Crew, Logistics Planner, or Ground Mission Control) and the actions that a user can perform depending on his role.

## Domain Rules

- Item IDs and update IDs must be unique.
- Inventory quantities cannot be negative. The system must not allow recorded usage to exceed available usable quantity.
- A resupply mission cannot be submitted if its total cargo weight or volume exceeds mission capacity, or if a required weight or volume measurement is missing.
- Retrying an update that Earth has already accepted must not apply the update twice.
- Conflicting station and Earth updates must be retained for review rather than silently overwriting one another.
- Only authorized users may perform restricted actions, including mission approval, dispatch confirmation, cargo receipt, and conflict resolution.

# Functional Requirements

### FR1 Find An Item
As a Station Inventory Crew member, I want to find an item and view its current quantity, location, and condition n within three interactions from the main screen, so that I can easily check the station's inventory.
**Goal:** G1

### FR2 Update Item Quantity
As a Station Inventory Crew member, I want to update an item's quantity, so that the inventory is in pace with the available stock. The system shall display the item's unit, reject negative quantities and usage above the available usable quantity, and record the user and time of the operation.
**Goal:** G1

### FR3  Consistent Inventory Changes
The system shall apply the same inventory validation rules to all crew members, display a saved value immediately after a valid update, and make the recent changes available for the next crew shift.
**Goals:** G1, G4

### FR4 Identify Resupply Needs
As a Logistics Planner, I want to confirm current inventory and identify items requiring replenishment, so that I can plan resupply needs. For each item, the system shall identify usable quantities below its configured minimum and display its importance.
**Goal:** G2

### FR5 Check Cargo Capacity
As a Logistics Planner, I want to select items for a resupply mission and check their weight and volume against available cargo capacity, so that I can prepare for a feasible mission. The system shall calculate the total weight and volume from item quantities and units, and block submission if either capacity is exceeded or a required measurement is missing.
**Goal:** G3

### FR6 Create and Update Cargo Manifests
As a Logistics Planner, I want to create and update cargo manifests and review mission status, so that I can track planned cargo throughout resupply. Each manifest shall identify its mission, item quantities, and version. Editing a submitted or approved manifest before dispatch shall return the mission to Draft for resubmission and reapproval.
**Goal:** G3

### FR7 Monitor Inventory from Ground Control
As a Ground Mission Control user, I want to view current station inventory and recent updates, so that I can monitor supplies and identify missing items. The system shall display the latest successful synchronization time alongside records.
**Goals:** G1, G4

### FR8 Verify Cargo Loading
As a Ground Mission Control user, I want to compare planned cargo with loaded cargo, so that I can identify missing items or loading problems before shipment. The system shall display planned and loaded quantities and allow recodrings for reported differences.
**Goal:** G5

### FR9 Track and Receive Shipments
As a Ground Mission Control user, I want to view a resupply delivery's status, expected arrival, and status history, so that I can track its delivery progress. Station Inventory Crew shall be able to record actual received quantities. The system shall record the actual received quantity to inventory, as well as any shortages or damages.
**Goals:** G3, G5

### FR10 Save Inventory Changes Offline
The system shall save inventory changes locally when communication with Earth is unavailable and preserve those changes after the application restarts, and display a count of pending updates and the last successful synchronization time.
**Goal:** SysG4 

### FR11 Synchronize Inventory Changes
When communication with Earth returns, the system shall send pending updates using unique update IDs. Retrying an update that Earth has already accepted shall not apply it twice. If the station and Earth contain conflicting changes, the system shall retain both versions for review instead of silent overwrites.
**Goal:** SysG4 

### FR12 Enforce Permissions and Record Changes
The system shall restrict inventory changes, manifest approval, dispatch confirmation, cargo receipt, and conflict resolution to authorized users. It shall record the user, time, and details of changes. 
**Goals:** G1, G3, G5, SysG4

# Acceptance Criteria

### AC1 Find an Item (FR1)
```gherkin
Feature: Inventory lookup

Scenario: View an item's current inventory details
  Given a crew member is at the dashboard
  And water packs exist in the inventory
  When the crew member opens Inventory and selects water packs
  Then the system displays the current quantity, location, and condition
  And these details are available within three interactions from the main screen
```

### AC2 Record Usage and Flag Low Stock (FR2, FR4)
```gherkin
Feature: Inventory updates

Scenario: Record valid usage that brings an item below minimum stock
  Given water has 12 usable packs
  And the minimum stock level is 10 packs
  When a crew member records 3 packs used
  Then the system shows 9 usable packs
  And displays a low-stock warning
  And records the user and time of the accepted change
```

### AC3 Reject Usage Above Available Quantity (FR2)
```gherkin
Scenario: Reject usage greater than available stock
  Given an item has 4 usable packs
  When a crew member attempts to record 5 packs used
  Then the system shows an error
  And the available quantity remains 4 packs
```

### AC4 Reject a Negative Quantity (FR2)

```gherkin
Scenario: Reject a negative inventory quantity
  Given an item has 4 usable packs
  When a crew member attempts to set its quantity to -1
  Then the system shows an error
  And the available quantity remains 4 packs
```

### AC5 Keep Changes Consistent for Handovers (FR3)
```gherkin
Scenario: The next shift can see a saved inventory change
  Given a crew member records an item's new location and the system saves the change
  When another crew member opens the same item record
  Then the saved location is displayed
  And this recent change is available in the update history
```

### AC6 Enforce Cargo Weight Capacity (FR5)
```gherkin
Feature: Resupply planning

Scenario: Block a mission that exceeds weight capacity
  Given a mission has a 500 kg weight limit
  And its selected cargo already weighs 490 kg
  When the planner adds 20 packs that weigh 1 kg each and submits the plan
  Then the system calculates a total weight of 510 kg
  And blocks submission
  And keeps the mission in Draft
```

### AC7 Enforce Cargo Volume Capacity (FR5)
```gherkin
Scenario: Block a mission that exceeds volume capacity
  Given a mission's selected cargo is already at its volume limit
  When the planner adds another item with a positive volume and submits the plan
  Then the system spots the volume limit being exceeded
  And blocks submission
```

### AC8 Require Cargo Measurements (FR5)
```gherkin
Scenario: Block submission when a selected item lacks a required measurement
  Given a selected resupply item has no recorded unit weight or volume
  When the planner attempts to submit the mission
  Then the system spots the missing measurement
  And blocks submission until the required measurement is filled
```

### AC9 Reapprove an Edited Manifest (FR6)
```gherkin
Scenario: Editing an approved manifest before dispatch
  Given a resupply mission has an approved cargo manifest
  And the mission has not been dispatched
  When the planner edits the manifest
  Then the mission returns to Draft
  And the edited manifest must be resubmitted and approved before dispatch
```

### AC10 View Inventory Updates from Ground Control (FR7)
```gherkin
Feature: Ground inventory monitoring

Scenario: Review current inventory and synchronization time
  Given inventory changes have been synchronized with Earth
  When Ground Mission Control opens the inventory view
  Then the system displays current inventory and recent updates
  And shows the latest successful synchronization time
```

### AC11 Identify a Loading Difference (FR8)
```gherkin
Feature: Cargo loading

Scenario: Record a shortage during loading
  Given a cargo manifest lists 20 water packs
  When Ground Mission Control sees a loading record showing 18 packs loaded
  Then the system displays a difference of 2 packs
  And allows the user to record the loading problem
```

### AC12 Receive a Partial Shipment (FR9)
```gherkin
Feature: Shipment receiving

Scenario: Record received cargo when some items are missing
  Given a Shipped mission lists 20 water packs
  And only 18 usable packs actually arrive
  When Station Inventory Crew confirms only 18 packs recieved
  Then the system adds 18 packs to inventory once
  And records the 2-pack shortage
  And shows the mission as Received
```

### AC13 Save Changes During a Communication Outage (FR10)
```gherkin
Feature: Offline inventory updates

Scenario: Preserve a local update after restarting the application
  Given a crew member is signed in
  And communication with Earth is unavailable
  When the crew member records 2 packs used and restarts the application
  Then the updated local quantity is still available
  And the update remains pending synchronization
  And the last successful synchronization time remains visible
```

### AC14 Don't Apply Duplicated Retry Update (FR11)
```gherkin
Feature: Inventory synchronization

Scenario: Retry an update that Earth already accepted
  Given Earth accepted update U101 but the station didn't receive confirmation
  When the station sends update U101 again after communication returns
  Then Earth acknowledges the previously accepted update
  And the inventory quantity won't be changed a second time
```

### AC15 Resolve a Synchronization Conflict (FR11, FR12)
```gherkin
Scenario: Keep competing changes for authorized review
  Given the station changed an item's location to Store B
  And Earth changed the same item's location to Store C
  When the changes synchronize
  Then the system retains both values for review
  And an authorized reviewer can select the correct value and enter a reason
  And the selected value, reviewer, time, and reason are recorded
```

### AC16 Deny Unauthorized Actions (FR12)
```gherkin
Feature: Role-based permissions

Scenario: Prevent an unauthorized user from approving a mission
  Given a user does not have permission to approve missions
  When the user attempts to approve a mission
  Then the system denies the action
  And the mission status remains unchanged
```

### AC17 Audit an Accepted Change (FR12)
```gherkin
Scenario: Record who changed an inventory item
  Given a signed-in user is authorized to update inventory
  When the user saves an accepted change to an item
  Then the system records the user's identity, the time, and the change details
```