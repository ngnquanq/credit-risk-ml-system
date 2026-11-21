-- E11: who entered an application, who it belongs to, and four-eyes policy changes.
ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS channel           VARCHAR(10) NOT NULL DEFAULT 'staff' CHECK (channel IN ('staff', 'self')),
    ADD COLUMN IF NOT EXISTS created_by_sub    VARCHAR(64),
    ADD COLUMN IF NOT EXISTS applicant_sub     VARCHAR(64),
    ADD COLUMN IF NOT EXISTS branch_id         VARCHAR(16),
    ADD COLUMN IF NOT EXISTS bureau_consent_at TIMESTAMP WITH TIME ZONE;
CREATE INDEX IF NOT EXISTS idx_loan_applications_applicant_sub ON loan_applications(applicant_sub);
CREATE INDEX IF NOT EXISTS idx_loan_applications_branch ON loan_applications(branch_id, created_at DESC);

CREATE TABLE IF NOT EXISTS policy_change (
    id          BIGSERIAL PRIMARY KEY,
    proposed_by VARCHAR(64) NOT NULL,
    approved_by VARCHAR(64),
    payload     JSONB NOT NULL,                -- {"approve_below": 0.25, "reject_above": 0.35}
    state       VARCHAR(12) NOT NULL CHECK (state IN ('proposed', 'active', 'rejected', 'expired', 'superseded')),
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    decided_at  TIMESTAMP WITH TIME ZONE,
    CHECK (approved_by IS NULL OR approved_by <> proposed_by)
);
