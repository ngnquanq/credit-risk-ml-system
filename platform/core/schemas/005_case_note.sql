-- ADR-0013: loan officers add verification notes and flag concerns; underwriters read them.
CREATE TABLE IF NOT EXISTS case_note (
    id         BIGSERIAL PRIMARY KEY,
    sk_id_curr VARCHAR(255) NOT NULL REFERENCES loan_applications(sk_id_curr) ON DELETE CASCADE,
    kind       VARCHAR(10)  NOT NULL CHECK (kind IN ('note', 'concern')),
    text       VARCHAR(1000) NOT NULL,
    author_sub VARCHAR(64)  NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_case_note_application ON case_note(sk_id_curr, created_at);
