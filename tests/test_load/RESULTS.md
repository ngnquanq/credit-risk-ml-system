# Load-Tuning Results

## Outcome

The platform is not yet at the project SLA. CPU throttling was reduced for the first measured bottleneck, but the current limiter is non-CPU delivery through the Knative Sequence KafkaChannel into KServe.

Final measured soft cycle:

- Command: `USERS=10 SPAWN_RATE=2 RUN_TIME=3m SKIP_CLEANUP=1 ./tests/test_load/run_e2e_load_test.sh`
- Artifacts: `tests/test_load/reports/e2e_prediction_20260427_163045.*`
- Inserts: 5,458, 29.43 insert RPS, PostgreSQL p95 3 ms
- Delivery: `hc.feature_ready=5198`, `hc.scoring=912`, `hc.scoring.dlq=0`, scoring ratio 17.5%
- E2E p95: not valid for this cycle because old backlog was draining and no current submissions correlated inside the 3-minute window
- Primary lag: KafkaChannel subscriber group for `scoring-pipeline-kn-sequence-0`, not the `hc.feature_ready` KafkaSource group

## Resource Shape Kept

The only resource change kept from this investigation is ClickHouse:

- `platform/data/k8s/data-warehouse/01-clickhouse.yaml`
- CPU request: `1000m` -> `2000m`
- CPU limit: `2` -> `4`

This reduced ClickHouse CFS throttling from 85.9% to the 16-22% range. Further ClickHouse CPU may still help upstream throughput, but it is no longer the highest-value next knob because events now accumulate downstream in the scoring Sequence channel.

## Evidence Trail

- Cycle 0 proved ClickHouse was the first CPU ceiling: 85.9% throttled periods and 1556.28 throttled seconds during the baseline run.
- Cycle 1 proved raising ClickHouse CPU reduced throttling but did not improve scoring delivery.
- KafkaSource repair was required after a dispatcher restart left `feature-ready-source` `Ready=False`; deleting the stale generated internal `Consumer` recreated `kafka-source-dispatcher-0` contract resources and restored readiness.
- Cycle 2 showed `knative-scoring-consumer` consumed `hc.feature_ready` with zero lag, while the Sequence KafkaChannel subscriber group accumulated roughly 4k+ messages of lag.
- `kafka-channel-dispatcher` logged HTTP 502 responses from `credit-risk-v1-predictor`; KServe queue-proxy logged connection resets to the app container on `127.0.0.1:3000`.
- Temporarily scaling `kafka-channel-dispatcher` 1 -> 4 caused continuous consumer-group rebalancing and was rolled back.

## Harness Changes

- `tests/test_load/run_e2e_load_test.sh` now writes reports under `tests/test_load/reports` by default and captures start/end cAdvisor snapshots.
- `tests/test_load/capture_k8s_cycle_metrics.py` adds reusable pod-level CFS throttling, CPU, memory, and restart summaries.
- `tests/test_load/locustfile_e2e_prediction.py` now gives each worker prediction monitor a unique Kafka consumer group and returns DB connections to the pool on failures.

## Next Work

The next milestone should target the scoring Sequence delivery path, not another blind CPU bump:

- Add a dead-letter sink/delivery policy to the Sequence KafkaChannel subscriber so KServe 502s become visible in a topic instead of appearing as `hc.scoring` drops.
- Investigate why `credit-risk-v1-predictor` queue-proxy sees connection resets while the app container mostly logs 200 responses.
- Validate whether Knative Kafka 1.13.6 has a dispatcher scaling/configuration limitation for this channel path before using dispatcher replicas as a tuning lever.
- Run a clean cycle after channel/KServe delivery is fixed; `SKIP_CLEANUP=1` is no longer useful because the scoring channel has accumulated backlog.

