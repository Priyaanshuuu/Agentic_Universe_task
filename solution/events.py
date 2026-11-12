from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DispositionSpec
from .parsing import normalize_phone, parse_event_timestamp
from .pii import PiiProtector


@dataclass
class EventIngestStats:
    events_total: int = 0
    malformed_events: int = 0
    duplicate_events_dropped: int = 0
    unknown_disposition_events: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_phone_hash(
    event: dict[str, Any],
    pii: PiiProtector,
) -> str | None:
    phone = event.get("phone")
    if not isinstance(phone, str) or not phone.strip():
        return None
    try:
        return pii.lookup_hash(normalize_phone(phone))
    except ValueError:
        return None


def _occurred_at_utc(event: dict[str, Any]) -> str | None:
    value = event.get("occurred_at")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return parse_event_timestamp(value).isoformat()
    except ValueError:
        return None


def _known_disposition(
    event: dict[str, Any],
    dispositions: dict[str, dict[str, DispositionSpec]],
) -> bool:
    if not str(event.get("event_type", "")).startswith("disposition."):
        return True
    payload = event.get("payload")
    code = payload.get("disposition_code") if isinstance(payload, dict) else None
    workflow = dispositions.get(event.get("workflow_id"), {})
    return isinstance(code, str) and code in workflow


def _find_lead_id(
    connection: sqlite3.Connection,
    event: dict[str, Any],
    phone_hash: str | None,
) -> int | None:
    workflow_id = event.get("workflow_id")
    if event.get("event_type") == "disposition.override":
        call_id = event.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            return None
        row = connection.execute(
            """
            SELECT lead_id
            FROM events
            WHERE workflow_id = ? AND call_id = ? AND lead_id IS NOT NULL
            ORDER BY rowid
            LIMIT 1
            """,
            (workflow_id, call_id),
        ).fetchone()
    else:
        if phone_hash is None:
            return None
        row = connection.execute(
            """
            SELECT lead_id
            FROM leads
            WHERE workflow_id = ? AND phone_lookup_hash = ?
            """,
            (workflow_id, phone_hash),
        ).fetchone()
    return row["lead_id"] if row is not None else None


def _increment_counter(
    connection: sqlite3.Connection,
    name: str,
    amount: int,
) -> None:
    connection.execute(
        """
        INSERT INTO quality_counters (counter_name, counter_value)
        VALUES (?, ?)
        ON CONFLICT(counter_name) DO UPDATE SET
            counter_value = counter_value + excluded.counter_value
        """,
        (name, amount),
    )


def relink_orphans(connection: sqlite3.Connection) -> int:
    """Link orphan events to leads that are now available."""
    changed = 0
    rows = connection.execute(
        """
        SELECT event_id, workflow_id, call_id, event_type, phone_lookup_hash
        FROM events
        WHERE link_status = 'orphan'
        ORDER BY rowid
        """
    ).fetchall()
    for row in rows:
        event = {
            "workflow_id": row["workflow_id"],
            "call_id": row["call_id"],
            "event_type": row["event_type"],
        }
        phone_hash = row["phone_lookup_hash"]
        lead_id = _find_lead_id(connection, event, phone_hash)
        if lead_id is None:
            continue
        connection.execute(
            """
            UPDATE events
            SET lead_id = ?, link_status = 'linked'
            WHERE event_id = ?
            """,
            (lead_id, row["event_id"]),
        )
        changed += 1
    _refresh_orphan_counter(connection)
    return changed


def _refresh_orphan_counter(connection: sqlite3.Connection) -> None:
    count = connection.execute(
        "SELECT COUNT(*) FROM events WHERE link_status = 'orphan'"
    ).fetchone()[0]
    connection.execute(
        """
        INSERT INTO quality_counters (counter_name, counter_value)
        VALUES ('orphan_events', ?)
        ON CONFLICT(counter_name) DO UPDATE SET counter_value = excluded.counter_value
        """,
        (count,),
    )


def ingest_event_file(
    connection: sqlite3.Connection,
    jsonl_path: str | Path,
    dispositions: dict[str, dict[str, DispositionSpec]],
    pii: PiiProtector,
) -> EventIngestStats:
    stats = EventIngestStats()
    jsonl_path = Path(jsonl_path)
    with jsonl_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            stats.events_total += 1
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                stats.malformed_events += 1
                continue
            if not isinstance(event, dict) or not event.get("event_id"):
                stats.malformed_events += 1
                continue
            event_id = event["event_id"]
            if connection.execute(
                "SELECT 1 FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone():
                stats.duplicate_events_dropped += 1
                continue

            if not _known_disposition(event, dispositions):
                stats.unknown_disposition_events += 1
                link_status = "ignored"
                lead_id = None
            else:
                phone_hash = _event_phone_hash(event, pii)
                lead_id = _find_lead_id(connection, event, phone_hash)
                link_status = "linked" if lead_id is not None else "orphan"

            phone_hash = _event_phone_hash(event, pii)
            payload = event.get("payload", {})
            connection.execute(
                """
                INSERT INTO events (
                    event_id, workflow_id, event_type, call_id,
                    phone_lookup_hash, occurred_at_utc, payload_json,
                    lead_id, link_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event.get("workflow_id", ""),
                    event.get("event_type", ""),
                    event.get("call_id"),
                    phone_hash,
                    _occurred_at_utc(event),
                    json.dumps(payload, sort_keys=True),
                    lead_id,
                    link_status,
                    _now(),
                ),
            )

    relink_orphans(connection)
    for name, value in (
        ("events_total", stats.events_total),
        ("malformed_events", stats.malformed_events),
        ("duplicate_events_dropped", stats.duplicate_events_dropped),
        ("unknown_disposition_events", stats.unknown_disposition_events),
    ):
        _increment_counter(connection, name, value)
    _refresh_orphan_counter(connection)
    return stats
