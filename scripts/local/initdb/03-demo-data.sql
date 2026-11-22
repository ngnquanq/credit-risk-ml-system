-- Demo applications and decisions for trying the portals locally. Synthetic people only.
-- URLs use public_id (ADR-0014); sk_id_curr stays internal. Names, citizen IDs and phones are
-- encrypted with the local keys by generate.py and loaded from /generated/demo-identity.sql.
-- Owner ids match the demo users that scripts/local/generate.py puts into the local realms.
--   staff:     officer.hn01 = 11111111-1111-4111-8111-000000000001 (branch HN01)
--              officer.hcm02 = ...0002 (branch HCM02), underwriter = ...0003,
--              risk.manager1 = ...0004, risk.manager2 = ...0005, auditor = ...0006
--   customers: applicant.a@demo.local = 22222222-2222-4222-8222-000000000001
--              applicant.b@demo.local = ...0002

INSERT INTO loan_applications (sk_id_curr, public_id, birth_date, cnt_children, amt_income_total, amt_credit, amt_annuity,
    amt_goods_price, name_income_type, name_education_type, name_family_status, name_housing_type,
    employment_start_date, organization_type, channel, created_by_sub, applicant_sub, branch_id, bureau_consent_at)
VALUES
  -- Officer HN01, manual review with model reasons: the main demo case
  ('100002', 'f0155e69-6681-49e9-86c0-6c92e99d27c9', '1991-03-14', 0, 180000000, 40000000, 2035832, 40000000, 'Working', 'Higher education', 'Married',
   'House / apartment', '2025-06-01', 'Trade: type 7', 'staff', '11111111-1111-4111-8111-000000000001', NULL, 'HN01', now()),
  -- Officer HN01, approved automatically
  ('100533', '660d6fd8-0cb9-4aa2-b279-cfc342be4e9e', '1984-07-02', 2, 240000000, 25000000, 1272000, 25000000, 'State servant', 'Higher education', 'Married',
   'House / apartment', '2015-02-01', 'School', 'staff', '11111111-1111-4111-8111-000000000001', NULL, 'HN01', now()),
  -- Officer HCM02: another branch (officer.hn01 must be refused)
  ('100561', '425478cc-e1e9-4da2-a7f3-bf22ff734e3c', '1995-11-20', 1, 150000000, 30000000, 1527000, 28000000, 'Working', 'Secondary / secondary special',
   'Single / not married', 'With parents', '2023-09-15', 'Construction', 'staff', '11111111-1111-4111-8111-000000000002',
   NULL, 'HCM02', now()),
  -- Entered by the underwriter while covering a branch: separation of duties blocks their review
  ('100600', 'a1202dfb-1bf4-4942-9894-2523ea299667', '1988-01-30', 0, 200000000, 35000000, 1781000, 35000000, 'Commercial associate', 'Higher education',
   'Civil marriage', 'Rented apartment', '2019-05-01', 'Business Entity Type 3', 'staff',
   '11111111-1111-4111-8111-000000000003', NULL, 'HN01', now()),
  -- Self-service, applicant A, rejected with reasons
  ('100417', '4619a4eb-f94f-4fb9-ad3f-c28bb366caf6', '1999-08-08', 0, 120000000, 60000000, 3054000, 55000000, 'Working', 'Incomplete higher',
   'Single / not married', 'Rented apartment', '2026-05-01', 'Self-employed', 'self',
   '22222222-2222-4222-8222-000000000001', '22222222-2222-4222-8222-000000000001', NULL, now()),
  -- Self-service, applicant B (applicant A must not see it)
  ('100700', '88d3098b-e09e-42c6-a814-0259cc0185f7', '1979-12-12', 3, 300000000, 20000000, 1018000, 20000000, 'Pensioner', 'Secondary / secondary special',
   'Widow', 'House / apartment', NULL, 'XNA', 'self',
   '22222222-2222-4222-8222-000000000002', '22222222-2222-4222-8222-000000000002', NULL, now());

INSERT INTO application_status_log (sk_id_curr, status, created_by, event_id, metadata) VALUES
  ('100002', 'manual_review', 'decision-recorder', 'demo-100002', '{
     "band": "UNDER_REVIEW", "score": 0.31, "reasons": ["score_band"],
     "reason_codes": ["EXT_SCORE_LOW", "CREDIT_AMOUNT_HIGH", "EMPLOYMENT_LENGTH_SHORT"],
     "bands": {"approve_below": 0.25, "reject_above": 0.35},
     "contributions": {"EXT_SOURCE_2": 0.84, "AMT_CREDIT": 0.31, "DAYS_EMPLOYED": 0.22, "BUREAU_DEBT_TO_CREDIT_RATIO": 0.15,
                       "PREV_REFUSAL_RATE": 0.09, "AMT_ANNUITY": -0.05, "DAYS_BIRTH": -0.12, "EXT_SOURCE_3": -0.20},
     "explanation": {"base_value": -2.41, "margin": -0.8, "additive_ok": true},
     "model": "credit_risk_model", "model_version": "7", "feature_set_sha256": "3588abb0743bd500"}'),
  ('100533', 'approved', 'decision-recorder', 'demo-100533', '{
     "band": "APPROVE", "score": 0.08, "reasons": ["score_band"], "reason_codes": [],
     "bands": {"approve_below": 0.25, "reject_above": 0.35}, "model_version": "7"}'),
  ('100561', 'manual_review', 'decision-recorder', 'demo-100561', '{
     "reasons": ["features_incomplete"], "missing_groups": ["dwh"]}'),
  ('100600', 'manual_review', 'decision-recorder', 'demo-100600', '{
     "band": "UNDER_REVIEW", "score": 0.27, "reasons": ["score_band"], "reason_codes": ["INSTALMENT_HIGH"],
     "bands": {"approve_below": 0.25, "reject_above": 0.35},
     "contributions": {"AMT_ANNUITY": 0.41, "EXT_SOURCE_2": -0.10}, "model_version": "7"}'),
  ('100417', 'rejected', 'decision-recorder', 'demo-100417', '{
     "band": "REJECT", "score": 0.52, "reasons": ["score_band"],
     "reason_codes": ["EXT_SCORE_LOW", "EMPLOYMENT_LENGTH_SHORT", "CREDIT_AMOUNT_HIGH"],
     "bands": {"approve_below": 0.25, "reject_above": 0.35},
     "contributions": {"EXT_SOURCE_1": 0.9, "DAYS_EMPLOYED": 0.5, "AMT_CREDIT": 0.3}, "model_version": "7"}'),
  ('100700', 'approved', 'decision-recorder', 'demo-100700', '{
     "band": "APPROVE", "score": 0.11, "reasons": ["score_band"], "reason_codes": [], "model_version": "7"}');

INSERT INTO case_note (sk_id_curr, kind, text, author_sub) VALUES
  ('100002', 'note', 'Customer showed an employment contract from 06/2025; payslips for 3 months uploaded.',
   '11111111-1111-4111-8111-000000000001');

\i /generated/demo-identity.sql
