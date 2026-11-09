# Contracts — David Wang

## 1. Overview

This document defines the public interfaces for the eight modules in `architecture.md` and the REST APIs exposed by the User Interface module.

- **Language/framework:** Python 3.11+ / FastAPI
- **Testing framework:** pytest
- **Request/response format:** JSON

All business-operation functions are interface stubs during this milestone. Their bodies raise `NotImplementedError`. Each REST route catches this exception and returns HTTP 501.

## 2. Shared Data Structures

These structures describe the data exchanged between modules. They use the objects defined in the Domain Model of `spec.md`.

| Structure | Main fields |
|---|---|
| User | `user_id`, `role` |
| InventoryItem | `item_id`, `name`, `unit`, `quantity`, `condition`, `location`, `expiration_date`, `unit_weight`, `unit_volume`, `minimum_stock`, `importance` |
| InventoryUpdate | `update_id`, `item_id`, `change_details`, `user_id`, `timestamp`, `sync_status` |
| CargoLine | `item_id`, `quantity` |
| ResupplyMission | `mission_id`, `status`, `weight_limit`, `volume_limit`, `expected_arrival`, `status_history` |
| CargoManifest | `mission_id`, `version`, `status`, `cargo_lines` |
| ManifestLine | `item_id`, `planned_quantity`, `loaded_quantity`, `received_quantity` |
| AuditRecord | `user_id`, `action`, `entity_id`, `previous_values`, `new_values`, `timestamp`, `reviewer_id`, `reason` |

For Python interfaces, these structures are represented using `dict[str, Any]` and lists of dictionaries. API request bodies use typed request models.

### API Request Models

| Model | Fields |
|---|---|
| QuantityRequest | `quantity: float` |
| UsageRequest | `quantity_used: float` |
| CargoLineRequest | `item_id: str`, `quantity: float` |
| CargoLinesRequest | `cargo_lines: list[CargoLineRequest]` |
| LoadingRequest | `item_id: str`, `loaded_quantity: float` |
| ReceiptLineRequest | `item_id: str`, `received_quantity: float`, `damaged_quantity: float \| None` |
| ReceiptRequest | `received_lines: list[ReceiptLineRequest]` |
| ConflictResolutionRequest | `selected_value: Any`, `reason: str` |

Fractional inventory quantities and the handling of damaged quantities remain specification issues. The request models do not establish additional business rules for them.

## 3. Module Interfaces

### 3.1 User Interface

**Responsibility:** Provides role-specific views and exposes the REST API routes listed in Section 4.

The module contains the FastAPI route handlers. Each handler authenticates the request, calls the appropriate module functions, and returns the corresponding JSON response.

It does not implement inventory, mission, permission, audit, storage, or synchronization business rules.

The public route-handler functions and their mappings are specified in Section 4.

**Dependencies:** Authentication and Authorization, Inventory Management, Resupply Planning, Mission and Shipment Management, Synchronization, Audit Logging, and the external Earth-side system where required.

### 3.2 Authentication and Authorization

**Dependency:** Local Data Storage

| Public function | Signature | Success result | Failure | Spec rules served |
|---|---|---|---|---|
| `authenticate` | `authenticate(authorization: str \| None) -> dict[str, Any]` | Returns the authenticated user, including `user_id` and `role`. | Missing or invalid authentication. | FR12, NFR4, AC16 |
| `authorize` | `authorize(user_id: str, action: str) -> None` | Returns normally when the user is authorized for the requested action. | User does not have permission. | FR12, NFR4, AC15–AC16 |

**Injected dependencies:**

- Local Data Storage to retrieve user information.
- The authentication verifier used by the application.
- A permission policy that determines whether a user can perform a particular action.

The exact authentication mechanism and role-to-permission mapping are not specified. The implementation must not assume that every user with the same role automatically has every permission.

### 3.3 Inventory Management

**Dependencies:** Authentication and Authorization, Local Data Storage, Audit Logging.

