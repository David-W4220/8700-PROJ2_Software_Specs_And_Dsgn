# Description

My part of the project focuses on station inventory and communication with Earth. Crew members record when they use supplies. Workers on Earth can see the recorded amounts to help plan resupply. If the station loses its connection to Earth, the crew can still save inventory changes on the station. When the connection comes back, the system sends those changes to Earth. This part does not cover payroll, taxes, accounting, spacecraft control, or life support control.

# Goals

1. **G1 Maintain Station Inventory:** Keep the recorded amounts of supplies up to date when crew members use them.
2. **G5 View Inventory from Earth:** Let workers on Earth check how much of each supply is recorded on the station.
3. **G7 Save Changes on Station:** Keep inventory changes saved on the station when communication with Earth is down.
4. **G8 Sync Changes with Earth:** Send saved inventory changes to Earth when communication comes back.

# Domain Model

## Actors

- **Station Inventory Crew:** Uses supplies and records how much was used. Crew members can still work with inventory when the station is offline.
- **Ground Mission Control:** Checks the station's inventory from Earth.
- **Logistics Planner:** Uses inventory amounts to help decide what needs to be sent to the station.

## Objects

- **InventoryItem:** A supply or piece of equipment. It has a name, unit, quantity, and may also have a location, condition, expiration date, weight, volume, or minimum stock amount.
- **StorageLocation:** The place where an item is kept on the station.
- **InventoryUpdate:** A record of a change to an item. It includes what changed, who made the change, when it happened, and a unique ID for syncing.
- **Station Inventory:** The local inventory records saved on the station.
- **Pending Update:** A change saved on the station that has not been confirmed by Earth yet.
- **User:** A person signed in to the system. Their role controls which actions they can take.

## Domain Rules

- An item's quantity cannot be negative.
- A crew member cannot record using more than the usable amount of an item.
- A change saved while offline stays pending until Earth confirms it.
- Sending the same update again must not apply the change twice.
- If the station and Earth both change the same item, the system keeps both versions for review instead of replacing one without warning.

# Functional Requirements

### FR-001 Record Supply Use

The system must let a crew member record how much of a supply item was used. It must update the available amount, show the unit, reject negative amounts or usage above what is available, and record who made the change and when.

**Goals:** G1

### FR-002 View Inventory from Earth

The system must let Ground Mission Control and Logistics Planners see the recorded amount and unit for each supply item. It must also show when the inventory last synced successfully with Earth.

**Goals:** G5, G8

### FR-003 Save Changes While Offline

If the station loses communication with Earth, the system must save inventory changes on the station. The changes must still be there after the app is restarted. The system must show how many updates are waiting to sync and when the last successful sync happened.

**Goals:** G7

### FR-004 Sync Changes When Communication Returns

When communication with Earth comes back, the system must send the waiting inventory updates using unique IDs. If Earth already accepted an update, sending it again must not apply it twice. If the station and Earth changed the same item, the system must keep both versions for an authorized reviewer. The reviewer must be able to choose the correct value and enter a reason. The system must record the chosen value, the reason, who made the choice, and when.

**Goals:** G8

# Acceptance Criteria

### AC-001 Record Supply Use (FR-001)

```gherkin
Feature: Recording supply use

Scenario: Update the amount after a crew member uses supplies
  Given the station has 12 usable packs of water
  When a crew member records that 3 packs were used
  Then the system shows 9 usable packs left
  And records who made the change and when
```

### AC-002 Reject Usage Above the Available Amount (FR-001)

```gherkin
Feature: Checking inventory amounts

Scenario: Do not allow a crew member to use more than the available amount
  Given the station has 4 usable packs of an item
  When a crew member tries to record using 5 packs
  Then the system shows an error
  And the amount stays at 4 packs
```

### AC-003 Reject a Negative Amount (FR-001)

```gherkin
Feature: Checking inventory amounts

Scenario: Do not allow a negative quantity
  Given the station has 4 usable packs of an item
  When a crew member tries to set the amount to -1
  Then the system shows an error
  And the amount stays at 4 packs
```

### AC-004 View Amounts from Earth (FR-002)

```gherkin
Feature: Viewing station inventory from Earth

Scenario: Check the station's recorded supply amounts
  Given an inventory change has synced with Earth
  When Ground Mission Control opens the inventory view
  Then the system shows the recorded amount and unit
  And shows when the last successful sync happened
```

### AC-005 Keep Offline Changes After Restarting the App (FR-003)

```gherkin
Feature: Offline inventory changes

Scenario: Keep a change saved while the station is offline
  Given a crew member is signed in
  And the station has 5 usable packs of water
  And communication with Earth is down
  When the crew member records using 2 packs and restarts the app
  Then the station still shows 3 usable packs of water
  And the change is still waiting to sync
  And the system shows 1 update waiting to sync
  And the last successful sync time is still shown
```

### AC-006 Send Waiting Updates After Communication Returns (FR-004)

```gherkin
Feature: Syncing inventory changes

Scenario: Send a saved change when communication comes back
  Given update U102 is waiting to sync on the station
  And communication with Earth has returned
  When the system syncs inventory changes
  Then it sends update U102 to Earth
  And marks U102 as synced after Earth accepts it
```

### AC-007 Do Not Apply the Same Update Twice (FR-004)

```gherkin
Feature: Syncing inventory changes

Scenario: Retry an update after its confirmation was lost
  Given Earth accepted update U101 but the station did not get the confirmation
  And communication with Earth is available again
  When the station sends update U101 again
  Then Earth confirms that it already accepted the update
  And the item amount is not changed a second time
```

### AC-008 Keep Conflicting Changes for Review (FR-004)

```gherkin
Feature: Reviewing inventory changes

Scenario: Keep station and Earth changes to the same item
  Given the station changed an item's location to Store B
  And Earth changed the same item's location to Store C
  When the changes sync
  Then the system keeps both locations for review
  And an authorized reviewer can choose the correct location and enter a reason
  And the system records the chosen location, the reason, who made the choice, and when
```
