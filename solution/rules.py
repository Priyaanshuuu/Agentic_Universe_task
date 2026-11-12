from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from typing import Iterable

from .config import DispositionSpec


IST = timezone(timedelta(hours=5, minutes=30))
UTC_MIN = datetime.min.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class CallFact:
    lead_id: int
    workflow_id: str
    call_id: str
    initiated_at: datetime
    connected: bool
    telephony_failed: bool
    effective_disposition: str | None


@dataclass(frozen=True)
class LeadFact:
    lead_id: int
    workflow_id: str
    external_ref: str
    batch_id: str
    bucket: str
    calls: tuple[CallFact, ...]
    current_disposition: str | None
    ever_success: bool

    @property
    def total_calls(self) -> int:
        return len(self.calls)

    @property
    def connected_calls(self) -> int:
        return sum(call.connected for call in self.calls)

    @property
    def last_call_at(self) -> str:
        if not self.calls:
            return ""
        return self.calls[-1].initiated_at.astimezone(IST).isoformat()


def _event_time(value: str | None) -> datetime:
    if not value:
        return UTC_MIN
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _payload_code(payload_json: str) -> str | None:
    payload = json.loads(payload_json)
    code = payload.get("disposition_code") if isinstance(payload, dict) else None
    return code if isinstance(code, str) else None


def build_call_facts(
    connection: sqlite3.Connection,
    dispositions: dict[str, dict[str, DispositionSpec]],
) -> tuple[CallFact, ...]:
    rows = connection.execute(
        """
        SELECT rowid, lead_id, workflow_id, call_id, event_type,
               occurred_at_utc, payload_json
        FROM events
        WHERE link_status = 'linked'
          AND lead_id IS NOT NULL
          AND call_id IS NOT NULL
        ORDER BY rowid
        """
    ).fetchall()
    grouped: dict[tuple[int, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[(row["lead_id"], row["call_id"])].append(row)

    facts: list[CallFact] = []
    for (lead_id, call_id), events in grouped.items():
        initiated = [
            event for event in events if event["event_type"] == "call.initiated"
        ]
        if not initiated:
            continue
        initiated.sort(key=lambda event: (_event_time(event["occurred_at_utc"]), event["rowid"]))
        initiated_at = _event_time(initiated[0]["occurred_at_utc"])
        workflow_id = initiated[0]["workflow_id"]

        overrides = [
            event
            for event in events
            if event["event_type"] == "disposition.override"
        ]
        sets = [
            event
            for event in events
            if event["event_type"] == "disposition.set"
        ]
        disposition_events = overrides or sets
        disposition_events.sort(
            key=lambda event: (_event_time(event["occurred_at_utc"]), event["rowid"])
        )
        effective = (
            _payload_code(disposition_events[-1]["payload_json"])
            if disposition_events
            else None
        )
        facts.append(
            CallFact(
                lead_id=lead_id,
                workflow_id=workflow_id,
                call_id=call_id,
                initiated_at=initiated_at,
                connected=any(
                    event["event_type"] == "call.connected" for event in events
                ),
                telephony_failed=any(
                    event["event_type"] == "call.telephony_failed"
                    for event in events
                ),
                effective_disposition=effective,
            )
        )
    return tuple(
        sorted(facts, key=lambda fact: (fact.workflow_id, fact.lead_id, fact.initiated_at, fact.call_id))
    )


def _bucket(
    calls: Iterable[CallFact],
    workflow_dispositions: dict[str, DispositionSpec],
) -> str:
    calls = tuple(calls)
    if not calls:
        return "yet_to_reach_out"
    if any(
        call.effective_disposition
        and workflow_dispositions.get(call.effective_disposition, DispositionSpec("", False, False)).is_terminal
        for call in calls
    ):
        return "completed"
    if all(call.telephony_failed for call in calls):
        return "in_progress_telephony_failed"
    return "in_progress_dialed"


def build_lead_facts(
    connection: sqlite3.Connection,
    dispositions: dict[str, dict[str, DispositionSpec]],
) -> tuple[LeadFact, ...]:
    calls_by_lead: dict[int, list[CallFact]] = defaultdict(list)
    for call in build_call_facts(connection, dispositions):
        calls_by_lead[call.lead_id].append(call)

    leads = connection.execute(
        """
        SELECT lead_id, workflow_id, external_ref, batch_id
        FROM leads
        ORDER BY workflow_id, external_ref
        """
    ).fetchall()
    facts: list[LeadFact] = []
    for lead in leads:
        calls = tuple(
            sorted(calls_by_lead.get(lead["lead_id"], ()), key=lambda call: call.initiated_at)
        )
        workflow_dispositions = dispositions.get(lead["workflow_id"], {})
        calls_with_dispositions = [
            call for call in calls if call.effective_disposition is not None
        ]
        current = (
            calls_with_dispositions[-1].effective_disposition
            if calls_with_dispositions
            else None
        )
        facts.append(
            LeadFact(
                lead_id=lead["lead_id"],
                workflow_id=lead["workflow_id"],
                external_ref=lead["external_ref"],
                batch_id=lead["batch_id"],
                bucket=_bucket(calls, workflow_dispositions),
                calls=calls,
                current_disposition=current,
                ever_success=any(
                    call.effective_disposition
                    and workflow_dispositions.get(
                        call.effective_disposition,
                        DispositionSpec("", False, False),
                    ).is_success
                    for call in calls
                ),
            )
        )
    return tuple(facts)


def ist_date(value: datetime) -> date:
    return value.astimezone(IST).date()
