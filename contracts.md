# Contracts

This file defines the proposed calling interfaces for the modules in `architecture.md`. The implementation is a skeleton: every module function raises `NotImplementedError`, and every HTTP route currently returns HTTP 501.

## Module functions

| Module | Function signature | Success result | Failure | Spec rule served | Injected values |
|---|---|---|---|---|---|
| Inventory Interface | `get_earth_inventory_view() -> dict` | `{"items": [{"item_id": str, "name": str, "quantity": int, "unit": str}], "last_successful_sync": str \| None}` | `NotImplementedError` in skeleton; proposed HTTP errors are documented under APIs | FR-002, NFR7, NFR8 | None |
| Inventory Manager | `record_supply_use(item_id: str, used_quantity: int, user_id: str, now: datetime, update_id: str) -> dict` | Updated item plus accepted update record, including quantity, unit, user, time, and update ID | `NotImplementedError`; proposed invalid quantity error: HTTP 400 `{"error":"validation_error","message":str}` | FR-001, NFR2, NFR6, NFR8 | `user_id`, `now`, and `update_id` |
| Station Storage | `save_offline_change(update: dict) -> dict` | `{"item_id": str, "quantity": int, "pending_count": int, "last_successful_sync": str \| None, "update_id": str}` | `NotImplementedError` | FR-003, NFR1, NFR7 | Update payload; persistence adapter is a module dependency |
| Station Storage | `get_sync_status() -> dict` | `{"pending_count": int, "last_successful_sync": str \| None}` | `NotImplementedError` | FR-003, NFR7 | None |
| Station Storage | `get_inventory_item(item_id: str) -> dict` | One local inventory item, including item ID, quantity, and unit | `NotImplementedError` | FR-001, FR-003 | `item_id` |
| Station Storage | `get_update_history(item_id: str) -> dict` | `{"updates": [update_record, ...]}` for the requested item | `NotImplementedError` | FR-001, NFR6 | `item_id` |
| Sync Manager | `sync_pending_updates() -> dict` | `{"accepted_update_ids": [str], "pending_update_ids": [str]}` | `NotImplementedError`; failed transfers remain pending under FR-004 | FR-004, NFR1, NFR3, NFR4 | Ground Storage adapter and station storage adapter are module dependencies |
| Sync Manager | `retry_update(update_id: str) -> dict` | `{"update_id": str, "status": "synced" \| "already_accepted"}` | `NotImplementedError` | FR-004, NFR3 | `update_id`; Ground Storage adapter is a module dependency |
| Ground Storage | `get_inventory_snapshot() -> dict` | Earth-side inventory snapshot and latest successful sync time | `NotImplementedError` | FR-002, FR-004 | None |
| User Permissions | `require_authenticated_user(user_id: str) -> dict` | Authenticated user identity | `NotImplementedError`; proposed denial: HTTP 403 `{"error":"forbidden","message":str}` | FR-001, FR-004, NFR5 | Authenticated identity supplied by the caller |
| User Permissions | `authorize_conflict_resolution(user_id: str) -> dict` | Authorized reviewer identity | `NotImplementedError`; proposed denial: HTTP 403 `{"error":"forbidden","message":str}` | FR-004, NFR5 | `user_id`; role policy is unresolved in the spec |
| Conflict Review | `resolve_conflict(conflict_id: str, selected_location: str, reason: str, reviewer_id: str, now: datetime) -> dict` | Resolution containing both original locations, selected location, reason, reviewer, and time | `NotImplementedError`; proposed denial: HTTP 403; missing conflict: HTTP 404 | FR-004, NFR4, NFR5, NFR6 | `reviewer_id`, `now`, and selected value |

## REST APIs

All routes currently return HTTP 501 with `{"error":"not_implemented","message":"..."}`. Request fields below are the proposed JSON contract. NFRs are quality constraints on the functional routes, so they do not create artificial NFR-only endpoints.

| Method and route | Request | Public function | Requirement(s) served | Proposed success / failure |
|---|---|---|---|---|
| `POST /inventory/items/{item_id}/usage` | `{"used_quantity": int, "user_id": str, "now": ISO-8601 datetime, "update_id": str}` | `Inventory Manager.record_supply_use` | FR-001; NFR2, NFR6, NFR8 | 200 with updated item and accepted update; 400 for invalid quantity; 403 for unauthorized caller |
| `GET /earth/inventory` | None | `Inventory Interface.get_earth_inventory_view` | FR-002; NFR7, NFR8 | 200 with item quantities/units and last sync time |
| `POST /station/offline/updates` | `{"update": object}` | `Station Storage.save_offline_change` | FR-003; NFR1, NFR7 | 201 with locally saved pending update |
| `GET /station/sync-status` | None | `Station Storage.get_sync_status` | FR-003; NFR7 | 200 with pending count and last successful sync time |
| `GET /station/inventory/items/{item_id}` | None | `Station Storage.get_inventory_item` | FR-001, FR-003 | 200 with the current station-local quantity and unit |
| `GET /station/inventory/items/{item_id}/updates` | None | `Station Storage.get_update_history` | FR-001; NFR6 | 200 with recorded changes for the item |
| `POST /sync` | None | `Sync Manager.sync_pending_updates` | FR-004; NFR1, NFR3, NFR4 | 200 with accepted and still-pending update IDs |
| `POST /sync/updates/{update_id}/retry` | None | `Sync Manager.retry_update` | FR-004; NFR3 | 200 with `synced` or `already_accepted`; duplicate IDs do not apply twice |
| `POST /conflicts/{conflict_id}/resolve` | `{"selected_location": str, "reason": str, "reviewer_id": str, "now": ISO-8601 datetime}` | `Conflict Review.resolve_conflict` | FR-004; NFR4, NFR5, NFR6 | 200 with recorded resolution; 403 for unauthorized reviewer; 404 for unknown conflict |

## Server commands

From the repository root:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The server listens at `http://127.0.0.1:5000`. Example skeleton request:

```bash
curl -i -X POST http://127.0.0.1:5000/inventory/items/water/usage \
  -H 'Content-Type: application/json' \
  -d '{"used_quantity":3,"user_id":"crew-1","now":"2026-11-09T10:00:00Z","update_id":"U102"}'
```
