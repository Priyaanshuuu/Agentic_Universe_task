# Assignment A solution

This solution will ingest the supplied lead CSV and event JSONL files into SQLite,
then generate the five required reports from the database.

## Planned module boundaries

- `cli.py`: command-line entry point (`init-db`, `ingest`, and `report`).
- `config.py`: load workflow schemas and the disposition catalogue.
- `parsing.py`: normalize headers, phones, dates, decimals, and enums.
- `database.py`: SQLite connection, schema initialization, and transactions.
- `leads.py`: lead ingestion, validation, rejection, and duplicate merging.
- `events.py`: append-only event ingestion, deduplication, and linking.
- `rules.py`: effective dispositions, lead buckets, and report facts.
- `reports.py`: exact CSV and JSON output generation.

The modules will remain small and depend on lower-level modules only. Parsing and
business rules will be testable without a database or generated data.

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
