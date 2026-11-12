PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS leads (
    lead_id INTEGER PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    phone_lookup_hash TEXT NOT NULL,
    phone_encrypted BLOB NOT NULL,
    customer_name_encrypted BLOB NOT NULL,
    external_ref TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workflow_id, phone_lookup_hash)
);

CREATE INDEX IF NOT EXISTS idx_leads_workflow_ref
    ON leads (workflow_id, external_ref);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    call_id TEXT,
    phone_lookup_hash TEXT,
    occurred_at_utc TEXT,
    payload_json TEXT NOT NULL,
    lead_id INTEGER,
    link_status TEXT NOT NULL CHECK (link_status IN ('linked', 'orphan', 'ignored')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (lead_id) REFERENCES leads (lead_id)
);

CREATE INDEX IF NOT EXISTS idx_events_lead
    ON events (lead_id, occurred_at_utc);

CREATE INDEX IF NOT EXISTS idx_events_pending_phone
    ON events (workflow_id, phone_lookup_hash, link_status);

CREATE INDEX IF NOT EXISTS idx_events_call
    ON events (workflow_id, call_id);

CREATE TABLE IF NOT EXISTS rejections (
    rejection_id INTEGER PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    reason TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rejections_sort
    ON rejections (workflow_id, batch_id, row_number);

CREATE TABLE IF NOT EXISTS ingested_drops (
    drop_path TEXT PRIMARY KEY,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_counters (
    counter_name TEXT PRIMARY KEY,
    counter_value INTEGER NOT NULL DEFAULT 0
);