| Public function | Signature | Success result | Failure | Spec rules served |
|---|---|---|---|---|
| `find_item` | `find_item(item_id: str) -> dict[str, Any]` | Returns the item and its current quantity, unit, location, and condition. | Item not found. | FR1, AC1 |
| `set_quantity` | `set_quantity(item_id: str, quantity: float, user_id: str) -> dict[str, Any]` | Returns the updated item and accepted update record. | Item not found or invalid negative quantity. | FR2, FR3, FR12, AC4, AC5, AC17 |
| `record_usage` | `record_usage(item_id: str, quantity_used: float, user_id: str) -> dict[str, Any]` | Returns the updated item, accepted update record, and low-stock status. | Item not found, negative usage, or usage above available usable quantity. | FR2, FR3, FR4, FR12, AC2–AC5, AC13, AC17 |
| `get_update_history` | `get_update_history(item_id: str \| None = None, limit: int = 20) -> list[dict[str, Any]]` | Returns recent updates for an item, or across inventory if `item_id` is omitted. | Storage failure. | FR3, FR7, AC5, AC10 |
| `list_inventory` | `list_inventory() -> list[dict[str, Any]]` | Returns current inventory records. | Storage failure. | FR7, AC10 |
| `add_received_quantity` | `add_received_quantity(item_id: str, received_quantity: float, user_id: str) -> dict[str, Any]` | Returns the updated inventory item after recording received quantity. | Item not found or invalid quantity. | FR9, FR12, AC12 |

**Injected dependencies:**

- Authentication and Authorization for protected inventory changes.
- Local Data Storage for retrieving and saving inventory and update records.
- Audit Logging for creating audit records.
- A clock for generating timestamps.
- An ID generator for assigning unique update IDs.

An accepted inventory change must save the updated item, update history, audit information, and pending synchronization record locally before reporting success. These related records should be saved together.

### 3.4 Resupply Planning

**Dependencies:** Authentication and Authorization, Inventory Management, Local Data Storage.

| Public function | Signature | Success result | Failure | Spec rules served |
|---|---|---|---|---|
| `get_resupply_needs` | `get_resupply_needs() -> list[dict[str, Any]]` | Returns items below their minimum usable stock levels, including their importance. | Storage failure. | FR4, AC2 |
| `check_capacity` | `check_capacity(mission_id: str, cargo_lines: list[dict[str, Any]]) -> dict[str, Any]` | Returns total cargo weight, total volume, and whether each capacity limit is satisfied. | Mission or item not found, or invalid request data. | FR5, AC6–AC8 |

Each `cargo_lines` entry contains `item_id` and `quantity`.

The capacity-check result should include:

- `total_weight`
- `total_volume`
- `within_weight_capacity`
- `within_volume_capacity`
- `can_submit`
- `errors`

An over-capacity result is returned as a capacity-check result. The actual submission operation must reject a mission that exceeds either capacity.

**Injected dependencies:**

- Inventory Management for item details and unit measurements.
- Local Data Storage for mission capacity information.
- Authentication and Authorization for protected operations.

### 3.5 Mission and Shipment Management

**Dependencies:** Authentication and Authorization, Inventory Management, Resupply Planning, Local Data Storage, Audit Logging.

| Public function | Signature | Success result | Failure | Spec rules served |
|---|---|---|---|---|
| `create_manifest` | `create_manifest(mission_id: str, cargo_lines: list[dict[str, Any]], user_id: str) -> dict[str, Any]` | Returns the created manifest and its version. | Mission not found or invalid mission state. | FR6 |
| `update_manifest` | `update_manifest(mission_id: str, cargo_lines: list[dict[str, Any]], user_id: str) -> dict[str, Any]` | Returns the updated manifest and mission status. | Mission not found or invalid mission state. | FR6, AC9 |
| `submit_manifest` | `submit_manifest(mission_id: str, user_id: str) -> dict[str, Any]` | Returns the submitted mission and status. | Mission not found, missing measurement, capacity exceeded, or invalid mission state. | FR5, FR6, AC6–AC9 |
| `approve_mission` | `approve_mission(mission_id: str, user_id: str) -> dict[str, Any]` | Returns the approved mission. | Mission not found or invalid mission state. | FR6, FR12, AC9, AC16 |
| `confirm_dispatch` | `confirm_dispatch(mission_id: str, user_id: str) -> dict[str, Any]` | Returns the dispatched mission. | Mission not found or invalid mission state. | FR6, FR12, AC9 |
| `record_loading` | `record_loading(mission_id: str, item_id: str, loaded_quantity: float, user_id: str) -> dict[str, Any]` | Returns planned quantity, loaded quantity, and their difference. | Mission or item not found, or invalid mission state. | FR8, AC11 |
| `get_mission` | `get_mission(mission_id: str) -> dict[str, Any]` | Returns mission status, expected arrival, manifest information, and status history. | Mission not found. | FR9 |
| `record_shipment_receipt` | `record_shipment_receipt(mission_id: str, received_lines: list[dict[str, Any]], user_id: str) -> dict[str, Any]` | Returns receipt information, shortages, damages, updated inventory information, and mission status. | Mission or item not found, or invalid mission state. | FR9, FR12, AC12 |

