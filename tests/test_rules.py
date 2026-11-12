import json

from solution.config import load_dispositions, load_workflow_schema
from solution.database import connect_database, initialize_database
from solution.events import ingest_event_file
from solution.leads import ingest_lead_file
from solution.pii import PiiProtector
from solution.rules import build_lead_facts


def test_effective_override_and_bucket_rules(tmp_path):
    database_path = tmp_path / "rules.sqlite"
    lead_path = tmp_path / "batch_001.csv"
    event_path = tmp_path / "events.jsonl"
    lead_path.write_text(
        "customer_name,phone,policy_number\n"
        "Asha Rao,+919876543210,MOT-1\n"
        "Vikram Das,+919876543211,MOT-2\n"
        "Meera Iyer,+919876543212,MOT-3\n"
        "Ravi Shah,+919876543213,MOT-4\n",
        encoding="utf-8",
    )
    events = [
        {
            "event_id": "e1",
            "event_type": "call.initiated",
            "workflow_id": "motor_renewal",
            "call_id": "c1",
            "occurred_at": "2026-10-01T04:30:00Z",
            "phone": "+919876543210",
            "payload": {},
        },
        {
            "event_id": "e2",
            "event_type": "call.connected",
            "workflow_id": "motor_renewal",
            "call_id": "c1",
            "occurred_at": "2026-10-01T04:31:00Z",
            "phone": "+919876543210",
            "payload": {},
        },
        {
            "event_id": "e3",
            "event_type": "disposition.set",
            "workflow_id": "motor_renewal",
            "call_id": "c1",
            "occurred_at": "2026-10-01T04:40:00Z",
            "phone": "+919876543210",
            "payload": {"disposition_code": "renewed"},
        },
        {
            "event_id": "e4",
            "event_type": "disposition.override",
            "workflow_id": "motor_renewal",
            "call_id": "c1",
            "occurred_at": "2026-10-02T04:40:00Z",
            "payload": {"disposition_code": "not_interested"},
        },
        {
            "event_id": "e5",
            "event_type": "call.initiated",
            "workflow_id": "motor_renewal",
            "call_id": "c2",
            "occurred_at": "2026-10-01T05:30:00Z",
            "phone": "+919876543211",
            "payload": {},
        },
        {
            "event_id": "e6",
            "event_type": "call.telephony_failed",
            "workflow_id": "motor_renewal",
            "call_id": "c2",
            "occurred_at": "2026-10-01T05:31:00Z",
            "phone": "+919876543211",
            "payload": {},
        },
        {
            "event_id": "e7",
            "event_type": "call.initiated",
            "workflow_id": "motor_renewal",
            "call_id": "c3",
            "occurred_at": "2026-10-01T06:30:00Z",
            "phone": "+919876543212",
            "payload": {},
        },
        {
            "event_id": "e8",
            "event_type": "call.connected",
            "workflow_id": "motor_renewal",
            "call_id": "c3",
            "occurred_at": "2026-10-01T06:31:00Z",
            "phone": "+919876543212",
            "payload": {},
        },
    ]
    event_path.write_text(
        "\n".join(json.dumps(event) for event in events),
        encoding="utf-8",
    )
    initialize_database(database_path)
    connection = connect_database(database_path)
    try:
        pii = PiiProtector(b"test secret")
        schema = load_workflow_schema(
            "assignment-a-data/schemas/motor_renewal.json"
        )
        dispositions = load_dispositions(
            "assignment-a-data/schemas/dispositions.csv"
        )
        ingest_lead_file(connection, lead_path, schema, "batch_001", pii)
        ingest_event_file(connection, event_path, dispositions, pii)
        facts = build_lead_facts(connection, dispositions)
        by_ref = {fact.external_ref: fact for fact in facts}

        assert by_ref["MOT-1"].bucket == "completed"
        assert by_ref["MOT-1"].current_disposition == "not_interested"
        assert by_ref["MOT-1"].ever_success is False
        assert by_ref["MOT-1"].last_call_at == "2026-10-01T10:00:00+05:30"
        assert by_ref["MOT-2"].bucket == "in_progress_telephony_failed"
        assert by_ref["MOT-3"].bucket == "in_progress_dialed"
        assert by_ref["MOT-4"].bucket == "yet_to_reach_out"
    finally:
        connection.close()
