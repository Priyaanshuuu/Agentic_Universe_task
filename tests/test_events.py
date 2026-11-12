import json

from solution.config import load_dispositions, load_workflow_schema
from solution.database import connect_database, initialize_database
from solution.events import ingest_event_file
from solution.leads import ingest_lead_file
from solution.pii import PiiProtector


def test_events_dedupe_unknowns_and_relink_orphans(tmp_path):
    database_path = tmp_path / "events.sqlite"
    event_path = tmp_path / "events.jsonl"
    lead_path = tmp_path / "batch_001.csv"
    lead_path.write_text(
        "customer_name,phone,policy_number\nAsha Rao,+919876543210,MOT-1\n",
        encoding="utf-8",
    )
    event_path.write_text(
        "\n".join(
            [
                '{"event_id":"orphan","event_type":"call.initiated","workflow_id":"motor_renewal","call_id":"c1","occurred_at":"2026-10-01 10:00:00","phone":"+919876543210","payload":{}}',
                '{"event_id":"orphan","event_type":"call.initiated","workflow_id":"motor_renewal","call_id":"c1","occurred_at":"2026-10-01 10:00:00","phone":"+919876543210","payload":{}}',
                '{"event_id":"unknown","event_type":"disposition.set","workflow_id":"motor_renewal","call_id":"c1","occurred_at":"2026-10-01T10:00:00Z","phone":"+919876543210","payload":{"disposition_code":"unknown"}}',
                '{"event_id":"bad","event_type":',
            ]
        ),
        encoding="utf-8",
    )
    initialize_database(database_path)
    connection = connect_database(database_path)
    pii = PiiProtector(b"test secret")
    try:
        dispositions = load_dispositions(
            "assignment-a-data/schemas/dispositions.csv"
        )
        stats = ingest_event_file(connection, event_path, dispositions, pii)
        assert stats.events_total == 4
        assert stats.malformed_events == 1
        assert stats.duplicate_events_dropped == 1
        assert stats.unknown_disposition_events == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE link_status = 'orphan'"
        ).fetchone()[0] == 1

        schema = load_workflow_schema(
            "assignment-a-data/schemas/motor_renewal.json"
        )
        ingest_lead_file(connection, lead_path, schema, "batch_001", pii)
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE link_status = 'orphan'"
        ).fetchone()[0] == 0
        assert json.loads(
            connection.execute(
                "SELECT payload_json FROM events WHERE event_id = 'orphan'"
            ).fetchone()["payload_json"]
        ) == {}
    finally:
        connection.close()