Each `cargo_lines` entry contains `item_id` and `quantity`.

Each `received_lines` entry contains `item_id` and `received_quantity`. An optional `damaged_quantity` field may be recorded when cargo damage is reported.

The specification does not yet define whether damaged quantities should be included in usable inventory or stored separately. This must be clarified before that behavior is implemented.

The manifest functions operate on an existing mission. Creating a new resupply mission is not currently covered by a functional requirement.

**Injected dependencies:**

- Authentication and Authorization for protected mission operations.
- Inventory Management for inventory updates when cargo is received.
- Resupply Planning for capacity validation before submission.
- Local Data Storage for mission and manifest records.
- Audit Logging for accepted mission and shipment operations.
- A clock for timestamps where required.

### 3.6 Audit Logging

**Dependency:** Local Data Storage

| Public function | Signature | Success result | Failure | Spec rules served |
|---|---|---|---|---|
| `record_event` | `record_event(user_id: str, action: str, entity_type: str, entity_id: str, previous_values: dict[str, Any] \| None, new_values: dict[str, Any], reviewer_id: str \| None = None, reason: str \| None = None) -> dict[str, Any]` | Returns a timestamped audit record for persistence. | Storage failure. | FR2, FR12, AC15, AC17 |
| `list_records` | `list_records(entity_id: str \| None = None, limit: int = 100) -> list[dict[str, Any]]` | Returns audit records, optionally filtered by entity. | Storage failure. | FR12, AC17 |

**Injected dependencies:**

- Local Data Storage for persistent audit records.
- A clock for generating timestamps.

Conflict resolution must record both competing values, the selected value, the reviewer, timestamp, and reason. The specification does not clearly establish whether ordinary inventory updates also require a reason.

### 3.7 Local Data Storage

**Dependencies:** None.

This module provides persistent access to station-side inventory, user, mission, manifest, audit, and synchronization records.

