from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .parsing import normalize_header


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    required: bool
    pii: bool = False
    reference: bool = False
    aliases: tuple[str, ...] = ()
    values: tuple[str, ...] = ()
    default: Any = None


@dataclass(frozen=True)
class WorkflowSchema:
    workflow_id: str
    fields: tuple[FieldSpec, ...]

    @property
    def reference_field(self) -> FieldSpec:
        return next(field for field in self.fields if field.reference)

    @property
    def headers(self) -> dict[str, FieldSpec]:
        result: dict[str, FieldSpec] = {}
        for field in self.fields:
            for name in (field.name, *field.aliases):
                result.setdefault(normalize_header(name), field)
        return result


@dataclass(frozen=True)
class DispositionSpec:
    code: str
    is_terminal: bool
    is_success: bool


def load_workflow_schema(path: str | Path) -> WorkflowSchema:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    fields = tuple(
        FieldSpec(
            name=field["name"],
            type=field["type"],
            required=field.get("required", False),
            pii=field.get("pii", False),
            reference=field.get("reference", False),
            aliases=tuple(field.get("aliases", ())),
            values=tuple(field.get("values", ())),
            default=field.get("default"),
        )
        for field in document["fields"]
    )
    return WorkflowSchema(workflow_id=document["workflow_id"], fields=fields)


def load_dispositions(path: str | Path) -> dict[str, dict[str, DispositionSpec]]:
    import csv

    result: dict[str, dict[str, DispositionSpec]] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            disposition = DispositionSpec(
                code=row["code"],
                is_terminal=row["is_terminal"].strip().lower() == "true",
                is_success=row["is_success"].strip().lower() == "true",
            )
            result.setdefault(row["workflow_id"], {})[disposition.code] = disposition
    return result
