# ADR-0014: Applicant personal data is kept apart and encrypted; URLs carry opaque ids only

## Status

Accepted

## Date

2026-11-22

## Context

Applying for a loan means proving who you are, so the portals now collect each applicant's full name, citizen ID number (CCCD) and mobile phone, plus photos of both sides of the ID card. Until now the platform stored none of these. It addressed applications by `sk_id_curr`, a sequential key from the Kaggle dataset that applicants even had to type in.

Three problems followed:
- `/applications/100417` is enumerable, and its key joins every operational, streaming and warehouse table.
- `/apply?amount=40000000&term=24` puts loan amounts in browser history, proxy logs and Referer headers.
- Raw personal data would flow wherever `loan_applications` flows: the Debezium CDC to Kafka, Flink, ClickHouse and the feature store.

We asked the security and data-engineering sources in the project notebook:
- *Practical Cybersecurity Architecture*
- *Fundamentals of Data Engineering*
- *Building Secure and Reliable Systems* ch. 12 and 14
- the OWASP Key Management and Secrets Management cheat sheets

They agree on the following:
- **Collect only what a purpose needs.** In the words of *Fundamentals of Data Engineering*, "Data cannot leak if it is never collected."
- Keep identity data out of analytics.
- Encrypt it with envelope encryption, and use a keyed hash for exact-match lookups.
- Mask it in user interfaces and logs.
- Unmask it only for whoever works the case.
- Retain documents no longer than needed.
- Never put identifiers in URLs, logs, audit details or model features.

The sources say nothing about Vietnamese law. That includes Decree 13/2023/NĐ-CP on personal data protection, the Law on Identification, and the State Bank's rules on keeping credit files.

## Decision

**What is stored, and where.**

| Data | Where | Why |
|---|---|---|
| Full name, citizen ID, phone | `applicant_identity`, one row per customer, each field encrypted | KYC, the loan contract, contacting the customer, fraud checks |
| HMAC-SHA256 of the citizen ID (separate key) | `applicant_identity.citizen_id_hmac`, unique | Finding a returning customer without decrypting anything |
| Last three digits of the citizen ID and phone | `applicant_identity` | Masked display only |
| ID card photos, payslips | Object storage, key `<HMAC of uploader>/<folder>/doc_<random>.<ext>` | Verification; the object key never names the person |
| Gender, ethnicity, religion | Not asked | Not needed (ADR-0013, E6) |

- `applicant_identity` is not part of the Debezium publication. Names, citizen IDs and phones therefore never reach Kafka, Flink, ClickHouse, Feast or a model.
- Model features stay derived: income, amounts, dates and bureau aggregates.

**Encryption.**
- Each value gets its own AES-256-GCM data key. That key is wrapped by a key-encryption key (KEK) taken from a keyring.
- The field name is authenticated data, so a ciphertext cannot be copied into another column.
- The keyring `APP_PII_KEKS` is `"k2:<key>,k1:<key>"`: the first key encrypts, and older keys can only decrypt. Each token records which KEK wrapped its data key, so keys can be rotated without downtime.
- Lookups use a separate key, `APP_PII_HMAC_KEY`.
- The keys come from Kubernetes Secrets (`make k8s-secrets`). Moving them into a KMS or HSM is a follow-up.

**Customer key.**
- The API resolves `sk_id_curr` from the citizen ID's HMAC.
- A returning customer keeps their key, and with it their history. A new customer gets a new numeric key in a range the historical data never uses.
- A form can never overwrite an existing identity; correcting one is a verified staff task.
- The data model allows one application per customer, so a second application gets `409` with a message that leaks nothing.

**Opaque ids.**
- Every application has a random `public_id` (UUIDv4).
- All routes, responses, audit entries and portal URLs use only `public_id`. `sk_id_curr` never leaves the API.
- Malformed, unknown and other people's ids all get the same `404` or `403`.
- The portals show a short reference, `HS-` plus the first 8 hex digits.

**No personal data or amounts in URLs.**
- The estimator's amount and term travel to `/apply` as a server-side draft behind the httpOnly `__Host-draft` cookie (30 minutes).
- Lookups by citizen ID are `POST /api/v1/customers:lookup` with the number in the body.
- The reason language comes from `Accept-Language`, not a query parameter.

**Masking and reveal.**
- Responses carry the name and the masked citizen ID and phone (`••• ••• ••• 789`).
- The full numbers come only from `POST /api/v1/applications/{id}/identity:reveal`, with a reason of at least 10 characters. It is allowed for:
  - the loan officer who entered the application;
  - an underwriter while the application is in manual review.
- The reveal is audited with the reason, never the values. The response is `Cache-Control: no-store`, and the portal keeps the values in component memory only.
- Auditors see the audited reveal, never the numbers. A two-person break-glass path for anyone else is a follow-up.

**Documents.**
- Browsers upload straight to storage with a presigned POST policy. The policy pins the object key and the content type (JPEG, PNG or PDF), and caps the size at 10 MB.
- The portal CSP allows exactly that storage origin in `connect-src`.
- On submission the API checks that each document id carries the caller's own HMAC prefix and that the object exists.
- Self-service applications must include both sides of the ID card. At a branch the officer checks the physical card.
- Objects expire after 90 days through a bucket lifecycle rule.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| Store nothing; verify identity in a separate KYC vendor | Least data held | No contract or contact data; no returning-customer match; out of scope for the portfolio |
| Plain columns in `loan_applications` with disk encryption only | Simplest | Personal data in CDC, Kafka, the warehouse and every backup in clear; a DB read is a breach |
| Unsalted SHA-256 of the citizen ID for lookup | No key to manage | 12-digit numbers are brute-forced in seconds |
| Signed or encrypted sequential ids instead of UUIDs | Keeps numeric ids | More code; a key to manage; no benefit over a random id |
| Amount and term in the URL, signed | No server state | Still in history and logs; the values are visible even if they cannot be changed |

## Consequences

### Positive

- A dump of the operational database, the warehouse or the event log reveals no names, citizen IDs or phones.
- URLs are not enumerable and carry no personal or financial data.
- Every look at full numbers has a who, when and why in the audit trail.

### Negative

- Reading a name costs a decryption, and the API needs two more secrets.
- One application per customer is a limitation inherited from the data model; supporting several is a follow-up (an application key distinct from the customer key).
- Older links with numeric ids stop working; this is intended.

### Risks

- **Retention periods are a business and legal decision the sources do not cover.** The 90-day document expiry and the indefinite identity retention must be confirmed against Vietnamese regulations before production.
- Someone who submits another person's citizen ID would be matched to that person's customer key. Mitigations:
  - the officer verifies the ID photos;
  - the 409 response is generic;
  - rate limiting the public ingress (T01) is the remaining control.
- A lost KEK makes identities unreadable. KEKs need the same backup and rotation discipline as database credentials (OWASP Key Management).
