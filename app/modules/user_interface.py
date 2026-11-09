#FastAPI REST routes for the app, defines interfaces for synchronization, 
#status reporting, conflict resolution.

from typing import Any, Callable

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.modules.authentication_authorization import authenticate, authorize
from app.modules.audit_logging import list_records
from app.modules.inventory_management import (find_item, get_update_history, list_inventory, record_usage, set_quantity, )
from app.modules.mission_shipment_management import (approve_mission, confirm_dispatch, create_manifest, get_mission,
    record_loading, record_shipment_receipt, submit_manifest, update_manifest,)
from app.modules.resupply_planning import check_capacity, get_resupply_needs
from app.modules.synchronization import (get_status, list_conflicts, resolve_conflict, synchronize_pending_updates,)

router = APIRouter()

# Request models define the JSON body.
class QuantityRequest(BaseModel):
    quantity: float

class UsageRequest(BaseModel):
    quantity_used: float

class CargoLinesRequest(BaseModel):
    cargo_lines: list[dict[str, Any]]

class LoadingRequest(BaseModel):
    item_id: str
    loaded_quantity: float

class ReceiptLineRequest(BaseModel):
    item_id: str
    received_quantity: float
    damaged_quantity: float | None = None


class ReceiptRequest(BaseModel):
    received_lines: list[ReceiptLineRequest]


class ConflictResolutionRequest(BaseModel):
    selected_value: Any
    reason: str

def _not_implemented_response() -> JSONResponse:
    #Return the required temporary HTTP 501 response
    return JSONResponse(status_code=501,
        content={
            "error": "not_implemented",
            "message": "This endpoint is not implemented yet.",
        },
    )


def _execute(authorization: str | None, action: str, operation: Callable[..., Any],
    *args: Any, identity_parameter: str | None = None, **kwargs: Any,) -> Any:
    #Call the authentication and authorization interfaces, then the
    #mapped module function. Unimplemented operations return HTTP 501.
    
    try:
        user = authenticate(authorization)
        user_id = user["user_id"]

        authorize(user_id, action)

        # Inject the authenticated identity into operations that need it.
        if identity_parameter is not None:
            kwargs[identity_parameter] = user_id

        return operation(*args, **kwargs)

    except NotImplementedError:
        # Expected behavior during the initial skeleton milestone.
        return _not_implemented_response()


def _ground_inventory_view() -> dict[str, Any]:
    #Combine inventory, recent updates, and synchronization status
    return {
        "inventory": list_inventory(),
        "recent_updates": get_update_history(),
        "sync_status": get_status(),
    }


# FR1: Find an inventory item.
@router.get("/inventory/{item_id}")
def get_inventory_item(item_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),):
      
    return _execute(authorization, "view_inventory", find_item, item_id)


# FR2: Set an item's quantity.
@router.patch("/inventory/{item_id}/quantity")
def update_inventory_quantity(item_id: str, request: QuantityRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),):
      
    return _execute(authorization, "update_inventory", set_quantity, item_id, request.quantity,
        identity_parameter="user_id",)


# FR2: Record item usage.
@router.post("/inventory/{item_id}/usage")
def record_inventory_usage(item_id: str, request: UsageRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),):
      
    return _execute(authorization, "update_inventory", record_usage, 
        item_id, request.quantity_used, identity_parameter="user_id",)


# FR3: Retrieve recent inventory updates.
@router.get("/inventory/{item_id}/updates")
def get_inventory_updates(item_id: str, limit: int = 20,
    authorization: str | None = Header(default=None, alias="Authorization"),):
  
    return _execute(authorization, "view_inventory", get_update_history, item_id, limit,)


# FR4: Identify items requiring resupply.
@router.get("/resupply/needs")
def get_resupply_needs_route(authorization: str | None = Header(default=None, alias="Authorization"),):
  
    return _execute(authorization, "view_resupply_needs", get_resupply_needs)

# FR5: Check cargo weight and volume.
@router.post("/missions/{mission_id}/capacity-check")
def check_mission_capacity(mission_id: str, request: CargoLinesRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),):
      
    return _execute(authorization, "plan_resupply", check_capacity, mission_id, request.cargo_lines,)


