# Scoring down

**Notice.** Alert on `decisions_total{reason="scoring_unavailable"}` rising, `hc.scoring.dlq` growing, or the review queue passing 50.

**What already happens.** The scoring sequence retries 3 times, then dead-letters the request. The decision recorder turns each dead letter into `manual_review` with reason `scoring_unavailable`. No application is approved.

**Do.**
1. `kubectl get inferenceservice -n kserve` and `kubectl describe` the newest revision. KServe keeps serving the last ready revision if a new one failed.
2. If the new model version is at fault, re-promote the previous version in MLflow (the watcher redeploys it).
3. If the online store (Feast/Redis) is down, restart it. The stream materialiser replays from Kafka.
4. Tell credit operations how many applications were routed to review (`SELECT count(*) FROM application_status_log WHERE metadata->'reasons' ? 'scoring_unavailable' AND created_at > <incident start>`).

**Confirm.** New applications get automated decisions again; the rate of `scoring_unavailable` decisions drops to 0.

**Do not** re-drive the scoring DLQ for applications already decided by an underwriter: the human decision stands.
