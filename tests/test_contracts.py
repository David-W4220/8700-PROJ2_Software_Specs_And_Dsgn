#Tests for the FastAPI skeleton to verify route registration 
#and the required HTTP 501 response.

import re, pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

AUTH_HEADERS = {
    "Authorization": "Bearer test-token"
}

EXPECTED_RESPONSE = {
    "error": "not_implemented",
    "message": "This endpoint is not implemented yet."
}


# One test entry for each REST API operation.
API_CASES = [
    pytest.param("GET", "/inventory/WTR-001", None, id="FR1-find-item"),

    pytest.param("PATCH", "/inventory/WTR-001/quantity",
                 {"quantity": 9}, id="FR2-update-quantity"),

    pytest.param("POST", "/inventory/WTR-001/usage",
                 {"quantity_used": 3}, id="FR2-record-usage"),

    pytest.param("GET", "/inventory/WTR-001/updates",
                 None, id="FR3-update-history"),

    pytest.param("GET", "/resupply/needs",
                 None, id="FR4-resupply-needs"),

    pytest.param("POST", "/missions/M-001/capacity-check",
                 {"cargo_lines": [
                     {"item_id": "WTR-001", "quantity": 10}
                 ]}, id="FR5-capacity-check"),

    pytest.param("POST", "/missions/M-001/manifest",
                 {"cargo_lines": [
                     {"item_id": "WTR-001", "quantity": 10}
                 ]}, id="FR6-create-manifest"),

    pytest.param("PATCH", "/missions/M-001/manifest",
                 {"cargo_lines": [
                     {"item_id": "WTR-001", "quantity": 12}
                 ]}, id="FR6-update-manifest"),

    pytest.param("POST", "/missions/M-001/submit",
                 None, id="FR6-submit-manifest"),

    pytest.param("POST", "/missions/M-001/approval",
                 None, id="FR12-approve-mission"),

    pytest.param("POST", "/missions/M-001/dispatch",
                 None, id="FR12-dispatch-mission"),

    pytest.param("GET", "/ground/inventory",
                 None, id="FR7-ground-inventory"),

    pytest.param("POST", "/missions/M-001/loading",
                 {"item_id": "WTR-001", "loaded_quantity": 18},
                 id="FR8-record-loading"),

    pytest.param("GET", "/missions/M-001",
                 None, id="FR9-mission-details"),

    pytest.param("POST", "/missions/M-001/receipt",
                 {"received_lines": [
                     {"item_id": "WTR-001", "received_quantity": 18}
                 ]}, id="FR9-receive-shipment"),

    pytest.param("GET", "/sync/status",
                 None, id="FR10-sync-status"),

    pytest.param("POST", "/sync",
                 None, id="FR11-synchronize"),

    pytest.param("GET", "/sync/conflicts",
                 None, id="FR11-list-conflicts"),

    pytest.param("POST", "/sync/conflicts/C-001/resolution",
                 {
                     "selected_value": "Store B",
                     "reason": "Physical inventory confirms Store B"
                 }, id="FR11-resolve-conflict"),

    pytest.param("GET", "/audit/records?entity_id=WTR-001&limit=10",
                 None, id="FR12-audit-records"),
]


@pytest.mark.parametrize("method,path,body", API_CASES)
def test_api_route_returns_501(method, path, body):
    #Every unfinished API route must return the required 501 response

    request_args = {"headers": AUTH_HEADERS}

    if body is not None:
        request_args["json"] = body

    response = client.request(method, path, **request_args)

    assert response.status_code == 501
    assert response.json() == EXPECTED_RESPONSE


def test_all_expected_api_operations_are_registered():
    #Verify that all documented API operations appear in OpenAPI

    openapi = client.get("/openapi.json").json()

    actual_operations = {
        (method.upper(), path)
        for path, path_item in openapi["paths"].items()
        for method in path_item
        if method.lower() in {"get", "post", "patch", "put", "delete"}
    }

    # Helper to convert concrete test IDs into OpenAPI's parameter template format
    def normalize_path(path: str) -> str:
        path = path.split("?")[0]  # Strip query parameters
        path = re.sub(r'/WTR-\d+', '/{item_id}', path)
        path = re.sub(r'/M-\d+', '/{mission_id}', path)
        path = re.sub(r'/C-\d+', '/{conflict_id}', path)
        return path

    expected_operations = {
        # Normalize concrete test paths to match OpenAPI's parameterized route structure
        (param.values[0], normalize_path(param.values[1]))
        for param in API_CASES
    }

    assert actual_operations == expected_operations
