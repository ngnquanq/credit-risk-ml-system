-- ================================================================================
-- Minimal Operational DB Init (CDC Only)
-- Purpose: Create only the core tables used by the API and enable CDC
-- ================================================================================

-- Ensure replication permissions (required for Debezium logical replication)
ALTER USER ops_admin WITH REPLICATION;

-- Create core tables required by the application
\i /schemas/001_create_loan_applications.sql
\i /schemas/002_create_application_status_log.sql

-- Create CDC publication for Debezium
CREATE PUBLICATION debezium_pub FOR TABLE loan_applications;

