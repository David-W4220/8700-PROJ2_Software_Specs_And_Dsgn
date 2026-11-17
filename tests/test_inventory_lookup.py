import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules import local_data_storage as storage


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Give each test its own temporary database.
    monkeypatch.setattr(
        storage,
        "DB_PATH",
        tmp_path / "test_inventory_lookup.db",
    )

    storage.initialize_database()
    storage.seed_demo_data()

    return TestClient(app)


HEADERS = {
    "Authorization": "Bearer crew-01",
}


def test_lookup_existing_inventory_item(client):
    response = client.get(
        "/inventory/WTR-001",
        headers=HEADERS,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["item_id"] == "WTR-001"
    assert data["name"] == "Drinking Water"
    assert data["quantity"] == 120.0
    assert data["location"] == "Storage A"


def test_lookup_reads_from_local_storage(client):
    """
    Inventory lookup uses the local database directly.
    It does not require a synchronization or Earth-side API call.
    """
    response = client.get(
        "/inventory/WTR-001",
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["item_id"] == "WTR-001"


def test_lookup_nonexistent_item_returns_404(client):
    response = client.get(
        "/inventory/DOES-NOT-EXIST",
        headers=HEADERS,
    )

    assert response.status_code == 404