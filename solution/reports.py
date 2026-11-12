from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from .config import DispositionSpec
from .pii import PiiProtector
from .rules import LeadFact, build_lead_facts, ist_date


QUALITY_COUNTERS = (
    "lead_rows_total",
    "lead_rows_rejected",
    "duplicate_lead_rows_merged",
    "field_warnings",
    "events_total",
    "malformed_events",
    "duplicate_events_dropped",
    "orphan_events",
    "unknown_disposition_events",
)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _batch_summary(facts: tuple[LeadFact, ...]) -> list[dict[str, object]]:
    buckets: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {
            "total_leads": 0,
            "yet_to_reach_out": 0,
            "in_progress_telephony_failed": 0,
            "in_progress_dialed": 0,
            "completed": 0,
        }
    )
    for fact in facts:
        counts = buckets[(fact.workflow_id, fact.batch_id)]
        counts["total_leads"] += 1
        counts[fact.bucket] += 1
    return [
        {
            "workflow_id": workflow_id,
            "batch_id": batch_id,
            **buckets[(workflow_id, batch_id)],
        }
        for workflow_id, batch_id in sorted(buckets)
    ]


def _daily_overview(
    facts: tuple[LeadFact, ...],
    dispositions: dict[str, dict[str, DispositionSpec]],
) -> list[dict[str, object]]:
    daily: dict[tuple[str, object], dict[str, object]] = defaultdict(
        lambda: {
            "total_calls": 0,
            "connected_calls": 0,
            "success_leads": set(),
        }
    )
    for fact in facts:
        workflow_dispositions = dispositions.get(fact.workflow_id, {})
        for call in fact.calls:
            key = (fact.workflow_id, ist_date(call.initiated_at))
            summary = daily[key]
            summary["total_calls"] += 1
            summary["connected_calls"] += int(call.connected)
            if (
                call.effective_disposition
                and workflow_dispositions.get(
                    call.effective_disposition,
                    DispositionSpec("", False, False),
                ).is_success
            ):
                summary["success_leads"].add(fact.lead_id)

    rows = []
    for workflow_id, report_date in sorted(daily):
        summary = daily[(workflow_id, report_date)]
        total_calls = int(summary["total_calls"])
        connected_calls = int(summary["connected_calls"])
        rows.append(
            {
                "workflow_id": workflow_id,
                "date": report_date.isoformat(),
                "total_calls": total_calls,
                "connected_calls": connected_calls,
                "connectivity_rate": f"{connected_calls / total_calls:.4f}",
                "success_leads": len(summary["success_leads"]),
            }
        )
    return rows


def _lead_report(
    connection: sqlite3.Connection,
    facts: tuple[LeadFact, ...],
    pii: PiiProtector,
) -> list[dict[str, object]]:
    encrypted_phones = {
        row["lead_id"]: row["phone_encrypted"]
        for row in connection.execute(
            "SELECT lead_id, phone_encrypted FROM leads"
        )
    }
    rows = []
    for fact in facts:
        phone = pii.decrypt(encrypted_phones[fact.lead_id])
        rows.append(
            {
                "workflow_id": fact.workflow_id,
                "external_ref": fact.external_ref,
                "batch_id": fact.batch_id,
                "phone_masked": f"+91******{phone[-4:]}",
                "bucket": fact.bucket,
                "total_calls": fact.total_calls,
                "connected_calls": fact.connected_calls,
                "last_call_at": fact.last_call_at,
                "current_disposition": fact.current_disposition or "",
                "ever_success": "true" if fact.ever_success else "false",
            }
        )
    return rows


def _rejections(connection: sqlite3.Connection) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT workflow_id, batch_id, row_number, reason
            FROM rejections
            ORDER BY workflow_id, batch_id, row_number
            """
        )
    ]


def _quality(connection: sqlite3.Connection) -> dict[str, object]:
    counters = {
        row["counter_name"]: row["counter_value"]
        for row in connection.execute("SELECT counter_name, counter_value FROM quality_counters")
    }
    reasons: dict[str, int] = defaultdict(int)
    for row in connection.execute(
        "SELECT reason, COUNT(*) AS count FROM rejections GROUP BY reason ORDER BY reason"
    ):
        reasons[row["reason"]] = row["count"]
    return {
        name: counters.get(name, 0)
        for name in QUALITY_COUNTERS[:4]
    } | {
        "rejections_by_reason": dict(reasons),
    } | {
        name: counters.get(name, 0)
        for name in QUALITY_COUNTERS[4:]
    }


def generate_reports(
    connection: sqlite3.Connection,
    output_dir: str | Path,
    dispositions: dict[str, dict[str, DispositionSpec]],
    pii: PiiProtector,
) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    facts = build_lead_facts(connection, dispositions)

    _write_csv(
        output_dir / "batch_summary.csv",
        [
            "workflow_id",
            "batch_id",
            "total_leads",
            "yet_to_reach_out",
            "in_progress_telephony_failed",
            "in_progress_dialed",
            "completed",
        ],
        _batch_summary(facts),
    )
    _write_csv(
        output_dir / "daily_overview.csv",
        [
            "workflow_id",
            "date",
            "total_calls",
            "connected_calls",
            "connectivity_rate",
            "success_leads",
        ],
        _daily_overview(facts, dispositions),
    )
    _write_csv(
        output_dir / "lead_report.csv",
        [
            "workflow_id",
            "external_ref",
            "batch_id",
            "phone_masked",
            "bucket",
            "total_calls",
            "connected_calls",
            "last_call_at",
            "current_disposition",
            "ever_success",
        ],
        _lead_report(connection, facts, pii),
    )
    _write_csv(
        output_dir / "rejections.csv",
        ["workflow_id", "batch_id", "row_number", "reason"],
        _rejections(connection),
    )
    with (output_dir / "data_quality.json").open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        json.dump(_quality(connection), file, indent=2)
        file.write("\n")
