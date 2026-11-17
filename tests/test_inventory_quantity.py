from datetime import datetime

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
        tmp_path / "test_inventory_quantity.db",
    )

    storage.initialize_database()
    storage.seed_demo_data()

    return TestClient(app)


HEADERS = {
    "Authorization": "Bearer crew-01",
}


def test_negative_quantity_is_rejected(client):
    response = client.patch(
        "/inventory/WTR-001/quantity",
        headers=HEADERS,
        json={"quantity": -5},
    )

    assert response.status_code == 422

    # The rejected request must not change the stored quantity.
    item = storage.get_inventory_item("WTR-001")
    assert item["quantity"] == 120.0


def test_zero_quantity_is_accepted(client):
    response = client.patch(
        "/inventory/WTR-001/quantity",
        headers=HEADERS,
        json={"quantity": 0},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["item_id"] == "WTR-001"
    assert data["quantity"] == 0.0

    # Confirm that the new quantity was persisted.
    item = storage.get_inventory_item("WTR-001")
    assert item["quantity"] == 0.0


def test_quantity_update_creates_audit_record(client):
    response = client.patch(
        "/inventory/WTR-001/quantity",
        headers=HEADERS,
        json={"quantity": 90},
    )

    assert response.status_code == 200

    records = storage.list_audit_records("WTR-001")

    assert len(records) == 1

    record = records[0]

    assert record["user_id"] == "crew-01"
    assert record["action"] == "inventory.quantity_updated"
    assert record["entity_id"] == "WTR-001"
    assert record["old_values"]["quantity"] == 120.0
    assert record["new_values"]["quantity"] == 90.0

    # Confirm that the audit timestamp is a valid ISO timestamp.
    datetime.fromisoformat(record["timestamp"])