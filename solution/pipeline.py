from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .config import load_dispositions, load_workflow_schema
from .events import ingest_event_file
from .leads import ingest_lead_file
from .pii import PiiProtector


@dataclass(frozen=True)
class DropIngestResult:
    skipped: bool
    lead_files: int = 0
    event_files: int = 0


def ingest_drop(
    connection: sqlite3.Connection,
    drop_path: str | Path,
    schemas_dir: str | Path,
    dispositions_path: str | Path,
    pii: PiiProtector,
) -> DropIngestResult:
    drop_path = Path(drop_path).resolve()
    schemas_dir = Path(schemas_dir)
    if connection.execute(
        "SELECT 1 FROM ingested_drops WHERE drop_path = ?",
        (str(drop_path),),
    ).fetchone():
        return DropIngestResult(skipped=True)

    dispositions = load_dispositions(dispositions_path)
    lead_files = 0
    event_files = 0
    with connection:
        for workflow_dir in sorted(
            path for path in (drop_path / "leads").iterdir() if path.is_dir()
        ):
            schema = load_workflow_schema(
                schemas_dir / f"{workflow_dir.name}.json"
            )
            for lead_path in sorted(workflow_dir.glob("*.csv")):
                ingest_lead_file(
                    connection,
                    lead_path,
                    schema,
                    lead_path.stem,
                    pii,
                )
                lead_files += 1

        for event_path in sorted((drop_path / "events").glob("*.jsonl")):
            ingest_event_file(connection, event_path, dispositions, pii)
            event_files += 1

        connection.execute(
            """
            INSERT INTO ingested_drops (drop_path, ingested_at)
            VALUES (?, datetime('now'))
            """,
            (str(drop_path),),
        )
    return DropIngestResult(
        skipped=False,
        lead_files=lead_files,
        event_files=event_files,
    )
