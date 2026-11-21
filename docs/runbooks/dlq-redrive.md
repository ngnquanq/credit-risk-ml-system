# Re-drive a dead-letter queue

**Notice.** `hc.decisions.dlq` (malformed decision events) or `hc.scoring.dlq` (scoring failures) has messages after an incident.

**`hc.scoring.dlq`.** Usually nothing to do: each message already produced a `manual_review` row. Re-drive only for applications still `submitted` (none should be):

```sql
SELECT la.sk_id_curr FROM loan_applications la
LEFT JOIN application_status_log s ON s.sk_id_curr = la.sk_id_curr
WHERE s.id IS NULL AND la.created_at > '<incident start>';
```

**`hc.decisions.dlq`.** These are events the recorder could not parse.
1. Read a sample: `kafka-console-consumer --topic hc.decisions.dlq --from-beginning --max-messages 5 --property print.headers=true`.
2. Fix the producer (scoring service event shape) first.
3. Re-publish the corrected events to `hc.scoring`. The recorder is idempotent on `event_id`, so a re-drive cannot create duplicates.

**Confirm.** Both DLQs drained; every application from the incident window has a terminal status.
