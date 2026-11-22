-- Audit trail database (E13). Locally the API connects as the database owner; in the cluster it
-- uses the INSERT-only audit_writer role and the read-only audit_reader role.
CREATE DATABASE audit;
\connect audit
\i /schemas/audit/001_audit_event.sql
\connect operations
