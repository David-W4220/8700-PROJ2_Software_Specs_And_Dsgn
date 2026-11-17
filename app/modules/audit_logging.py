import uuid
from app.modules import local_data_storage as storage


def record_event(user_id: str, action: str, entity_type: str, entity_id: str,
    old_values: dict | None = None, new_values: dict | None = None,
    details: dict | None = None,) -> dict:
    #Create and save an audit event.
    record = {
        "audit_id": str(uuid.uuid4()),
        "timestamp": storage.utc_timestamp(),
        "user_id": user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "old_values": old_values or {},
        "new_values": new_values or {},
        "details": details or {},
    }
    return storage.save_audit_record(record)

def list_records() -> list[dict]:
    #Return stored audit records.
    return storage.list_audit_records()