| Public function | Signature | Success result | Failure | Spec rules served |
|---|---|---|---|---|
| `get_user` | `get_user(user_id: str) -> dict[str, Any]` | Returns a user record. | User not found. | FR12, NFR4 |
| `get_inventory_item` | `get_inventory_item(item_id: str) -> dict[str, Any]` | Returns an inventory item. | Item not found. | FR1, FR2 |
| `list_inventory_items` | `list_inventory_items() -> list[dict[str, Any]]` | Returns stored inventory items. | Storage failure. | FR4, FR7 |
| `save_inventory_item` | `save_inventory_item(item: dict[str, Any]) -> dict[str, Any]` | Returns the saved inventory item. | Invalid record or storage failure. | FR2, FR9, FR10 |
| `save_inventory_update` | `save_inventory_update(update: dict[str, Any]) -> dict[str, Any]` | Returns the saved update record. | Duplicate update ID or storage failure. | FR2, FR10, FR11 |
| `get_inventory_update` | `get_inventory_update(update_id: str) -> dict[str, Any]` | Returns an inventory update by ID. | Update not found. | FR11, AC14 |
| `list_inventory_updates` | `list_inventory_updates(item_id: str \| None = None, limit: int = 20) -> list[dict[str, Any]]` | Returns stored update history. | Storage failure. | FR3, FR7 |
| `list_pending_updates` | `list_pending_updates() -> list[dict[str, Any]]` | Returns updates awaiting synchronization. | Storage failure. | FR10, FR11 |
| `mark_update_acknowledged` | `mark_update_acknowledged(update_id: str, acknowledged_at: datetime) -> None` | Marks the update as acknowledged. | Update not found or storage failure. | FR11, NFR2, AC14 |
| `get_last_successful_sync_time` | `get_last_successful_sync_time() -> datetime \| None` | Returns the latest successful synchronization time, or `None` if no successful synchronization has occurred. | Storage failure. | FR7, FR10, AC10, AC13 |
| `get_mission` | `get_mission(mission_id: str) -> dict[str, Any]` | Returns a stored mission. | Mission not found. | FR6, FR9 |
| `save_mission` | `save_mission(mission: dict[str, Any]) -> dict[str, Any]` | Returns the saved mission. | Invalid mission or storage failure. | FR6, FR8, FR9 |
| `get_manifest` | `get_manifest(mission_id: str) -> dict[str, Any]` | Returns the mission manifest. | Manifest not found. | FR6 |
| `save_manifest` | `save_manifest(manifest: dict[str, Any]) -> dict[str, Any]` | Returns the saved manifest. | Invalid manifest or storage failure. | FR6 |
| `save_audit_record` | `save_audit_record(record: dict[str, Any]) -> dict[str, Any]` | Returns the saved audit record. | Storage failure. | FR12 |
| `list_audit_records` | `list_audit_records(entity_id: str \| None = None, limit: int = 100) -> list[dict[str, Any]]` | Returns stored audit records. | Storage failure. | FR12, AC17 |
| `save_sync_conflict` | `save_sync_conflict(conflict: dict[str, Any]) -> dict[str, Any]` | Saves a conflict record containing both competing values. | Storage failure. | FR11, AC15 |
| `list_sync_conflicts` | `list_sync_conflicts() -> list[dict[str, Any]]` | Returns unresolved synchronization conflicts. | Storage failure. | FR11, AC15 |

The storage module must preserve locally saved updates after application restarts. Pending updates must not be deleted until Earth acknowledges them.

A single accepted inventory change should persist its item, update, and audit information together. The transaction handling is internal to Local Data Storage and does not require another architecture module.

### 3.8 Synchronization

**Dependencies:** Local Data Storage, Audit Logging, external Earth-side system.

| Public function | Signature | Success result | Failure | Spec rules served |
|---|---|---|---|---|
| `get_status` | `get_status() -> dict[str, Any]` | Returns pending update count and last successful synchronization time. | Storage failure. | FR7, FR10, AC10, AC13 |
| `synchronize_pending_updates` | `synchronize_pending_updates() -> dict[str, Any]` | Returns acknowledged, failed, and conflicting updates. | Earth-side communication failure; failed updates remain pending. | FR11, NFR3, AC14, AC15 |
| `list_conflicts` | `list_conflicts() -> list[dict[str, Any]]` | Returns conflicts requiring review. | Storage failure. | FR11, AC15 |
| `resolve_conflict` | `resolve_conflict(conflict_id: str, selected_value: Any, reviewer_id: str, reason: str) -> dict[str, Any]` | Returns the resolved conflict and selected value. | Conflict not found, invalid resolution, or unauthorized operation. | FR11, FR12, AC15 |

**Injected dependencies:**

- Local Data Storage for pending updates, acknowledgements, conflicts, and synchronization timestamps.
- Audit Logging for conflict-resolution records.
- The external Earth-side system for sending updates and receiving acknowledgements.
- A clock and scheduler for synchronization timing.

The Earth-side system remains external. Its implementation and exact API are not part of this skeleton. The conflict detection and comparison rules remain to be defined.

## 4. REST API Contracts

The following REST APIs are exposed through the User Interface module.

All routes require an `Authorization` header. Authenticated user identity is obtained from the authorization context, not trusted from request-body `user_id` fields.

Protected write operations must also pass the corresponding authorization check.

