-- ================================================================================
-- Operational Database Initialization Script
-- Purpose: Initialize schemas and tables for Home Credit operational database
-- ================================================================================

-- Create operational schemas
CREATE SCHEMA IF NOT EXISTS application_ops;     -- Live application state and processing
CREATE SCHEMA IF NOT EXISTS audit_logs;          -- Audit trails and compliance
CREATE SCHEMA IF NOT EXISTS system_config;       -- System configurations and settings
CREATE SCHEMA IF NOT EXISTS model_operations;    -- Model deployment and monitoring metadata

-- ================================================================================
-- APPLICATION OPERATIONS SCHEMA
-- ================================================================================
 -- Ensure replication permissions
ALTER USER ops_admin WITH REPLICATION;

-- Create test applications table
CREATE TABLE IF NOT EXISTS applications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    application_data JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'submitted',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

  -- Create CDC publication
CREATE PUBLICATION debezium_pub FOR TABLE applications;

-- Insert sample data
INSERT INTO applications (user_id, application_data, status) VALUES
(12345, '{"income": 50000, "purpose": "home_loan", "amount": 200000}', 'submitted'),
(12346, '{"income": 75000, "purpose": "car_loan", "amount": 30000}', 'submitted')
ON CONFLICT DO NOTHING;

-- Core loan applications table for operational state
CREATE TABLE IF NOT EXISTS application_ops.loan_applications (
    id BIGSERIAL PRIMARY KEY,
    application_id UUID UNIQUE NOT NULL,
    external_source INTEGER,                      -- External data source identifier
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    
    -- Credit decision fields
    risk_score DECIMAL(7,4),                      -- Model output score
    risk_tier VARCHAR(20),                        -- Risk categorization
    decision VARCHAR(20),                         -- approve/reject/review
    decision_reason TEXT,                         -- Human readable explanation
    decision_confidence DECIMAL(5,4),             -- Model confidence
    
    -- Application metadata
    loan_amount DECIMAL(15,2),
    loan_purpose VARCHAR(100),
    processing_time_ms INTEGER,                   -- Performance tracking
    
    -- Indexing for performance
    CONSTRAINT valid_status CHECK (status IN ('pending', 'processing', 'approved', 'rejected', 'review', 'error')),
    CONSTRAINT valid_decision CHECK (decision IS NULL OR decision IN ('approve', 'reject', 'review'))
);

-- Model predictions and inference history
CREATE TABLE IF NOT EXISTS application_ops.model_predictions (
    id BIGSERIAL PRIMARY KEY,
    application_id UUID REFERENCES application_ops.loan_applications(application_id) ON DELETE CASCADE,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    prediction_result JSONB NOT NULL,             -- Full model output
    feature_values JSONB,                         -- Input features used
    confidence_score DECIMAL(5,4),
    inference_time_ms INTEGER,                    -- Performance tracking
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Ensure we can track model performance over time
    CONSTRAINT positive_inference_time CHECK (inference_time_ms > 0)
);

-- Application processing pipeline state
CREATE TABLE IF NOT EXISTS application_ops.processing_pipeline (
    id BIGSERIAL PRIMARY KEY,
    application_id UUID REFERENCES application_ops.loan_applications(application_id) ON DELETE CASCADE,
    stage VARCHAR(50) NOT NULL,                   -- data_validation, feature_engineering, model_inference, etc.
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    stage_data JSONB,                            -- Stage-specific metadata
    
    CONSTRAINT valid_pipeline_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    UNIQUE(application_id, stage)
);

-- ================================================================================
-- AUDIT LOGS SCHEMA
-- ================================================================================

