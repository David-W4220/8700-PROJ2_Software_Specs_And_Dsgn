"""Acceptance tests for AC-001 through AC-008.

These tests call only the REST endpoints declared in contracts.md. Their
preconditions use the concrete fixture values from test_plan.md. The current
application skeleton returns 501 until the corresponding behavior is built.
"""

import unittest

from app import app


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def assert_all(self, failures):
        self.assertEqual(failures, [], "\n".join(failures))

    def test_AC001_record_supply_use(self):
        response = self.client.post(
            "/inventory/items/water/usage",
            json={
                "used_quantity": 3,
                "user_id": "crew-1",
                "now": "2026-11-09T10:00:00Z",
                "update_id": "U201",
            },
        )
        body = response.get_json() or {}
        failures = []
        if response.status_code != 200:
            failures.append(f"expected HTTP 200, got {response.status_code}")
        if body.get("quantity") != 9:
            failures.append(f"expected quantity 9, got {body.get('quantity')!r}")
        if body.get("unit") != "packs":
            failures.append(f"expected unit 'packs', got {body.get('unit')!r}")
        update = body.get("update", {})
        for key, expected in {
            "user_id": "crew-1",
            "time": "2026-11-09T10:00:00Z",
            "update_id": "U201",
        }.items():
            if update.get(key) != expected:
                failures.append(f"expected update.{key}={expected!r}, got {update.get(key)!r}")
        self.assert_all(failures)

    def test_AC002_reject_overuse_and_accept_limit_control(self):
        before_response = self.client.get("/station/inventory/items/water")
        before_history_response = self.client.get("/station/inventory/items/water/updates")
        before = before_response.get_json() or {}
        before_history = (before_history_response.get_json() or {}).get("updates", [])

        rejected = self.client.post(
            "/inventory/items/water/usage",
            json={"used_quantity": 5, "user_id": "crew-1", "now": "2026-11-09T10:00:00Z", "update_id": "U202"},
        )
        rejected_body = rejected.get_json() or {}
        after_response = self.client.get("/station/inventory/items/water")
        after_history_response = self.client.get("/station/inventory/items/water/updates")
        after = after_response.get_json() or {}
        after_history = (after_history_response.get_json() or {}).get("updates", [])

        control = self.client.post(
            "/inventory/items/water/usage",
            json={"used_quantity": 4, "user_id": "crew-1", "now": "2026-11-09T10:01:00Z", "update_id": "U203"},
        )
        control_body = control.get_json() or {}
        failures = []
        if rejected.status_code != 400:
            failures.append(f"rejection expected HTTP 400, got {rejected.status_code}")
        if rejected_body.get("error") != "validation_error":
            failures.append(f"expected validation_error, got {rejected_body.get('error')!r}")
        if after_response.status_code != 200 or after.get("quantity") != before.get("quantity", 4):
            failures.append("rejected overuse changed the item or item state could not be read")
        if after_history_response.status_code != 200 or after_history != before_history:
            failures.append("rejected overuse created an update record or history could not be read")
        if control.status_code != 200 or control_body.get("quantity") != 0:
            failures.append("same-shape control at the available limit was not accepted with quantity 0")
        self.assert_all(failures)

    def test_AC003_reject_negative_and_accept_zero_control(self):
        before_response = self.client.get("/station/inventory/items/water")
        before_history_response = self.client.get("/station/inventory/items/water/updates")
        before = before_response.get_json() or {}
        before_history = (before_history_response.get_json() or {}).get("updates", [])

        rejected = self.client.post(
            "/inventory/items/water/usage",
            json={"used_quantity": -1, "user_id": "crew-1", "now": "2026-11-09T10:00:00Z", "update_id": "U204"},
        )
        rejected_body = rejected.get_json() or {}
        after_response = self.client.get("/station/inventory/items/water")
        after_history_response = self.client.get("/station/inventory/items/water/updates")
        after = after_response.get_json() or {}
        after_history = (after_history_response.get_json() or {}).get("updates", [])

        control = self.client.post(
            "/inventory/items/water/usage",
            json={"used_quantity": 0, "user_id": "crew-1", "now": "2026-11-09T10:01:00Z", "update_id": "U205"},
        )
        control_body = control.get_json() or {}
        failures = []
        if rejected.status_code != 400:
            failures.append(f"rejection expected HTTP 400, got {rejected.status_code}")
        if rejected_body.get("error") != "validation_error":
            failures.append(f"expected validation_error, got {rejected_body.get('error')!r}")
        if after_response.status_code != 200 or after.get("quantity") != before.get("quantity", 4):
            failures.append("negative quantity changed the item or item state could not be read")
        if after_history_response.status_code != 200 or after_history != before_history:
            failures.append("negative quantity created an update record or history could not be read")
        if control.status_code != 200 or control_body.get("quantity") != 4:
            failures.append("same-shape zero-usage control was not accepted with quantity 4")
        self.assert_all(failures)

    def test_AC004_view_inventory_from_earth(self):
        response = self.client.get("/earth/inventory")
        body = response.get_json() or {}
        failures = []
        if response.status_code != 200:
            failures.append(f"expected HTTP 200, got {response.status_code}")
        if {"item_id": "water", "name": "water", "quantity": 9, "unit": "packs"} not in body.get("items", []):
            failures.append("expected water quantity 9 packs in Earth inventory")
        if body.get("last_successful_sync") != "2026-11-09T09:55:00Z":
            failures.append("expected the specified last successful sync time")
        self.assert_all(failures)

    def test_AC005_keep_offline_change_after_restart(self):
        response = self.client.post(
            "/station/offline/updates",
            json={"update": {"item_id": "water", "used_quantity": 2, "user_id": "crew-1", "update_id": "U206"}},
        )
        body = response.get_json() or {}
        # A new client represents a fresh app session against the same persistent store.
        restarted_client = app.test_client()
        item_response = restarted_client.get("/station/inventory/items/water")
        status_response = restarted_client.get("/station/sync-status")
        item = item_response.get_json() or {}
        status = status_response.get_json() or {}
        failures = []
        if response.status_code != 201:
            failures.append(f"expected local-save HTTP 201, got {response.status_code}")
        if body.get("pending_count") != 1:
            failures.append(f"expected pending_count 1, got {body.get('pending_count')!r}")
        if item_response.status_code != 200 or item.get("quantity") != 3:
            failures.append("restart did not retain local quantity 3, or local inventory could not be read")
        if status_response.status_code != 200 or status.get("pending_count") != 1:
            failures.append("restart did not retain one pending update")
        if status.get("last_successful_sync") != "2026-11-09T09:55:00Z":
            failures.append("restart did not retain the last successful sync time")
        self.assert_all(failures)

    def test_AC006_sync_waiting_update(self):
        response = self.client.post("/sync")
        body = response.get_json() or {}
        failures = []
        if response.status_code != 200:
            failures.append(f"expected HTTP 200, got {response.status_code}")
        if "U102" not in body.get("accepted_update_ids", []):
            failures.append("expected Earth-accepted update U102 to be marked synced")
        if body.get("pending_update_ids") != []:
            failures.append("expected no pending update after Earth acceptance")
        self.assert_all(failures)

    def test_AC007_duplicate_update_is_not_applied_twice(self):
        before_item_response = self.client.get("/station/inventory/items/water")
        before_history_response = self.client.get("/station/inventory/items/water/updates")
        before_item = before_item_response.get_json() or {}
        before_history = (before_history_response.get_json() or {}).get("updates", [])

        response = self.client.post("/sync/updates/U101/retry")
        body = response.get_json() or {}
        after_item_response = self.client.get("/station/inventory/items/water")
        after_history_response = self.client.get("/station/inventory/items/water/updates")
        after_item = after_item_response.get_json() or {}
        after_history = (after_history_response.get_json() or {}).get("updates", [])
        failures = []
        if response.status_code != 200 or body.get("status") != "already_accepted":
            failures.append("expected HTTP 200 and already_accepted for U101 retry")
        if after_item_response.status_code != 200 or after_item.get("quantity") != before_item.get("quantity", 9):
            failures.append("duplicate retry changed the quantity or item state could not be read")
        if after_history_response.status_code != 200 or after_history != before_history:
            failures.append("duplicate retry created a second inventory update or history could not be read")
        self.assert_all(failures)

    def test_AC008_resolve_conflict_and_record_audit(self):
        response = self.client.post(
            "/conflicts/conflict-1/resolve",
            json={
                "selected_location": "Store B",
                "reason": "Station count confirmed",
                "reviewer_id": "reviewer-1",
                "now": "2026-11-09T10:05:00Z",
            },
        )
        body = response.get_json() or {}
        failures = []
        if response.status_code != 200:
            failures.append(f"expected HTTP 200, got {response.status_code}")
        for key, expected in {
            "station_location": "Store B",
            "earth_location": "Store C",
            "selected_location": "Store B",
            "reason": "Station count confirmed",
            "reviewer_id": "reviewer-1",
            "time": "2026-11-09T10:05:00Z",
        }.items():
            if body.get(key) != expected:
                failures.append(f"expected {key}={expected!r}, got {body.get(key)!r}")
        self.assert_all(failures)


if __name__ == "__main__":
    unittest.main()
