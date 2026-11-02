
# Architecture Document

## 1. Overview

My part of the system focuses on station inventory and communication with Earth. The system lets crew members record supplies being used and saves those changes on the station. When communication with Earth returns, the changes are sent over so Ground Mission Control can see the updated inventory.

## 2. Modules

| Module | Responsibility | May Depend On |
| --- | --- | --- |
| Inventory Interface | Lets users view inventory and enter changes (FR-001, FR-002) | Inventory Manager, Station Storage, Ground Storage |
| Inventory Manager | Checks and updates item quantities (FR-001) | Station Storage, User Permissions |
| Station Storage | Saves inventory and pending changes locally (FR-003) | None |
| Sync Manager | Sends changes between the station and Earth (FR-004) | Station Storage, Ground Storage |
| Ground Storage | Keeps the inventory information received on Earth (FR-002, FR-004) | None |
| User Permissions | Checks user identity and permissions (FR-001, FR-004) | Station Storage, Ground Storage |
| Conflict Review | Lets authorized users review conflicting changes (FR-004) | User Permissions, Ground Storage |

These are the main parts of the system. They do not all need to be separate programs.

## 3. Request Flow

The main scenario is when a crew member uses supplies while communication with Earth is down.

1. A crew member opens inventory and selects an item.
2. The crew member enters how much of the item was used.
3. The Inventory Manager checks that the amount is valid.
4. If the amount is invalid, the system shows an error and does not change the quantity.
5. If it is valid, the system updates the quantity and saves the change locally with the user's information, time, and a unique update ID.
6. The change stays saved on the station even if the application restarts.
7. The system shows how many updates are waiting to sync.
8. When communication returns, the Sync Manager sends the waiting changes to Earth.
9. Earth checks the update ID so the same change is not applied twice.
10. If Earth and the station changed the same item, both versions are kept for review.
11. An authorized reviewer chooses the correct value and provides a reason.
12. After Earth accepts an update, the station marks it as synced and updates the last successful sync time.

This follows FR-001 through FR-004 and AC-001 through AC-008.

## 4. Design Decisions

| Decision | Reason |
| --- | --- |
| Save inventory locally on the station | Changes must remain saved during communication outages (FR-003). |
| Check quantities before saving | The system cannot allow negative amounts or usage above what is available (FR-001). |
| Give every update a unique ID | This prevents changes from being applied twice during syncing (FR-004). |
| Keep pending changes until Earth confirms them | This prevents updates from being lost if communication fails (AC-006). |
| Save both versions of conflicting changes | The system must allow conflicts to be reviewed instead of replacing one automatically (AC-008). |
| Check permissions before conflict review | Only authorized reviewers should make these decisions (AC-008). |
| Show the last successful sync time | Users need to know how current the inventory information is (FR-002, FR-003). |

## 5. Constraints and Known Limits

The biggest constraint is that communication between the station and Earth might not always be available. Because of this, the station has to save inventory changes locally.

Another issue is that the same update might get sent multiple times if the connection fails during syncing. The system uses unique update IDs to prevent the same change from being applied twice.

The system also needs to keep inventory records accurate and make sure unauthorized users cannot resolve conflicts.

The specification does not require a certain programming language, database, or framework, so I am leaving those choices open for now.

The design does not provide live updates to Earth while communication is down. If the project grows to include multiple stations, the syncing process would probably need to be expanded.

## 6. Out of Scope

This part of the project does not cover payroll, taxes, accounting, spacecraft control, or life support control.

## 7. Spec Issues

One issue is that the specification does not explain exactly how the system determines when two changes conflict.

It also does not clearly identify which user role is responsible for resolving conflicts.

Finally, the specification describes changing inventory quantities but also includes an example where an item's location changes. This may need to be explained more clearly before implementation.
