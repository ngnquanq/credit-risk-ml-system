-- ================================================================================
-- Bureau Database Initialization Script
-- Purpose: Initialize database schema for external bureau credit data service
-- ================================================================================

-- Create extension for better query performance
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create basic tables for bureau credit data
CREATE TABLE IF NOT EXISTS bureau (
    sk_id_curr BIGINT NOT NULL,
    sk_id_bureau BIGINT NOT NULL,
    credit_active VARCHAR(50),
    credit_currency VARCHAR(50),
    days_credit INTEGER,
    credit_day_overdue INTEGER,
    days_credit_enddate DECIMAL(10,2),
    days_enddate_fact DECIMAL(10,2),
    amt_credit_max_overdue DECIMAL(15,2),
    cnt_credit_prolong INTEGER,
    amt_credit_sum DECIMAL(15,2),
    amt_credit_sum_debt DECIMAL(15,2),
    amt_credit_sum_limit DECIMAL(15,2),
    amt_credit_sum_overdue DECIMAL(15,2),
    credit_type VARCHAR(100),
    days_credit_update INTEGER,
    amt_annuity DECIMAL(15,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (sk_id_curr, sk_id_bureau)
);

CREATE TABLE IF NOT EXISTS bureau_balance (
    sk_id_bureau BIGINT NOT NULL,
    months_balance INTEGER NOT NULL,
    status VARCHAR(10),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (sk_id_bureau, months_balance)
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_bureau_sk_id_curr ON bureau(sk_id_curr);
CREATE INDEX IF NOT EXISTS idx_bureau_sk_id_bureau ON bureau(sk_id_bureau);
CREATE INDEX IF NOT EXISTS idx_bureau_balance_sk_id_bureau ON bureau_balance(sk_id_bureau);

-- Query log table for monitoring
CREATE TABLE IF NOT EXISTS query_log (
    id SERIAL PRIMARY KEY,
    request_id UUID DEFAULT uuid_generate_v4(),
    sk_id_curr BIGINT,
    query_type VARCHAR(50),
    source_channel VARCHAR(20), 
    processing_time_ms INTEGER,
    records_returned INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on query log
CREATE INDEX IF NOT EXISTS idx_query_log_sk_id_curr ON query_log(sk_id_curr);
CREATE INDEX IF NOT EXISTS idx_query_log_created_at ON query_log(created_at);

COMMENT ON DATABASE bureau_db IS 'External bureau credit data for Home Credit risk model';
COMMENT ON TABLE bureau IS 'Credit bureau data matching CSV structure';
COMMENT ON TABLE bureau_balance IS 'Bureau credit balance history';
COMMENT ON TABLE query_log IS 'API query performance and pattern tracking';

-- External normalized credit scores from third-party sources
CREATE TABLE IF NOT EXISTS external_score (
    sk_id_curr BIGINT PRIMARY KEY,
    ext_source_1 DECIMAL(9,6),
    ext_source_2 DECIMAL(9,6),
    ext_source_3 DECIMAL(9,6),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE external_score IS 'Normalized external credit scores (e.g., 0..1) for each sk_id_curr';
