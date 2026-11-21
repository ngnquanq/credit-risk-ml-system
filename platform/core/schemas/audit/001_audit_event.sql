-- E13: append-only, hash-chained audit trail in its own database ("audit").
-- Roles: audit_writer (services) may INSERT and SELECT; audit_reader (auditor API) reads the view.
-- No service role holds UPDATE, DELETE or TRUNCATE. The owner role is break-glass only.

CREATE TABLE IF NOT EXISTS audit_event (
    id            BIGSERIAL PRIMARY KEY,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_sub     VARCHAR(64) NOT NULL,
    actor_realm   VARCHAR(16) NOT NULL CHECK (actor_realm IN ('staff', 'customers', 'service')),
    actor_roles   TEXT[] NOT NULL,
    action        VARCHAR(48) NOT NULL,
    resource_type VARCHAR(24) NOT NULL,
    resource_id   VARCHAR(64) NOT NULL,
    outcome       VARCHAR(8)  NOT NULL CHECK (outcome IN ('allowed', 'denied', 'error')),
    trace_id      VARCHAR(32),
    details       JSONB NOT NULL DEFAULT '{}'::jsonb,
    prev_hash     BYTEA NOT NULL,
    hash          BYTEA NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_event (resource_type, resource_id, id);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_event (actor_sub, occurred_at DESC);

CREATE OR REPLACE VIEW audit_trace AS
    SELECT id, occurred_at, actor_sub, actor_realm, actor_roles, action,
           resource_type, resource_id, outcome, trace_id, details
    FROM audit_event;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'audit_writer') THEN
        CREATE ROLE audit_writer LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'audit_reader') THEN
        CREATE ROLE audit_reader LOGIN;
    END IF;
END $$;

REVOKE ALL ON audit_event FROM PUBLIC;
GRANT INSERT, SELECT ON audit_event TO audit_writer;
GRANT USAGE ON SEQUENCE audit_event_id_seq TO audit_writer;
GRANT SELECT ON audit_trace TO audit_reader;
-- Passwords for both roles are set at deploy time from Kubernetes Secrets (make k8s-secrets).