| Requirement | Method and route | Request body / parameters | Public function mapping |
|---|---|---|---|
| FR1 | `GET /inventory/{item_id}` | Path: `item_id` | `InventoryManagement.find_item` |
| FR2 | `PATCH /inventory/{item_id}/quantity` | `{"quantity": 9}` | `InventoryManagement.set_quantity` |
| FR2 | `POST /inventory/{item_id}/usage` | `{"quantity_used": 3}` | `InventoryManagement.record_usage` |
| FR3 | `GET /inventory/{item_id}/updates` | Query: `limit` | `InventoryManagement.get_update_history` |
| FR4 | `GET /resupply/needs` | None | `ResupplyPlanning.get_resupply_needs` |
| FR5 | `POST /missions/{mission_id}/capacity-check` | `{"cargo_lines": [{"item_id": "WTR-001", "quantity": 10}]}` | `ResupplyPlanning.check_capacity` |
| FR6 | `POST /missions/{mission_id}/manifest` | `{"cargo_lines": [{"item_id": "WTR-001", "quantity": 10}]}` | `MissionShipmentManagement.create_manifest` |
| FR6 | `PATCH /missions/{mission_id}/manifest` | `{"cargo_lines": [{"item_id": "WTR-001", "quantity": 12}]}` | `MissionShipmentManagement.update_manifest` |
| FR6 | `POST /missions/{mission_id}/submit` | None | `MissionShipmentManagement.submit_manifest` |
| FR12 | `POST /missions/{mission_id}/approval` | None | `MissionShipmentManagement.approve_mission` |
| FR12 | `POST /missions/{mission_id}/dispatch` | None | `MissionShipmentManagement.confirm_dispatch` |
| FR7 | `GET /ground/inventory` | None | `InventoryManagement.list_inventory`, `InventoryManagement.get_update_history`, `Synchronization.get_status` |
| FR8 | `POST /missions/{mission_id}/loading` | `{"item_id": "WTR-001", "loaded_quantity": 18}` | `MissionShipmentManagement.record_loading` |
| FR9 | `GET /missions/{mission_id}` | Path: `mission_id` | `MissionShipmentManagement.get_mission` |
| FR9 | `POST /missions/{mission_id}/receipt` | `{"received_lines": [{"item_id": "WTR-001", "received_quantity": 18}]}` | `MissionShipmentManagement.record_shipment_receipt` |
| FR10 | `GET /sync/status` | None | `Synchronization.get_status` |
| FR11 | `POST /sync` | None | `Synchronization.synchronize_pending_updates` |
| FR11 | `GET /sync/conflicts` | None | `Synchronization.list_conflicts` |
| FR11, FR12 | `POST /sync/conflicts/{conflict_id}/resolution` | `{"selected_value": "Store B", "reason": "Physical inventory confirms Store B"}` | `Synchronization.resolve_conflict` |
| FR12 | `GET /audit/records` | Optional query: `entity_id`, `limit` | `AuditLogging.list_records` |

### API Response Fields

The following response structures are proposed so that the API results can be tested consistently.

| Endpoint | Successful response fields |
|---|---|
| `GET /inventory/{item_id}` | `item` |
| `PATCH /inventory/{item_id}/quantity` | `item`, `update` |
| `POST /inventory/{item_id}/usage` | `item`, `update`, `low_stock` |
| `GET /inventory/{item_id}/updates` | `updates` |
| `GET /resupply/needs` | `items` |
| `POST /missions/{mission_id}/capacity-check` | `mission_id`, `total_weight`, `total_volume`, `within_weight_capacity`, `within_volume_capacity`, `can_submit`, `errors` |
| Manifest creation and update | `manifest`, `mission_status` |
| Mission submission, approval, and dispatch | `mission` |
| `GET /ground/inventory` | `inventory`, `recent_updates`, `sync_status` |
| `POST /missions/{mission_id}/loading` | `mission_id`, `item_id`, `planned_quantity`, `loaded_quantity`, `difference` |
| `GET /missions/{mission_id}` | `mission` |
| `POST /missions/{mission_id}/receipt` | `mission`, `received_lines`, `shortages`, `damages` |
| `GET /sync/status` | `pending_update_count`, `last_successful_sync_time` |
| `POST /sync` | `acknowledged`, `failed`, `conflicts`, `pending_update_count`, `last_successful_sync_time` |
| `GET /sync/conflicts` | `conflicts` |
| Conflict resolution | `conflict`, `audit_record` |
| `GET /audit/records` | `records` |