-- API request/response audit trail
CREATE TABLE IF NOT EXISTS audit_logs.api_requests (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID DEFAULT gen_random_uuid(),
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    user_id VARCHAR(100),
    ip_address INET,
    user_agent TEXT,
    request_headers JSONB,
    request_body JSONB,
    response_status INTEGER,
    response_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_http_method CHECK (method IN ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'))
);

-- Data access audit (for compliance)
CREATE TABLE IF NOT EXISTS audit_logs.data_access (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,           -- table, file, endpoint
    resource_id VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL,                  -- read, write, delete, export
    sensitive_data_accessed BOOLEAN DEFAULT FALSE,
    access_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Model decisions audit (for explainability and compliance)
CREATE TABLE IF NOT EXISTS audit_logs.decision_audit (
    id BIGSERIAL PRIMARY KEY,
    application_id UUID NOT NULL,
    decision_made VARCHAR(20) NOT NULL,
    decision_factors JSONB,                       -- Key factors that influenced decision
    human_reviewer VARCHAR(100),                  -- If reviewed by human
    compliance_flags JSONB,                       -- Any compliance concerns
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ================================================================================
-- SYSTEM CONFIGURATION SCHEMA
-- ================================================================================

-- Application configuration and feature flags
CREATE TABLE IF NOT EXISTS system_config.app_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(255) UNIQUE NOT NULL,
    config_value JSONB NOT NULL,
    description TEXT,
    environment VARCHAR(50) DEFAULT 'production',
    is_active BOOLEAN DEFAULT TRUE,
    created_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Model configuration and hyperparameters
CREATE TABLE IF NOT EXISTS system_config.model_config (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    version VARCHAR(50) NOT NULL,
    config_data JSONB NOT NULL,                   -- Model hyperparameters, thresholds, etc.
    is_active BOOLEAN DEFAULT FALSE,
    performance_metrics JSONB,                    -- Validation metrics
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(model_name, version)
);

-- Alert thresholds and monitoring configuration
CREATE TABLE IF NOT EXISTS system_config.alert_config (
    id SERIAL PRIMARY KEY,
    alert_name VARCHAR(100) UNIQUE NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    threshold_value DECIMAL(10,4),
    comparison_operator VARCHAR(10),              -- >, <, >=, <=, =
    is_enabled BOOLEAN DEFAULT TRUE,
    alert_recipients TEXT[],                      -- Email addresses
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ================================================================================
-- MODEL OPERATIONS SCHEMA
-- ================================================================================

-- Model deployment history and versioning
CREATE TABLE IF NOT EXISTS model_operations.deployment_history (
    id BIGSERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    version VARCHAR(50) NOT NULL,
    deployment_type VARCHAR(50) DEFAULT 'production', -- staging, production, canary
    deployed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deployed_by VARCHAR(100) NOT NULL,
    rollback_version VARCHAR(50),                 -- Previous version for rollback
    status VARCHAR(50) DEFAULT 'active',
    deployment_notes TEXT,
    performance_baseline JSONB,                   -- Expected performance metrics
    
    CONSTRAINT valid_deployment_status CHECK (status IN ('active', 'inactive', 'rolled_back', 'failed'))
);

-- Model performance monitoring
CREATE TABLE IF NOT EXISTS model_operations.model_metrics (
    id BIGSERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    version VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,           -- accuracy, precision, recall, auc, etc.
    metric_value DECIMAL(10,6),
    metric_metadata JSONB,                       -- Additional context
    measurement_window VARCHAR(50),              -- daily, hourly, real-time
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- A/B test tracking for model experiments
CREATE TABLE IF NOT EXISTS model_operations.ab_experiments (
    id SERIAL PRIMARY KEY,
    experiment_name VARCHAR(100) UNIQUE NOT NULL,
    model_a_version VARCHAR(50) NOT NULL,
    model_b_version VARCHAR(50) NOT NULL,
    traffic_split_percent INTEGER DEFAULT 50,    -- Percentage to model B
    start_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    end_date TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    success_metric VARCHAR(100),                 -- Primary metric to optimize
    results JSONB,                              -- Experiment results
    
    CONSTRAINT valid_traffic_split CHECK (traffic_split_percent BETWEEN 0 AND 100)
);

-- ================================================================================
-- PERFORMANCE INDEXES
-- ================================================================================

-- Application operations indexes
CREATE INDEX IF NOT EXISTS idx_loan_applications_status ON application_ops.loan_applications(status);
CREATE INDEX IF NOT EXISTS idx_loan_applications_created_at ON application_ops.loan_applications(created_at);
CREATE INDEX IF NOT EXISTS idx_loan_applications_risk_score ON application_ops.loan_applications(risk_score);
CREATE INDEX IF NOT EXISTS idx_model_predictions_application_id ON application_ops.model_predictions(application_id);
CREATE INDEX IF NOT EXISTS idx_model_predictions_model_version ON application_ops.model_predictions(model_name, model_version);
CREATE INDEX IF NOT EXISTS idx_processing_pipeline_application_id ON application_ops.processing_pipeline(application_id);

-- Audit logs indexes
CREATE INDEX IF NOT EXISTS idx_api_requests_created_at ON audit_logs.api_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_api_requests_endpoint ON audit_logs.api_requests(endpoint);
CREATE INDEX IF NOT EXISTS idx_data_access_user_id ON audit_logs.data_access(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_decision_audit_application_id ON audit_logs.decision_audit(application_id);

-- System config indexes
CREATE INDEX IF NOT EXISTS idx_app_config_active ON system_config.app_config(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_model_config_active ON system_config.model_config(model_name, is_active) WHERE is_active = TRUE;

-- Model operations indexes
CREATE INDEX IF NOT EXISTS idx_deployment_history_model_status ON model_operations.deployment_history(model_name, status);
CREATE INDEX IF NOT EXISTS idx_model_metrics_recorded_at ON model_operations.model_metrics(model_name, recorded_at);

-- ================================================================================
-- INITIAL CONFIGURATION DATA
-- ================================================================================

-- Insert default system configurations
INSERT INTO system_config.app_config (config_key, config_value, description, created_by) VALUES
('max_concurrent_applications', '100', 'Maximum number of applications to process simultaneously', 'system'),
('default_risk_threshold', '0.7', 'Default risk score threshold for loan approval', 'system'),
('feature_flags', '{"enable_real_time_scoring": true, "enable_explainable_ai": true}', 'Application feature flags', 'system'),
('data_retention_days', '2555', 'Number of days to retain operational data (7 years)', 'system')
ON CONFLICT (config_key) DO NOTHING;

-- Insert default alert configurations
INSERT INTO system_config.alert_config (alert_name, metric_name, threshold_value, comparison_operator, alert_recipients) VALUES
('high_rejection_rate', 'daily_rejection_rate', 0.8, '>', ARRAY['ops-team@company.com']),
('low_model_confidence', 'average_confidence', 0.6, '<', ARRAY['ml-team@company.com']),
('processing_time_spike', 'avg_processing_time_ms', 5000, '>', ARRAY['platform-team@company.com'])
ON CONFLICT (alert_name) DO NOTHING;

-- ================================================================================
-- TRIGGERS FOR AUTO-UPDATING TIMESTAMPS
-- ================================================================================

-- Function to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add triggers for timestamp updates
CREATE TRIGGER update_loan_applications_updated_at BEFORE UPDATE
    ON application_ops.loan_applications FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_app_config_updated_at BEFORE UPDATE
    ON system_config.app_config FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ================================================================================
-- COMMENTS FOR DOCUMENTATION
-- ================================================================================

COMMENT ON SCHEMA application_ops IS 'Operational data for loan application processing and decisions';
COMMENT ON SCHEMA audit_logs IS 'Audit trails for compliance and security monitoring';
COMMENT ON SCHEMA system_config IS 'System configuration and feature management';
COMMENT ON SCHEMA model_operations IS 'ML model deployment, monitoring, and experimentation';

COMMENT ON TABLE application_ops.loan_applications IS 'Core operational state for each loan application';
COMMENT ON TABLE application_ops.model_predictions IS 'ML model inference results and metadata';
COMMENT ON TABLE audit_logs.api_requests IS 'HTTP API request/response audit trail';
COMMENT ON TABLE system_config.model_config IS 'ML model configuration and hyperparameters';
COMMENT ON TABLE model_operations.deployment_history IS 'Model deployment versioning and rollback history';

-- Grant appropriate permissions
GRANT USAGE ON SCHEMA application_ops TO ops_admin;
GRANT USAGE ON SCHEMA audit_logs TO ops_admin;
GRANT USAGE ON SCHEMA system_config TO ops_admin;
GRANT USAGE ON SCHEMA model_operations TO ops_admin;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA application_ops TO ops_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA audit_logs TO ops_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA system_config TO ops_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA model_operations TO ops_admin;

GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA application_ops TO ops_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA audit_logs TO ops_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA system_config TO ops_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA model_operations TO ops_admin;