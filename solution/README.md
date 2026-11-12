# Assignment A solution

This solution ingests lead CSV and event JSONL drops into SQLite, then generates
the five required reports from the database.

## Run

From the repository root:

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

`AU_PII_KEY` is required for `ingest` and `report`. Use a secret value outside
local development and never commit it.

## Module boundaries

- `cli.py`: command-line entry point (`init-db`, `ingest`, and `report`).
- `config.py`: load workflow schemas and the disposition catalogue.
- `parsing.py`: normalize headers, phones, dates, decimals, and enums.
- `database.py`: SQLite connection, schema initialization, and transactions.
- `leads.py`: lead ingestion, validation, rejection, and duplicate merging.
- `events.py`: append-only event ingestion, deduplication, and linking.
- `rules.py`: effective dispositions, lead buckets, and report facts.
- `reports.py`: exact CSV and JSON output generation.

The modules remain small and depend on lower-level modules only. Parsing and
business rules are testable without generated data.

## Database design

The database schema is in [`schema.sql`](./schema.sql).

- `leads` stores one row per `(workflow_id, phone_lookup_hash)`.
- `events` is append-only and uses `event_id` as its primary key.
- `rejections` stores non-PII rejection details.
- `ingested_drops` makes drop-level re-ingestion idempotent.
- `quality_counters` stores the data-quality totals used by the report.

Phone numbers will be normalized before hashing. The lookup hash is used for
matching, while the encrypted phone and customer name are used when a value must
be displayed or processed. Plaintext PII will not be stored.

Workflow-specific optional lead fields will be stored as normalized JSON in
`leads.attributes_json`; report-critical identity fields remain separate columns.

Events that cannot currently be linked are retained with `link_status = 'orphan'`.
When a later lead upload arrives, the orphan is relinked by its workflow and
phone hash, or by `call_id` for overrides.
