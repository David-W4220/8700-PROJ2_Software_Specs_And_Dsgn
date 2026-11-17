import json, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Database file is created in the project root.
DB_PATH = Path(__file__).resolve().parents[2] / "space_station.db"


def utc_timestamp() -> str:
    #Return the current UTC time as an ISO 8601 string.
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    #Open the database and ensure that the required tables exist.
    database_path = Path(DB_PATH)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS inventory_items (
            item_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT,
            minimum_quantity REAL,
            importance TEXT,
            location TEXT,
            condition TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS inventory_updates (
            update_id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            old_quantity REAL NOT NULL,
            new_quantity REAL NOT NULL,
            update_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            acknowledged INTEGER NOT NULL DEFAULT 0,
            details TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_records (
            audit_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            old_values TEXT,
            new_values TEXT,
            details TEXT
        );

        CREATE TABLE IF NOT EXISTS missions (
            mission_id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS manifests (
            manifest_id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sync_conflicts (
            conflict_id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sync_metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )

    return connection


def initialize_database() -> None:
    #Create the database tables if they do not already exist.
    connection = _connect()
    connection.close()


def insert_demo_data() -> None:
    #Insert a user and inventory items if they do not exist.
    connection = _connect()

    try:
        connection.execute(
            """
            INSERT OR IGNORE INTO users (user_id, role, active)
            VALUES (?, ?, ?)
            """,
            ("crew-01", "Station Inventory Crew", 1),
        )

        demo_items = [
            (
                "WTR-001",
                "Drinking Water",
                120.0,
                "liters",
                40.0,
                "High",
                "Storage A",
                "Usable",
                utc_timestamp(),
            ),
            (
                "FOOD-001",
                "Food Packages",
                80.0,
                "packages",
                30.0,
                "High",
                "Storage B",
                "Usable",
                utc_timestamp(),
            ),
        ]

        connection.executemany(
            """
            INSERT OR IGNORE INTO inventory_items
            (
                item_id, name, quantity, unit, minimum_quantity,
                importance, location, condition, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            demo_items,
        )

        connection.commit()
    finally:
        connection.close()


def get_user(user_id: str) -> dict[str, Any] | None:
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),).fetchone()

        return dict(row) if row else None
    finally:
        connection.close()


def get_inventory_item(item_id: str) -> dict[str, Any] | None:
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT * FROM inventory_items WHERE item_id = ?",
            (item_id,),).fetchone()

        return dict(row) if row else None
    finally:
        connection.close()


def list_inventory_items() -> list[dict[str, Any]]:
    connection = _connect()
    try:
        rows = connection.execute("SELECT * FROM inventory_items ORDER BY item_id").fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()


def save_inventory_item(item: dict[str, Any]) -> dict[str, Any]:
    connection = _connect()
    try:
        connection.execute(
            """
            INSERT OR REPLACE INTO inventory_items
            (
                item_id, name, quantity, unit, minimum_quantity,
                importance, location, condition, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["item_id"],
                item["name"],
                float(item["quantity"]),
                item.get("unit"),
                item.get("minimum_quantity"),
                item.get("importance"),
                item.get("location"),
                item.get("condition"),
                item.get("updated_at") or utc_timestamp(),
            ),
        )
        connection.commit()
        return get_inventory_item(item["item_id"])
    finally:
        connection.close()


def save_inventory_update(update: dict[str, Any]) -> dict[str, Any]:
    #Save one inventory update record.
    update_id = update.get("update_id") or str(uuid.uuid4())

    connection = _connect()
    try:
        connection.execute(
            """
            INSERT INTO inventory_updates
            (
                update_id, item_id, user_id, old_quantity, new_quantity,
                update_type, timestamp, acknowledged, details
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                update_id,
                update["item_id"],
                update["user_id"],
                float(update["old_quantity"]),
                float(update["new_quantity"]),
                update.get("update_type", "quantity_update"),
                update.get("timestamp") or utc_timestamp(),
                int(update.get("acknowledged", False)),
                json.dumps(update.get("details", {})),
            ),
        )
        connection.commit()

        return get_inventory_update(update_id)
    finally:
        connection.close()


def get_inventory_update(update_id: str) -> dict[str, Any] | None:
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT * FROM inventory_updates WHERE update_id = ?",
            (update_id,),).fetchone()

        if not row: return None

        result = dict(row)
        result["details"] = json.loads(result["details"] or "{}")
        return result
    finally:
        connection.close()


def list_inventory_updates(item_id: str) -> list[dict[str, Any]]:
    connection = _connect()
    try:
        rows = connection.execute(
            """
            SELECT * FROM inventory_updates
            WHERE item_id = ?
            ORDER BY timestamp
            """,
            (item_id,),).fetchall()

        results = []
        for row in rows:
            result = dict(row)
            result["details"] = json.loads(result["details"] or "{}")
            results.append(result)

        return results
    finally:
        connection.close()


def list_pending_updates() -> list[dict[str, Any]]:
    connection = _connect()
    try:
        rows = connection.execute(
            """
            SELECT * FROM inventory_updates
            WHERE acknowledged = 0
            ORDER BY timestamp
            """
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()


def mark_update_acknowledged(update_id: str) -> None:
    connection = _connect()
    try:
        connection.execute(
            """
            UPDATE inventory_updates
            SET acknowledged = 1
            WHERE update_id = ?
            """,
            (update_id,),
        )
        connection.commit()
    finally:
        connection.close()


def save_audit_record(record: dict[str, Any]) -> dict[str, Any]:
    #Save an audit record.
    audit_id = record.get("audit_id") or str(uuid.uuid4())

    connection = _connect()
    try:
        _insert_audit_record(connection, record, audit_id)
        connection.commit()

        return {
            **record,
            "audit_id": audit_id,
        }
    finally:
        connection.close()


def _insert_audit_record(connection: sqlite3.Connection,
    record: dict[str, Any], audit_id: str | None = None,) -> None:
    #Insert an audit record using an existing database connection.
    audit_id = audit_id or record.get("audit_id") or str(uuid.uuid4())

    connection.execute(
        """
        INSERT INTO audit_records
        (
            audit_id, timestamp, user_id, action, entity_type,
            entity_id, old_values, new_values, details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            audit_id,
            record.get("timestamp") or utc_timestamp(),
            record["user_id"],
            record["action"],
            record.get("entity_type", "inventory_item"),
            record["entity_id"],
            json.dumps(record.get("old_values", {})),
            json.dumps(record.get("new_values", {})),
            json.dumps(record.get("details", {})),
        ),
    )


def list_audit_records(entity_id: str | None = None,) -> list[dict[str, Any]]:
    connection = _connect()
    try:
        if entity_id is None:
            rows = connection.execute("SELECT * FROM audit_records ORDER BY timestamp").fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM audit_records
                WHERE entity_id = ?
                ORDER BY timestamp
                """,
                (entity_id,),).fetchall()

        results = []
        for row in rows:
            result = dict(row)
            result["old_values"] = json.loads(result["old_values"] or "{}")
            result["new_values"] = json.loads(result["new_values"] or "{}")
            result["details"] = json.loads(result["details"] or "{}")
            results.append(result)

        return results
    finally:
        connection.close()


def save_quantity_change(updated_item: dict[str, Any],
    update_record: dict[str, Any], audit_record: dict[str, Any],) -> None:
    """
    Save the inventory quantity, update history, and audit record together.
    If one operation fails, the transaction is rolled back.
    """
    connection = _connect()

    try:
        connection.execute("BEGIN IMMEDIATE")

        cursor = connection.execute(
            """
            UPDATE inventory_items
            SET quantity = ?, updated_at = ?
            WHERE item_id = ?
            """,
            (
                float(updated_item["quantity"]),
                updated_item["updated_at"],
                updated_item["item_id"],
            ),
        )

        if cursor.rowcount == 0:
            raise KeyError(updated_item["item_id"])

        update_id = update_record.get("update_id") or str(uuid.uuid4())

        connection.execute(
            """
            INSERT INTO inventory_updates
            (
                update_id, item_id, user_id, old_quantity, new_quantity,
                update_type, timestamp, acknowledged, details
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                update_id,
                update_record["item_id"],
                update_record["user_id"],
                float(update_record["old_quantity"]),
                float(update_record["new_quantity"]),
                update_record.get("update_type", "quantity_update"),
                update_record.get("timestamp") or utc_timestamp(),
                0,
                json.dumps(update_record.get("details", {})),
            ),
        )

        _insert_audit_record(connection, audit_record)
        connection.commit()

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_last_successful_sync_time() -> str | None:
    connection = _connect()
    try:
        row = connection.execute(
            """
            SELECT value FROM sync_metadata
            WHERE key = 'last_successful_sync_time'
            """
        ).fetchone()

        return row["value"] if row else None
    finally:
        connection.close()


def get_mission(mission_id: str) -> dict[str, Any] | None:
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT data FROM missions WHERE mission_id = ?",
            (mission_id,),
        ).fetchone()

        return json.loads(row["data"]) if row else None
    finally:
        connection.close()


def save_mission(mission: dict[str, Any]) -> None:
    connection = _connect()
    try:
        connection.execute(
            """
            INSERT OR REPLACE INTO missions (mission_id, data)
            VALUES (?, ?)
            """,
            (
                mission["mission_id"],
                json.dumps(mission),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def get_manifest(manifest_id: str) -> dict[str, Any] | None:
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT data FROM manifests WHERE manifest_id = ?",
            (manifest_id,),).fetchone()

        return json.loads(row["data"]) if row else None
    finally:
        connection.close()


def save_manifest(manifest: dict[str, Any]) -> None:
    connection = _connect()
    try:
        connection.execute(
            """
            INSERT OR REPLACE INTO manifests (manifest_id, data)
            VALUES (?, ?)
            """,
            (
                manifest["manifest_id"],
                json.dumps(manifest),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def save_sync_conflict(conflict: dict[str, Any]) -> None:
    conflict_id = conflict.get("conflict_id") or str(uuid.uuid4())

    connection = _connect()
    try:
        connection.execute(
            """
            INSERT OR REPLACE INTO sync_conflicts (conflict_id, data)
            VALUES (?, ?)
            """,
            (conflict_id, json.dumps(conflict)),
        )
        connection.commit()
    finally:
        connection.close()


def list_sync_conflicts() -> list[dict[str, Any]]:
    connection = _connect()
    try:
        rows = connection.execute("SELECT data FROM sync_conflicts").fetchall()

        return [json.loads(row["data"]) for row in rows]
    finally:
        connection.close()
