# Submission

## Candidate
- **Name:** _Fill in before submission_
- **Assignment chosen:** A (Data)
- **Time spent (honest estimate):** _Fill in before submission_

## How to run
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

$env:AU_PII_KEY = "local-development-key"
python assignment-a-data\tools\generate_data.py --seed 42 --scale small --out data
python -m solution init-db --db assignment_a.sqlite
python -m solution ingest --db assignment_a.sqlite --drop data\drop_1
python -m solution ingest --db assignment_a.sqlite --drop data\drop_2
python -m solution report --db assignment_a.sqlite --out reports
python -m pytest -q
```

## Design
The pipeline has separate parsing, ingestion, rules, and reporting modules. Lead
CSV rows are normalized against the workflow schema before being inserted into
SQLite. Events are stored in an append-only ledger, and reports are calculated
from the ledger rather than from the source files.

The database uses one lead per `(workflow_id, phone_lookup_hash)`, `event_id` as
the event primary key, a rejection table, quality counters, and an
`ingested_drops` table. Phone numbers use HMAC-SHA256 lookup hashes and AES-GCM
encrypted storage; customer names are encrypted. Optional workflow-specific
fields are stored as normalized JSON.

```text
drop -> normalize/validate -> SQLite leads
     -> append/dedupe/link  -> SQLite events
     -> derived rules       -> five reports
```

## Decisions & assumptions

| Decision | Why | Alternative considered |
|---|---|---|
| SQLite instead of Postgres | It is serverless and sufficient for this single-process assignment | Postgres |
| HMAC lookup plus AES-GCM storage | Phone matching needs deterministic lookup, while stored PII must not be plaintext | Plain hashes or plaintext |
| Keep unresolved events in the ledger | A lead may arrive after its events, so the final report must be able to relink them | Discarding orphans |
| Apply defaults after merging | A duplicate with an invalid optional value must not overwrite an earlier valid value with a default | Applying defaults to every input row |

## Failure modes considered

- Invalid lead values become a single rejection reason; optional invalid values
  become warnings.
- Duplicate leads merge by workflow and canonical phone. Duplicate events are
  ignored by `event_id`.
- Orphan events remain stored and are relinked after later lead ingestion.
- Drop paths are recorded transactionally, so re-ingesting a completed drop is
  skipped.
- A database transaction rolls back a drop if ingestion raises an error.
- This is intentionally a single-process SQLite pipeline; it does not implement
  multi-worker ingestion coordination or key rotation.

## Testing

Focused tests cover phone/date/decimal/enum parsing, lead validation and merging,
PII storage, event deduplication and relinking, effective dispositions, bucket
logic, report formatting, and drop idempotency. The full suite runs with
`python -m pytest -q`. I also ran both generated drops with a fresh seed and
verified all five reports were created.

## Results

On a small generated dataset with seed 99, the pipeline produced 1,901 leads and
8,690 stored events from two drops. Re-ingesting the first drop was skipped and
the five reports were generated successfully. Exact timings depend on the
machine and are not included here.

## If I had another day

1. Add a production key-management integration instead of an environment-only key.
2. Add a large-dataset benchmark and optimize bulk inserts if needed.
3. Add a migration/versioning mechanism for future schema changes.