### REST API Notes

1. FR10 does not need a separate endpoint for creating an offline inventory change. The existing quantity and usage endpoints perform the local inventory operation. The station stores the update locally, and `GET /sync/status` exposes the pending count and last successful synchronization time.

2. FR7's Ground Mission Control view combines inventory records, recent updates, and synchronization status from the corresponding public functions.

3. FR12 is partly cross-cutting. Authorization checks apply to inventory changes, manifest submission, approval, dispatch, cargo receipt, and conflict resolution. `GET /audit/records` provides access to audit information.

4. FR5 validation must also be enforced when submitting a manifest. Calling the capacity-check endpoint alone must not be the only protection against over-capacity submission.

5. The REST APIs do not create a new Earth-side module. Synchronization communicates with the external Earth-side system through the dependency listed in the Synchronization module.

6. NFR1–NFR6 are quality requirements and do not each require a separate REST endpoint.

7. The manifest routes assume that the corresponding Draft mission already exists. Creating a new mission is not currently defined by a functional requirement.

8. Updating item location, condition, or missing-item status is mentioned in the Domain Model and actor descriptions, but there are no corresponding functional requirements or REST routes in the current specification. These operations are not added here.

## 5. HTTP Response Contracts

The following HTTP status codes are proposed API conventions. The original specification does not prescribe HTTP status codes.

| Situation | HTTP status | Error code |
|---|---:|---|
| Successful read or write | 200 | None |
| Missing or invalid authentication | 401 | `unauthenticated` |
| User lacks required permission | 403 | `permission_denied` |
| Requested item, mission, or conflict does not exist | 404 | `not_found` |
| Operation is not allowed in the current mission state | 409 | `invalid_mission_state` |
| Negative quantity or usage above available quantity | 422 | `invalid_quantity` |
| Cargo exceeds capacity | 422 | `capacity_exceeded` |
| Required unit weight is missing | 422 | `missing_unit_weight` |
| Required unit volume is missing | 422 | `missing_unit_volume` |
| Earth-side communication is unavailable | 503 | `earth_unavailable` |
| Operation has not been implemented in this milestone | 501 | `not_implemented` |

A normal API error response uses this structure:

```json
{
  "error": "invalid_quantity",
  "message": "The requested quantity is not valid."
}
```

### Required Skeleton Response

Every unfinished REST route must return HTTP 501 with this exact response structure:

```json
{
  "error": "not_implemented",
  "message": "This endpoint is not implemented yet."
}
```

The server and routes must be runnable, but no business logic is implemented in this milestone.

## 6. Requirement Coverage

| Requirement | REST API entry point |
|---|---|
| FR1 | `GET /inventory/{item_id}` |
| FR2 | `PATCH /inventory/{item_id}/quantity`; `POST /inventory/{item_id}/usage` |
| FR3 | `GET /inventory/{item_id}/updates` |
| FR4 | `GET /resupply/needs` |
| FR5 | `POST /missions/{mission_id}/capacity-check`; capacity validation during manifest submission |
| FR6 | Manifest creation, update, and submission routes |
| FR7 | `GET /ground/inventory` |
| FR8 | `POST /missions/{mission_id}/loading` |
| FR9 | `GET /missions/{mission_id}`; `POST /missions/{mission_id}/receipt` |
| FR10 | Local behavior of inventory update routes; `GET /sync/status` |
| FR11 | `POST /sync`; conflict listing and resolution routes |
| FR12 | Authorization checks on protected routes; `GET /audit/records` |

All eight architecture modules have public interfaces or route handlers. The API and module mappings above provide entry points for the functional requirements.

## 7. Dependencies and Implementation Limits

- Python 3.11 or later.
- FastAPI for REST routes.
- Uvicorn to start the server.
- pytest and FastAPI TestClient for automated API tests.
- Persistent database technology is not selected in this milestone.
- The Earth-side system is external and is not implemented as another application module.
- Authentication details and role-permission mapping remain open.
- Conflict identification rules and damaged-cargo inventory treatment remain open.
- Fractional quantity rules and concurrent inventory update behavior remain open.
- Business logic is not implemented in this milestone.
