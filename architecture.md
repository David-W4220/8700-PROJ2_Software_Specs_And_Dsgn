# Architecture Description

## 1. Overview
Our system includes separate modules for managing inventory, mission and shipment, resupply planning, access control, auditing, data storage and synchronization. The space station side uses persistent local storage so that its inventory crew can view or update inventory during communication downtime. When communication is restored, the Synchronization module will transfer pending updates to the Earth-side system when communication is restored. Ground Mission Control will be able to view synchronized updates for inventory and operational information.

The Earth-side system is considered to be an external system as its implementation remains undefined in this spec.

## 2. Modules
| Module | Responsibility | May Depend On |
|---|---|---|
| User Interface | Provides role-specific views for Station Inventory Crew, Logistics Planner and Ground Mission Control. Allows users to view inventory records and synchronization status, review conflicts, and manage resupply and mission information. The inventory lookup interface should allow users to find an item within three interactions (By FR1, FR7, FR10, FR11; AC1, AC10, AC13, AC15 and NFR6). | Authentication and Authorization, Inventory Management, Resupply Planning, Mission and Shipment Management, Synchronization, Earth-side system (external) |
| Authentication and Authorization | Authenticates users and verifies their operations, including inventory updates, manifest approval, dispatch, receipt, and conflict resolution, against their assigned roles (By FR12, AC16). | Local Data Storage |
| Inventory Management | Maintains inventory records, handle item lookup, and saves valid quantity changes. Also identifies items below their minimum stock levels and displays low stock warnings and displays inventory update history for crew handovers (By AC1-5, AC10, NFR5, FR1-5, FR7). | Authentication and Authorization, Local Data Storage, Audit Logging |
| Resupply Planning | Identifies items below their minimum stock level and calculates cargo weight and volume. Rejects plans exceeding capacity or lacking required cargo measurements (By FR4-5, AC2, AC6-8). | Authentication and Authorization, Inventory Management, Local Data Storage |
| Mission and Shipment Management | Manages cargo manifests and controls mission statuses, submissions and approvals. Compares planned and actual loaded cargo. Tracks shipment status, estimated arrival time and shipment history. Records actual received quantities and any shortages or damage. (By FR5-6, FR8-9, AC6, AC9, AC11-12). It verifies Resupply Plans and blocks illegal mission submission. | Authentication and Authorization, Inventory Management, Resupply Planning, Local Data Storage, Audit Logging |
| Audit Logging | Records user operations, including operator, timestamp, affected item and change details. For conflict resolution between Earth and Station, it also records both versions of value, the slected value and the reviewer. (By FR12, AC15, AC17) | Local Data Storage |
| Local Data Storage | Persistently stores station-side inventory, user, audit, mission and manifest records, as well as update history and pending synchronization updates. Records are encrypted when stored. (By 	FR2-3, FR10-12, AC5, AC13-15, AC17, NFR1-2, NFR4) | None |
| Synchronization | Sends pending inventory updates to Earth using unique update IDs. The Earth-side system checks against previously processed IDs to prevent duplicate updates. This module also identifies conflicting changes and maintains the last successful synchronization time. Data transmitted between the station and Earth is encrypted mid-transit (AC10, AC13-15, NFR2-4, FR7, FR11). | Local Data Storage, Audit Logging, Earth-side system (external) |

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
6. As the shipment progresses, Mission and Shipment Management updates its status, estimated arrival time and shipment history.
8. When a shipment arrives, Mission and Shipment Management records the actual received quantities and any shortage or damage. Inventory Management updates inventory using the quantities actually received.

## 4. Design Decisions

| Decision | Reason |
|---|---|
| Use a modular application instead of separate microservices. | **Preference:** As a course project, a modular application is simpler to develop and maintain. The requirements don't actually require independently deployed services. |
| Use persistent station-side storage for inventory records and pending updates. | FR10, FR11, AC13, NFR1, and NFR2 require inventory operations to continue during communication outages and updates to survive application restarts. |
| Save inventory changes locally before reporting success. | FR2, FR10 and AC13 require valid updates to be saved and invalid quantity changes to be rejected. Saving the related records together prevents a partially saved update. |
| Assign each inventory update a unique ID and retain it until acknowledged. | FR11 and AC14 require synchronization retries without applying the same update more than once. The Earth-side system must also recognize previously processed IDs. |
| Retain conflicting versions and require authorized review instead of automatic overwriting. | FR11 and AC15 require conflicting updates to be reviewed rather than silently overwritten. |
| Enforce permissions within the application before protected operations are performed. | FR12, NFR4 and AC16 require unauthorized operations to be rejected. Hiding options in the User Interface alone would not enforce this requirement. |
| Record the user, timestamp, operation, affected record, and relevant change details. | FR12, AC15 and AC17 require accepted changes to have an audit trail. Conflict resolutions also need to record the reviewer and selected value. |
| Use station-side inventory records for inventory searches and index commonly searched fields. | FR1, AC1, and NFR5 require inventory searches to work locally and meet the specified performance target. |
| Require successful capacity validation before mission submission. | FR5, FR6, and AC6-9 require cargo limits and measurements to be checked and manifest changes to go through the required submission and approval process. |
| Encrypt stored records and data transmitted between the station and Earth. | NFR4 requires records to be encrypted at rest and communications to be encrypted in transit. The Earth-side system must provide encryption for its own stored records. |
| Prevent the same shipment receipt from being applied more than once. | This is a design safeguard that helps prevent duplicate receipt submissions from adding the same quantity to inventory twice. AC12 requires accurate receipt recording, although the spec does not explicitly define duplicate-receipt behavior. |

## 5. Constraints and Known Limits
- The spec didn't specify any specific programming languages, frameworks, databases, hosting providers or authentication libraries. These choices will depend on the implementation environment.
- The internal implementation and interface details of the Earth-side system is not yet specified, so only the station has persistent storage and role-specific access. The Earth side system is treated as an external integration endpoint, and the deployment and hosting arrangements for Ground Mission Control users are also undefined.
- Although it's guaranteed for viewing and editing locally stored inventory during communication downtime, the handling of offline creation or approval of manifests and other mission operations is undefined.
- Current architecture doesn't consider automatic conflict merging, so synchronization conflicts require manual review.
- The search performance requirement proposed in NFR5 requires testing to verify.
- Timestamps are initially recorded using the station's system clock and retained during synchronization, but the detailed clock synchronization protocol is undefined.
- Current design scope is only for a single station. Multiple stations would require additional synchronization and conflict-handling architectures.

## 6. Out of Scope
- Payroll management, taxes and general accounting.
- Life-support equipment management and control.
- Spacecraft control.

## 7. Spec Issues
1. **Role permissions are not fully defined.** FR12 and AC16 requires role-based access, but the spec didn't map roles to operations, making it uncertain what roles has permission to approve manifests, dispatch missions, receive shipments, or resolve synchronization conflicts. 
2. **The Earth-side interface wasn't specified.** FR7 and FR11 involves Ground Mission Control to access synchronized information and exchange updates between the Station and Earth, but the spec didn't define the interface or data exchange format.
3. **Conflict handling has no clear protocol.** FR11 and AC15 imply that conflicting updates must be identified and reviewed, but the spec didn't define what record or version information is used as benchmark to determine that two updates are conflicting.
4. **Duplicate receipt handling is undefined.** AC12 requires recording shipment receipt, but the spec didn't state whether repeated receipt submissions must be prevented to prevent repetitive inventory updates.