# FR6: Create a cargo manifest.
@router.post("/missions/{mission_id}/manifest")
def create_mission_manifest(mission_id: str, request: CargoLinesRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),):
      
    return _execute(authorization, "manage_manifest", create_manifest, mission_id, 
        request.cargo_lines, identity_parameter="user_id",)


# FR6: Update a cargo manifest.
@router.patch("/missions/{mission_id}/manifest")
def update_mission_manifest(mission_id: str, request: CargoLinesRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),):
      
    return _execute(authorization, "manage_manifest", update_manifest, mission_id,
        request.cargo_lines, identity_parameter="user_id",)
      

# FR6: Submit a cargo manifest.
@router.post("/missions/{mission_id}/submit")
def submit_mission_manifest(mission_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),):
      
    return _execute(authorization, "submit_manifest", submit_manifest, mission_id,
        identity_parameter="user_id",)


# FR12: Approve a mission.
@router.post("/missions/{mission_id}/approval")
def approve_resupply_mission(mission_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),):
      
    return _execute(authorization, "approve_mission", approve_mission, mission_id,
        identity_parameter="user_id",)


# FR12: Confirm mission dispatch.
@router.post("/missions/{mission_id}/dispatch")
def dispatch_resupply_mission(mission_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),):
  
    return _execute(authorization, "confirm_dispatch", confirm_dispatch,
        mission_id, identity_parameter="user_id", )


# FR7: Provide Ground Mission Control with inventory and sync information.
@router.get("/ground/inventory")
def get_ground_inventory(authorization: str | None = Header(default=None, alias="Authorization"),):
  
    return _execute(authorization, "view_inventory", _ground_inventory_view)


# FR8: Record loaded cargo and identify differences.
@router.post("/missions/{mission_id}/loading")
def record_mission_loading(mission_id: str, request: LoadingRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),):
      
    return _execute(authorization, "record_loading", record_loading, mission_id,
        request.item_id, request.loaded_quantity, identity_parameter="user_id",)


# FR9: Retrieve shipment information.
@router.get("/missions/{mission_id}")
def get_mission_details(mission_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),):
      
    return _execute(authorization, "view_mission", get_mission, mission_id)


# FR9: Record cargo receipt.
@router.post("/missions/{mission_id}/receipt")
def receive_mission_shipment(mission_id: str, request: ReceiptRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),):
      
    received_lines = [line.model_dump(exclude_none=True) for line in request.received_lines]

    return _execute(authorization, "record_receipt", record_shipment_receipt,
        mission_id, received_lines, identity_parameter="user_id",)


# FR10: Display pending updates and synchronization status.
@router.get("/sync/status")
def get_synchronization_status(authorization: str | None = Header(default=None, alias="Authorization"),):
  
    return _execute(authorization, "view_sync_status", get_status)


# FR11: Synchronize pending inventory updates.
@router.post("/sync")
def synchronize_updates(authorization: str | None = Header(default=None, alias="Authorization"),):
  
    return _execute(authorization, "synchronize_inventory", synchronize_pending_updates,)


# FR11: List synchronization conflicts.
@router.get("/sync/conflicts")
def get_synchronization_conflicts(authorization: str | None = Header(default=None, alias="Authorization"),):
      
    return _execute(authorization, "view_conflicts", list_conflicts)


# FR11/FR12: Resolve a synchronization conflict.
@router.post("/sync/conflicts/{conflict_id}/resolution")
def resolve_synchronization_conflict(conflict_id: str, request: ConflictResolutionRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),):
      
    return _execute(authorization, "resolve_conflict", resolve_conflict, conflict_id,
        request.selected_value, identity_parameter="reviewer_id", reason=request.reason,)


# FR12: Retrieve audit records.
@router.get("/audit/records")
def get_audit_records(entity_id: str | None = None, limit: int = 100,
    authorization: str | None = Header(default=None, alias="Authorization"),):
      
    return _execute(authorization, "view_audit_records", list_records, entity_id, limit,)
