import json

from solution.config import load_dispositions
from solution.database import connect_database, initialize_database
from solution.pipeline import ingest_drop
from solution.pii import PiiProtector


def test_drop_ingestion_is_idempotent(tmp_path):
    drop = tmp_path / "drop_1"
    (drop / "leads" / "motor_renewal").mkdir(parents=True)
    (drop / "events").mkdir()
    (drop / "leads" / "motor_renewal" / "batch_001.csv").write_text(
        "customer_name,phone,policy_number\nAsha Rao,+919876543210,MOT-1\n",
        encoding="utf-8",
    )
    (drop / "events" / "events_0001.jsonl").write_text(
        json.dumps(
            {
                "event_id": "e1",
                "event_type": "call.initiated",
                "workflow_id": "motor_renewal",
                "call_id": "c1",
                "occurred_at": "2026-10-01T04:30:00Z",
                "phone": "+919876543210",
                "payload": {},
            }
        ),
        encoding="utf-8",
    )
    database_path = tmp_path / "pipeline.sqlite"
    initialize_database(database_path)
    connection = connect_database(database_path)
    try:
        pii = PiiProtector(b"test secret")
        result = ingest_drop(
            connection,
            drop,
            "assignment-a-data/schemas",
            "assignment-a-data/schemas/dispositions.csv",
            pii,
        )
        skipped = ingest_drop(
            connection,
            drop,
            "assignment-a-data/schemas",
            "assignment-a-data/schemas/dispositions.csv",
            pii,
        )
        assert result == type(result)(False, 1, 1)
        assert skipped.skipped is True
        assert connection.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM ingested_drops"
        ).fetchone()[0] == 1
    finally:
        connection.close()
