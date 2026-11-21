# Database failover

**Notice.** CloudNativePG reports a new primary; API 5xx for under a minute; Debezium reconnecting.

**What already happens.** The replica is promoted and the `ops-db-rw` Service moves to it. The API and the decision recorder reconnect. A submit that was in flight can fail once; the portal retries once. The recorder commits Kafka offsets only after writing, so no decision is lost.

**Do.**
1. `kubectl get cluster ops-db -n data-services` and check `status.currentPrimary`.
2. Check the Debezium connector status. If it is `FAILED`, restart it. The replication slot is carried over by CloudNativePG.
3. Once the old primary is back as a replica, confirm replication lag (`cnpg_pg_replication_lag`) is near 0.

**If both instances are lost.** Run the restore procedure (`scripts/chaos/restore.sh` shows the steps) with the latest WAL. RPO is up to 5 minutes; record the window and tell credit operations, because applications in that window must be re-entered.
