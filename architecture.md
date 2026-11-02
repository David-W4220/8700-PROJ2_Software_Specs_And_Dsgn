# Architecture Description

## 1. Overview

The system will use a modular application with separate modules for inventory management, resupply planning, mission and shipment management, access control, auditing, storage, and synchronization.

The station-side application will use persistent local storage so Station Inventory Crew can view and update inventory when communication with Earth is unavailable. When communication is restored, the Synchronization module will transfer pending updates to the Earth-side system. Ground Mission Control will be able to view synchronized inventory information and operational updates.

The Earth-side system is treated as an external system because its internal implementation is not defined in the specification.

## 2. Modules

| Module | Responsibility | May Depend On |
|---|---|---|
| User Interface | Provides role-specific views for Station Inventory Crew and Ground Mission Control. Allows users to search inventory, view low-stock warnings, manage resupply and mission information, view synchronization status, and review conflicts. The inventory search interface should allow users to find an item within three interactions (AC1). | Authentication and Authorization; Inventory Management; Resupply Planning; Mission and Shipment Management; Synchronization; Earth-side system (external) |
| Authentication and Authorization | Authenticates users and checks whether their roles permit requested operations, including inventory updates, manifest approval, dispatch, receipt, and conflict resolution (AC16). | Local Data Storage |
| Inventory Management | Searches inventory records, validates and saves quantity changes, identifies accepted inventory updates, and maintains inventory history for crew handovers (AC1–AC5, AC10). | Authentication and Authorization; Local Data Storage; Audit Logging |
| Resupply Planning | Identifies items below their minimum quantities and calculates proposed cargo weight and volume. Rejects plans that exceed capacity or lack required measurements (AC2, AC6–AC8). | Authentication and Authorization; Inventory Management; Local Data Storage |
| Mission and Shipment Management | Manages cargo manifests and mission status, controls submission and approval, compares planned and loaded cargo, and records shipment receipts and discrepancies (AC6, AC9, AC11–AC12). It checks the results from Resupply Planning before allowing a mission to be submitted. | Authentication and Authorization; Inventory Management; Resupply Planning; Local Data Storage; Audit Logging |
| Audit Logging | Records the user, timestamp, operation, affected record, and relevant change details for audited operations. For conflict resolution, it also records the selected value and the reviewer. | Local Data Storage |
| Local Data Storage | Persistently stores station-side inventory, user and role records, mission and manifest records, update history, audit records, and pending synchronization updates. Stored records are encrypted at rest. | None |
| Synchronization | Sends pending inventory updates to Earth, processes acknowledgements, prevents duplicate updates, identifies conflicting changes, and maintains the last successful synchronization time. Data transmitted between the station and Earth is encrypted in transit (AC10, AC13–AC15). | Local Data Storage; Audit Logging; Earth-side system (external) |

## 3. Request Flow

### Scenario A: Inventory update during a communication outage

1. A Station Inventory Crew member searches for an item through the User Interface.
2. Authentication and Authorization verifies the user's identity and checks permission to update inventory.
3. The user enters the quantity used. Inventory Management validates the change, including checking that the quantity is not negative and that usage does not exceed the available quantity.
4. If the change is valid, Inventory Management creates an update record with a unique update ID and a timestamp from the station's system clock.
5. Local Data Storage saves the updated quantity, update history, audit record, and pending synchronization record together. The application reports success only after the local save is completed.
6. The User Interface displays the updated inventory and the number of pending updates. The saved changes remain available after an application restart.
7. When communication with Earth is restored, Synchronization begins attempting to send pending updates within 60 seconds.
8. Synchronization sends each update ID and its data to the Earth-side system. The Earth-side system checks update IDs so that previously processed updates are not applied again.
9. If conflicting changes are detected, Synchronization retains both versions for review instead of silently overwriting either one.
10. An authorized user reviews the conflict through the User Interface and selects the value to keep. The resolution, selected value, reviewer, timestamp, and reason are recorded by Audit Logging.
11. After an update is acknowledged, Synchronization marks it as synchronized and updates the last successful synchronization time. Failed updates remain pending for another attempt.

### Scenario B: Resupply planning and shipment operations

1. Resupply Planning identifies items below their configured minimum quantities.
2. The Logistics Planner selects items for resupply. Resupply Planning checks that required weight and volume measurements are available and that the proposed cargo is within mission capacity.
3. Mission and Shipment Management allows submission only after the capacity checks pass. If the cargo exceeds capacity or required measurements are missing, the mission cannot be submitted and remains in Draft.
4. If a submitted or approved manifest is edited before dispatch, Mission and Shipment Management returns the mission to Draft and requires resubmission and reapproval.
5. During loading, Mission and Shipment Management compares the loaded cargo with the approved manifest and records any differences.
6. When a shipment arrives, Mission and Shipment Management records the actual received quantities and any shortage or damage. Inventory Management updates inventory using the quantities actually received.

