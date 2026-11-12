from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .config import FieldSpec, WorkflowSchema
from .parsing import (
    normalize_header,
    normalize_phone,
    parse_date,
    parse_decimal,
    parse_enum,
)
from .pii import PiiProtector


@dataclass
class LeadIngestStats:
    rows_total: int = 0
    rows_rejected: int = 0
    duplicate_rows_merged: int = 0
    field_warnings: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _parse_field(field: FieldSpec, raw: str) -> Any:
    if field.type == "string":
        return raw.strip()
    if field.type == "phone":
        return normalize_phone(raw)
    if field.type == "date":
        return parse_date(raw)
    if field.type == "decimal":
        return parse_decimal(raw)
    if field.type == "enum":
        return parse_enum(raw, field.values)
    raise ValueError(f"unsupported_field_type:{field.type}")


def _parse_row(
    cells: list[str],
    column_fields: list[FieldSpec | None],
    schema: WorkflowSchema,
) -> tuple[dict[str, Any] | None, str | None, int]:
    raw_values = {
        field.name: (
            cells[index].strip()
            if index < len(cells) and column_fields[index] is field
            else ""
        )
        for index, field in enumerate(column_fields)
        if field is not None
    }
    values: dict[str, Any] = {}
    warnings = 0

    for field in schema.fields:
        raw = raw_values.get(field.name, "")
        if not raw:
            if field.required:
                return None, f"missing_required:{field.name}", warnings
            values[field.name] = None
            continue
        try:
            values[field.name] = _parse_field(field, raw)
        except ValueError as error:
            if field.required and field.type == "phone":
                return None, "invalid_phone", warnings
            if field.required:
                return None, str(error), warnings
            values[field.name] = None
            warnings += 1

    return values, None, warnings


def _attributes(schema: WorkflowSchema, values: dict[str, Any]) -> dict[str, Any]:
    excluded = {"customer_name", "phone", schema.reference_field.name}
    return {
        field.name: _serialize_value(values.get(field.name))
        for field in schema.fields
        if field.name not in excluded
    }


def _with_defaults(schema: WorkflowSchema, values: dict[str, Any]) -> dict[str, Any]:
    result = dict(values)
    for field in schema.fields:
        if result.get(field.name) is None and field.default is not None:
            result[field.name] = field.default
    return result


def _apply_attribute_defaults(
    schema: WorkflowSchema,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    result = dict(attributes)
    for field in schema.fields:
        if (
            field.name not in {"customer_name", "phone", schema.reference_field.name}
            and result.get(field.name) is None
            and field.default is not None
        ):
            result[field.name] = field.default
    return result


def ingest_lead_file(
    connection: sqlite3.Connection,
    csv_path: str | Path,
    schema: WorkflowSchema,
    batch_id: str,
    pii: PiiProtector,
) -> LeadIngestStats:
    stats = LeadIngestStats()
    now = _now()
    csv_path = Path(csv_path)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        headers = next(reader, [])
        header_map = schema.headers
        column_fields = [
            header_map.get(normalize_header(header))
            for header in headers
        ]

        for cells in reader:
            if not any(cell.strip() for cell in cells):
                continue
            stats.rows_total += 1
            row_number = stats.rows_total
            values, reason, warnings = _parse_row(cells, column_fields, schema)
            if reason:
                stats.rows_rejected += 1
                connection.execute(
                    """
                    INSERT INTO rejections (workflow_id, batch_id, row_number, reason)
                    VALUES (?, ?, ?, ?)
                    """,
                    (schema.workflow_id, batch_id, row_number, reason),
                )
                continue

            stats.field_warnings += warnings
            assert values is not None
            canonical_phone = values["phone"]
            lookup_hash = pii.lookup_hash(canonical_phone)
            existing = connection.execute(
                """
                SELECT lead_id, customer_name_encrypted, external_ref, attributes_json
                FROM leads
                WHERE workflow_id = ? AND phone_lookup_hash = ?
                """,
                (schema.workflow_id, lookup_hash),
            ).fetchone()

            if existing is None:
                connection.execute(
                    """
                    INSERT INTO leads (
                        workflow_id, phone_lookup_hash, phone_encrypted,
                        customer_name_encrypted, external_ref, batch_id,
                        attributes_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        schema.workflow_id,
                        lookup_hash,
                        pii.encrypt(canonical_phone),
                        pii.encrypt(values["customer_name"]),
                        values[schema.reference_field.name],
                        batch_id,
                        json.dumps(
                            _attributes(
                                schema,
                                _with_defaults(schema, values),
                            ),
                            sort_keys=True,
                        ),
                        now,
                        now,
                    ),
                )
                continue

            stats.duplicate_rows_merged += 1
            attributes = json.loads(existing["attributes_json"])
            incoming_attributes = _attributes(schema, values)
            for name, value in incoming_attributes.items():
                if value is not None:
                    attributes[name] = value
            attributes = _apply_attribute_defaults(schema, attributes)
            connection.execute(
                """
                UPDATE leads
                SET customer_name_encrypted = ?,
                    external_ref = ?,
                    attributes_json = ?,
                    updated_at = ?
                WHERE lead_id = ?
                """,
                (
                    pii.encrypt(values["customer_name"]),
                    values[schema.reference_field.name],
                    json.dumps(attributes, sort_keys=True),
                    now,
                    existing["lead_id"],
                ),
            )

    connection.execute(
        """
        INSERT INTO quality_counters (counter_name, counter_value)
        VALUES ('lead_rows_total', ?)
        ON CONFLICT(counter_name) DO UPDATE SET
            counter_value = counter_value + excluded.counter_value
        """,
        (stats.rows_total,),
    )
    for name, value in (
        ("lead_rows_rejected", stats.rows_rejected),
        ("duplicate_lead_rows_merged", stats.duplicate_rows_merged),
        ("field_warnings", stats.field_warnings),
    ):
        connection.execute(
            """
            INSERT INTO quality_counters (counter_name, counter_value)
            VALUES (?, ?)
            ON CONFLICT(counter_name) DO UPDATE SET
                counter_value = counter_value + excluded.counter_value
            """,
            (name, value),
        )
    return stats
