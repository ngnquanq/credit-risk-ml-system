CREATE TABLE IF NOT EXISTS application_status_log (
    id BIGSERIAL PRIMARY KEY,
    sk_id_curr VARCHAR(255) NOT NULL REFERENCES loan_applications(sk_id_curr) ON DELETE CASCADE,
    
    -- Status Information
    status VARCHAR(50) NOT NULL CHECK (status IN (
        'submitted',           -- Initial submission
        'pre_screening',       -- Business rules validation
        'pre_screening_passed',
        'pre_screening_failed',
        'document_verification', 
        'bureau_requested',    -- External bureau API called
        'bureau_received',     -- Bureau data received
        'feature_engineering', -- Flink processing
        'ml_scoring',          -- Model inference
        'scoring_completed',
        'approved',            -- Final decisions
        'rejected',
        'manual_review',
        'cancelled',
        'error'                -- System errors
    )),
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    created_by VARCHAR(100) NOT NULL,  -- Which service/user made this change
    
    -- Additional Context
    metadata JSONB,  -- Service-specific data (scores, reasons, error details)
    
    -- Performance: Most queries will be by sk_id_curr + recent timestamps
    CONSTRAINT valid_created_by CHECK (created_by != '')
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_application_status_log_sk_id_curr 
    ON application_status_log(sk_id_curr, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_application_status_log_status 
    ON application_status_log(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_application_status_log_created_at 
    ON application_status_log(created_at DESC);

-- Create view for current status (most common query)
CREATE OR REPLACE VIEW current_application_status AS
SELECT DISTINCT ON (sk_id_curr) 
    sk_id_curr,
    status as current_status,
    created_at as status_updated_at,
    created_by as last_updated_by,
    metadata
FROM application_status_log
ORDER BY sk_id_curr, created_at DESC;

-- Comments for documentation
COMMENT ON TABLE application_status_log IS 'Event sourcing log for application status changes. Append-only table for full audit trail.';
COMMENT ON COLUMN application_status_log.sk_id_curr IS 'Reference to loan application';
COMMENT ON COLUMN application_status_log.status IS 'Application workflow status at this point in time';
COMMENT ON COLUMN application_status_log.created_by IS 'Service or user that triggered this status change (api-service, ml-scoring-service, etc.)';
COMMENT ON COLUMN application_status_log.metadata IS 'Additional context: scores, rejection reasons, error details, processing time, etc.';

COMMENT ON VIEW current_application_status IS 'View showing current status of each application (most recent status log entry)';

-- Example usage queries for documentation
/*
-- Insert new status change
INSERT INTO application_status_log (sk_id_curr, status, created_by, metadata) 
VALUES ('CUSTOMER_001', 'ml_scoring', 'ml-scoring-service', 
        '{"score": 0.85, "confidence": 0.92, "processing_time_ms": 150}');

-- Get current status of application
SELECT current_status FROM current_application_status WHERE sk_id_curr = 'CUSTOMER_001';

-- Get full status history of application
SELECT status, created_at, created_by, metadata 
FROM application_status_log 
WHERE sk_id_curr = 'CUSTOMER_001' 
ORDER BY created_at;

-- Get all applications in specific status
SELECT sk_id_curr, status_updated_at 
FROM current_application_status 
WHERE current_status = 'ml_scoring';
*/

