import json

from solution.config import load_workflow_schema
from solution.database import connect_database, initialize_database
from solution.leads import ingest_lead_file
from solution.pii import PiiProtector


def test_lead_ingestion_merges_duplicates_and_protects_pii(tmp_path):
    database_path = tmp_path / "data.sqlite"
    csv_path = tmp_path / "batch_001.csv"
    csv_path.write_text(
        "Name,Mobile No,Policy No,Expiry Date,Premium,Language\n"
        "Asha Rao,+91 98765 43210,MOT-1,01-Dec-2026,\"₹12,500\",HI\n"
        "Asha Updated,09876543210,MOT-1,02/12/2026,,Hindi\n"
        ",9876543210,MOT-2,,100,en\n",
        encoding="utf-8",
    )
    schema = load_workflow_schema(
        "assignment-a-data/schemas/motor_renewal.json"
    )
    initialize_database(database_path)
    connection = connect_database(database_path)
    try:
        stats = ingest_lead_file(
            connection,
            csv_path,
            schema,
            "batch_001",
            PiiProtector(b"test secret"),
        )
        connection.commit()
        assert stats.rows_total == 3
        assert stats.rows_rejected == 1
        assert stats.duplicate_rows_merged == 1
        assert stats.field_warnings == 1
        lead = connection.execute(
            "SELECT * FROM leads"
        ).fetchone()
        assert b"9876543210" not in lead["phone_encrypted"]
        assert b"Asha Updated" not in lead["customer_name_encrypted"]
        assert json.loads(lead["attributes_json"])["preferred_language"] == "hi"
        assert connection.execute("SELECT COUNT(*) FROM rejections").fetchone()[0] == 1
    finally:
        connection.close()
