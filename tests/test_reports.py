import csv
import json

from solution.config import load_dispositions, load_workflow_schema
from solution.database import connect_database, initialize_database
from solution.events import ingest_event_file
from solution.leads import ingest_lead_file
from solution.pii import PiiProtector
from solution.reports import generate_reports


def test_reports_have_exact_shapes_and_formatting(tmp_path):
    database_path = tmp_path / "reports.sqlite"
    lead_path = tmp_path / "batch_001.csv"
    event_path = tmp_path / "events.jsonl"
    output_dir = tmp_path / "reports"
    lead_path.write_text(
        "customer_name,phone,policy_number\nAsha Rao,+919876543210,MOT-1\n",
        encoding="utf-8",
    )
    event_path.write_text(
        "\n".join(
            [
                '{"event_id":"e1","event_type":"call.initiated","workflow_id":"motor_renewal","call_id":"c1","occurred_at":"2026-10-01T04:30:00Z","phone":"+919876543210","payload":{}}',
                '{"event_id":"e2","event_type":"call.connected","workflow_id":"motor_renewal","call_id":"c1","occurred_at":"2026-10-01T04:31:00Z","phone":"+919876543210","payload":{}}',
                '{"event_id":"e3","event_type":"disposition.set","workflow_id":"motor_renewal","call_id":"c1","occurred_at":"2026-10-01T04:40:00Z","phone":"+919876543210","payload":{"disposition_code":"renewed"}}',
            ]
        ),
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
        generate_reports(connection, output_dir, dispositions, pii)
    finally:
        connection.close()

    with (output_dir / "daily_overview.csv").open(newline="", encoding="utf-8") as file:
        daily = list(csv.DictReader(file))
    assert daily == [
        {
            "workflow_id": "motor_renewal",
            "date": "2026-10-01",
            "total_calls": "1",
            "connected_calls": "1",
            "connectivity_rate": "1.0000",
            "success_leads": "1",
        }
    ]
    with (output_dir / "lead_report.csv").open(newline="", encoding="utf-8") as file:
        lead = list(csv.DictReader(file))[0]
    assert lead["phone_masked"] == "+91******3210"
    assert lead["ever_success"] == "true"
    quality = json.loads((output_dir / "data_quality.json").read_text())
    assert quality["events_total"] == 3