## 4. Design Decisions

| Decision | Reason |
|---|---|
| Use a modular application instead of separate microservices. | **Preference:** This is a course project, and the requirements do not require independently deployed services. A modular application is simpler to develop and maintain. |
| Use persistent station-side storage for inventory records and pending updates. | FR10, FR11, AC13, NFR1, and NFR2 require inventory operations to continue during communication outages and updates to survive application restarts. |
| Save inventory changes locally before reporting success. | FR2, FR10, AC3, AC4, and AC13 require valid updates to be saved and invalid quantity changes to be rejected. Saving the related records together prevents a partially saved update. |
| Assign each inventory update a unique ID and retain it until acknowledged. | FR11 and AC14 require synchronization retries without applying the same update more than once. The Earth-side system must also recognize previously processed IDs. |
| Retain conflicting versions and require authorized review instead of automatic overwriting. | FR11 and AC15 require conflicting updates to be reviewed rather than silently overwritten. |
| Enforce permissions within the application before protected operations are performed. | FR12 and AC16 require unauthorized operations to be rejected. Hiding options in the User Interface alone would not enforce this requirement. |
| Record the user, timestamp, operation, affected record, and relevant change details. | FR12 and AC17 require accepted changes to have an audit trail. Conflict resolutions also need to record the reviewer and selected value. |
| Use station-side inventory records for inventory searches and index commonly searched fields. | FR1, AC1, and NFR5 require inventory searches to work locally and meet the specified performance target. |
| Require successful capacity validation before mission submission. | FR5, FR6, and AC6–AC9 require cargo limits and measurements to be checked and manifest changes to go through the required submission and approval process. |
| Encrypt stored records and data transmitted between the station and Earth. | NFR4 requires records to be encrypted at rest and communications to be encrypted in transit. The Earth-side system must provide encryption for its own stored records. |
| Prevent the same shipment receipt from being applied more than once. | **Design safeguard:** This helps prevent duplicate receipt submissions from adding the same quantity to inventory twice. AC12 requires accurate receipt recording, although the specification does not explicitly define duplicate-receipt behavior. |

## 5. Constraints and Known Limits

- The specification does not identify a programming language, framework, database product, hosting provider, or authentication library. These choices will follow the team's implementation environment.
- The architecture assumes persistent storage is available at the station. The Earth-side system is treated as an external integration endpoint. Its internal implementation and interface details are not defined.
- The User Interface provides role-specific access for station and Ground Mission Control users, but the exact deployment and hosting arrangement for the Earth-side interface is not specified.
- Offline availability is guaranteed for viewing locally stored inventory and recording inventory changes. Offline creation or approval of manifests and other mission operations is not specified.
- Synchronization conflicts require manual review. The architecture does not include automatic conflict merging.
- The synchronization process relies on the Earth-side system recognizing previously processed update IDs to prevent duplicate application.
- The search performance target is two seconds in at least 95 out of 100 trials for 10,000 inventory records on the team's agreed test device. This must be verified through testing.
- Timestamps are initially recorded using the station's system clock and retained during synchronization. A detailed clock synchronization policy is not defined.
- The design targets the current single-station scope. Supporting multiple stations would require additional synchronization and conflict-handling design.

## 6. Out of Scope

- Payroll management.
- Taxes and general accounting.
- Life-support equipment and control.
- Spacecraft control.

## 7. Spec Issues

1. **Role permissions are not fully defined.** FR12 requires role-based access, but the specification does not provide a complete mapping of which roles can approve manifests, dispatch missions, receive shipments, or resolve synchronization conflicts. The team should define a role-permission matrix before implementation and testing.
2. **The Earth-side interface is not specified.** FR7 and FR11 require Ground Mission Control to access synchronized information and the station to exchange updates with Earth, but the specification does not define the interface or data exchange format.
3. **Conflict detection needs a precise rule.** FR11 and AC15 require conflicting updates to be identified and reviewed, but the specification should define what record or version information is used to determine that two updates conflict.
4. **Duplicate receipt behavior is not explicit.** AC12 requires shipment receipt recording, but the specification does not state whether repeated receipt submissions must be prevented from updating inventory more than once. The architecture includes this as a design safeguard.
5. **The inventory search interaction count should be verified.** AC1 specifies a three-interaction limit. The User Interface is designed to support this, but the team should confirm the exact interaction sequence during implementation and testing.
