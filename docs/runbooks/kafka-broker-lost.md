# Kafka broker lost

**Notice.** Under-replicated partitions > 0, a broker pod not ready.

**What already happens.** With 3 brokers, RF 3 and `min.insync.replicas=2`, producers (`acks=all`) keep writing and consumers fail over. Nothing is lost while two brokers are up.

**Do.**
1. `kubectl get pods -n data-services -l app=kafka-broker`. Usually the StatefulSet restarts the pod by itself.
2. If its volume is damaged, delete the PVC of that broker only, then the pod. The broker rejoins and re-replicates.
3. If **two** brokers are down, writes stop (by design: no data loss). Restore one broker first.

**Confirm.** Under-replicated partitions back to 0; consumer lag for `decision-recorder` and the feature consumers returns to normal.
