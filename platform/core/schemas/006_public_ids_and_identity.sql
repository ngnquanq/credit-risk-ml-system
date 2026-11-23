-- ADR-0014: opaque application ids for every URL, and applicant personal data kept apart.
-- applicant_identity is NOT in the Debezium publication (only loan_applications is), so names,
-- citizen ids and phone numbers never reach Kafka, Flink, ClickHouse or the feature store.

ALTER TABLE loan_applications ADD COLUMN IF NOT EXISTS public_id UUID NOT NULL DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS ux_loan_applications_public_id ON loan_applications(public_id);

CREATE TABLE IF NOT EXISTS applicant_identity (
    id               BIGSERIAL PRIMARY KEY,
    customer_ref     VARCHAR(255) NOT NULL UNIQUE,  -- internal customer key (loan_applications.sk_id_curr)
    citizen_id_hmac  CHAR(64)     NOT NULL UNIQUE,  -- HMAC-SHA256 with a separate key: exact-match lookup only
    full_name_enc    TEXT         NOT NULL,         -- envelope-encrypted (AES-256-GCM), see services/loan-api/src/identity
    citizen_id_enc   TEXT         NOT NULL,
    phone_enc        TEXT         NOT NULL,
    citizen_id_last3 CHAR(3)      NOT NULL,         -- for masked display only
    phone_last3      CHAR(3)      NOT NULL,
    key_id           VARCHAR(16)  NOT NULL,         -- KEK that wrapped the data keys (rotation)
    created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
