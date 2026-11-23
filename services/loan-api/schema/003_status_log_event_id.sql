-- E5: idempotent decision recording. One row per decision event; replays insert nothing.
ALTER TABLE application_status_log ADD COLUMN IF NOT EXISTS event_id VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS uq_status_log_event_id
    ON application_status_log(event_id) WHERE event_id IS NOT NULL;
