-- Same schema as the cluster (platform/core/schemas), applied in order.
\i /schemas/001_create_loan_applications.sql
\i /schemas/002_create_application_status_log.sql
\i /schemas/003_status_log_event_id.sql
\i /schemas/004_ownership_and_policy.sql
\i /schemas/005_case_note.sql
\i /schemas/006_public_ids_and_identity.sql
