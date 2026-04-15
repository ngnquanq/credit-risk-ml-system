# Codebase Concerns

**Analysis Date:** 2026-04-15

## Tech Debt

**Hardcoded Prediction Threshold:**
- Issue: Prediction threshold of 0.3 is hardcoded in training and scoring, with no runtime knob for A/B testing or business rule adjustments
- Files: `application/training/train_register.py` (line 204), `application/scoring/config.py` (line 38, default=0.3), `application/domain/entities/loan_application.py` (line 31, default=0.5 in evaluate_worthiness)
- Impact: Cannot adjust decision boundary without retraining and redeploying models. No feature flag or A/B testing framework. Threshold mismatch between domain layer (0.5) and inference layer (0.3) invites bugs.
- Fix approach: Externalize threshold to a configuration service or environment variable with safe defaults. Store per-model-version threshold in MLflow artifact (feast_metadata.yaml already includes it). Add confidence interval or business metrics-driven threshold selection.

**No Cross-Validation in Training:**
- Issue: `train_register.py` trains on simple 80/20 split without cross-validation, hyperparameter tuning, or grid search
- Files: `application/training/train_register.py` (lines 115-117)
- Impact: Risk of overfitting, single-split bias, no statistical confidence in metrics. Cannot compare multiple hyperparameter sets. Model may degrade on production distributions not represented in test set.
- Fix approach: Implement stratified k-fold cross-validation (k=5). Add GridSearchCV or RandomizedSearchCV for hyperparameter tuning. Log CV fold metrics to MLflow. Consider validation curve analysis.

**Hardcoded Feature Set:**
- Issue: Model features are hardcoded in `train_register.py` (lines 65-90) as a 24-feature list. No version tracking between training notebook and production script.
- Files: `application/training/train_register.py`, `notebook/*.ipynb` (notebooks not directly synced)
- Impact: Notebooks may use different features than production. No feature versioning or schema evolution. Dead code if features are added to Flink but not to training.
- Fix approach: Store feature list in a shared config file or Feast registry (feature_store.yaml). Generate FEATURES list dynamically from Feast metadata at startup. Version feature sets alongside models in MLflow.

**Missing Drift Monitoring:**
- Issue: No data drift, concept drift, or schema evolution monitoring in place. Features are generated in Flink and streamed to Redis with no validation.
- Files: `application/flink/jobs/cdc_application_etl.py`, `application/flink/jobs/bureau_aggregation_etl.py`, `application/feast_repo/stream_processor.py`, `application/scoring/service.py`
- Impact: Feature distributions may shift without alerting ops. New categorical values in production data will cause silent failures or unexpected model behavior. Scoring service may crash on schema changes.
- Fix approach: Add schema registry enforcement (use Confluent Schema Registry Avro). Implement feature statistics monitoring (mean, std, nulls) in Feast stream processor. Add data quality assertions before materializing to Redis. Monitor prediction distributions (calibration).

**Feast Feature Views Have Hardcoded TTLs:**
- Issue: Feature views use fixed TTL (1-7 days) without SLA alignment to application requirements
- Files: `application/feast_repo/feature_views.py` (lines 160-182)
- Impact: 1-day TTL on application features may not align with scoring SLA (sub-10 minutes). Stale features in Redis cause "under-review" decisions. No gradual stale cutoff.
- Fix approach: Make TTLs environment-configurable. Define per-feature-view SLAs based on business risk. Implement feature freshness tracking in stream_processor.py.

**Flink CDC Job Has Brittle Date Handling:**
- Issue: `cdc_application_etl.py` and UDFs in `cdc_udfs.py` handle date parsing with generic try-catch blocks, risking silent failures
- Files: `application/flink/jobs/cdc_application_etl.py` (lines 206-208), `application/flink/jobs/cdc_udfs.py`
- Impact: Malformed dates (e.g., year 2500 from corrupt data) produce NULL features. Model receives unexpected NULL columns and predicts "under-review".
- Fix approach: Add explicit date validation (reasonable ranges: birth 1900-2020, employment 1980-now). Log schema validation errors with sample data. Implement DLQ for unparseable records.

## Known Bugs

**Feature Coordinate Race Condition:**
- Symptoms: Occasionally scoring fails with "under-review" even though all 3 feature sources were written to Redis. Feature_ready signal is lost.
- Files: `application/feast_repo/stream_processor.py` (lines 280-304, batch flusher), `application/scoring/service.py` (lines 354-367, fetch_features_from_feast)
- Trigger: High message rate (>150 RPS) during batch timeout window. If batch_timeout_sec expires while a thread is batching, Lua script coordination can miss updates.
- Workaround: Restart feast-stream-processor pod. Increase FEAST_BATCH_TIMEOUT_MS (default 300ms) to 1000ms.
- Root cause: Stream processor uses 3 separate batch buffers with no atomic coordination. Lua script relies on SET with TTL but doesn't acquire locks. Under high concurrency, one thread completes flush before another starts, violating the "wait for all 3" contract.
- Fix approach: Replace per-source buffering with single batch buffer keyed by sk_id_curr. Use Redis INCR with atomic checks for "3 sources ready". Add feature readiness gauge metric to Prometheus.

**DWH Consumer TODO Comment (Schema Mismatch):**
- Symptoms: DWH consumer sometimes publishes partial or misaligned features. Scoring service logs warnings about missing 10+ features.
- Files: `application/entrypoints/feature_consumer.py` (line 14, "Todo: some problem with the table schema, remember that we are querying from mart tables")
- Trigger: After dbt mart tables are refreshed or schema changes in application_mart database.
- Workaround: Manually query mart tables in ClickHouse to verify schema. Restart feature-consumer pod.
- Root cause: DWH consumer uses `get_table_columns(tbl)` with cached schema (lines 77-85). If mart tables are recreated, schema cache is stale.
- Fix approach: Invalidate schema cache on consumer startup or add TTL. Add schema validation step before publishing to Kafka. Log schema mismatches with full record for debugging.

**Inconsistent Error Handling in Bureau Aggregation:**
- Symptoms: Occasionally Flink bureau aggregation job fails silently and stops producing to hc.application_ext. Data flow halts.
- Files: `application/flink/jobs/bureau_aggregation_udfs.py` (lines 68-74, error JSON return), `application/flink/jobs/bureau_aggregation_etl.py`
- Trigger: Malformed JSON in raw data (non-UTF8 bytes from previous consumer failure). Flink job hangs on parse error.
- Workaround: Restart Flink job. Replay from earliest offset.
- Root cause: UDF returns error JSON instead of failing task. Flink does not propagate errors. JSON parser sees error object instead of feature object downstream.
- Fix approach: Add error sink (DLQ topic). Make UDF throw exception (Flink native error handling). Add explicit Flink error handler for sinks.

## Security Considerations

**Default/Placeholder Credentials in Config:**
- Risk: `application/core/config.py` has placeholder defaults: `ops_secure_password`, `bureau_secure_password`, `dwh_password`, `minioadmin`. If env vars not set, app uses defaults.
- Files: `application/core/config.py` (lines 51-102)
- Current mitigation: Kubernetes secrets are used in production. Local dev uses Docker Compose with env vars. No validation that secrets are non-default.
- Recommendations: Add startup validation that checks critical passwords are not defaults. Fail fast if OPS_DB_PASSWORD == "ops_secure_password". Use Kubernetes SecretProviderClass to inject secrets at runtime.

**MinIO Credentials in Environment:**
- Risk: MinIO access key and secret key are read from environment variables and passed to Minio client at startup. Secrets visible in pod env during debugging.
- Files: `application/entrypoints/api/main.py` (lines 84-89), `application/core/config.py` (minio_access_key, minio_secret_key)
- Current mitigation: Docker image secrets are not committed to git. .gitignore includes .env files.
- Recommendations: Use Kubernetes SecretProviderClass or ExternalSecrets operator. Remove secrets from startup logs (currently logged in settings printout). Rotate MinIO credentials regularly.

**No Kafka Message Authentication/Encryption:**
- Risk: Kafka brokers are unencrypted plaintext connections. Customer loan data (sk_id_curr, amounts, documents) flows through unencrypted topics.
- Files: All Kafka consumers and producers: `application/entrypoints/bureau_consumer.py`, `application/entrypoints/feature_consumer.py`, `application/flink/jobs/*`, `application/feast_repo/stream_processor.py`
- Current mitigation: Running on private Kubernetes network (network segmentation).
- Recommendations: Enable Kafka TLS. Add SASL authentication. Encrypt messages before Kafka (end-to-end). Run Kafka brokers on private network only.

**ClickHouse Plaintext Password in Logs:**
- Risk: When ClickHouse client fails, error messages include password in connection string or logs.
- Files: `application/infrastructure/external/bureau_client.py`, `application/infrastructure/external/dwh_client_ch.py`
- Current mitigation: Loggers filter credentials (loguru configured). Connection strings use f-strings.
- Recommendations: Use Pydantic settings with SecretStr type. Redact passwords in error messages. Rotate ClickHouse credentials regularly.

## Performance Bottlenecks

**Feast Redis Online Store Throughput Under Load:**
- Problem: Feature stream processor writes to Redis using micro-batches (200 records, 300ms timeout). At 150 RPS with 3 sources (450 writes/sec), Redis socket throughput may saturate.
- Files: `application/feast_repo/stream_processor.py` (lines 310-330, batch flush logic)
- Cause: Single Redis connection (feast-redis:6379, IO threads=4) handles all 3 sources' writes. Lua script coordination adds latency.
- Improvement path: Increase Redis replica count. Shard Feast Redis by sk_id_curr prefix (hash). Reduce batch_timeout from 300ms to 100ms. Measure Redis latency with Prometheus metrics (mean/p99 write time).

**Flink Bureau Aggregation UDF CPU Cost:**
- Problem: `_transform_bureau_data()` in `bureau_aggregation_udfs.py` computes 60+ features from raw bureau arrays. High CPU for large bureau histories (1000+ records per customer).
- Files: `application/flink/jobs/bureau_aggregation_udfs.py` (lines 77-300+, aggregation logic)
- Cause: Nested loops over bureau + balance records. No optimization for common cases.
- Improvement path: Pre-aggregate in ClickHouse (push-down computation). Cache common aggregates. Parallelize UDF via Flink parallelism setting. Profile CPU with Flamegraph.

**ClickHouse Query Latency for Bureau/DWH Consumers:**
- Problem: Bureau and DWH consumers query ClickHouse for each application (~50ms latency). At 50 RPS, this blocks async loop.
- Files: `application/entrypoints/bureau_consumer.py` (lines 162-168, concurrency control), `application/entrypoints/feature_consumer.py`
- Cause: ThreadPoolExecutor(max_workers=20) with Semaphore(20) means max 50 RPS. Beyond that, queuing adds latency.
- Improvement path: Increase thread pool to 50. Pre-cache frequent customers in Redis. Batch ClickHouse queries (IN operator). Move to ClickHouse async driver.

## Fragile Areas

**Kafka Topic Schema Evolution:**
- Files: `application/feast_repo/feature_views.py` (dynamic schema loading via `infer_application_fields()`), `application/feast_repo/generate_schemas_from_kafka.py`
- Why fragile: Schema is inferred from Kafka topic sample. If schema changes (new field added), old Flink jobs continue producing old schema. Feast validator fails downstream.
- Safe modification: Before changing Kafka schema, update all producers (Flink jobs, consumers). Run schema registry to enforce schema compatibility. Test schema changes in staging first.
- Test coverage: No integration tests for schema evolution. Manual testing only.

**Feast Stream Processor Batch Coordination:**
- Files: `application/feast_repo/stream_processor.py` (lines 280-380)
- Why fragile: Three separate batch buffers (app_features, external, dwh) coordinate via Redis Lua script. If one source is slow or fails, others block waiting for coordination.
- Safe modification: Add feature readiness timeout (e.g., 60 seconds max wait). Implement fallback to "proceed with available features" mode. Test with network delays using toxiproxy.
- Test coverage: Unit tests for batch logic exist. No chaos engineering for network partitions.

**Flink CDC Job Debezium Envelope Parsing:**
- Files: `application/flink/jobs/cdc_application_etl.py` (lines 62-123), `application/flink/jobs/cdc_udfs.py`
- Why fragile: CDC job assumes Debezium JSON format with `payload.after` structure. If Debezium configuration changes or CDC source changes, parsing breaks silently.
- Safe modification: Add explicit schema validation. Test CDC envelope parsing with real Debezium output. Add DLQ for unparseable messages. Version CDC schema in feature_store.yaml.
- Test coverage: Unit tests for CDC parsing exist. Integration tests with real Debezium missing.

**MinIO Presigned URL Expiration:**
- Files: `application/entrypoints/api/main.py` (lines 84-100, MinIO client setup), `application/frontend/utils.py` (document upload)
- Why fragile: Presigned URLs expire (default 7 days). If upload takes >7 days, URL fails. Frontend retry logic does not handle all edge cases.
- Safe modification: Use longer URL expiry (30 days). Implement refresh token rotation for long-lived uploads. Add exponential backoff for retry. Test with clock skew (NTP offset).
- Test coverage: No tests for URL expiration. Manual testing only.

**Feast Feature Service Dynamic Discovery:**
- Files: `application/scoring/service.py` (lines 501-589, dynamic feature discovery at startup)
- Why fragile: Feature service is dynamically built from Feast registry at scoring service startup. If Feast is unavailable, startup hangs (no timeout).
- Safe modification: Add startup timeout (30 seconds). Implement feature discovery caching. Fall back to hardcoded feature list if Feast unavailable. Add readiness probe that checks feature freshness.
- Test coverage: No tests for Feast unavailability. Startup fails if Feast registry is broken.

## Scaling Limits

**Feast Redis Single Instance Bottleneck:**
- Current capacity: Redis 7 with 1 instance, 4 IO threads. Handles ~300 concurrent connections.
- Limit: At 150 RPS with 3 sources writing micro-batches, Redis throughput may saturate at 200-300 RPS (depending on record size and network latency).
- Scaling path: Add Redis cluster (3 nodes). Implement Redis pipelining for batch writes. Shard by customer ID. Monitor with redis_exporter Prometheus metrics (commands/sec, latency).

**Flink Task Slots:**
- Current capacity: Flink cluster with 1 TaskManager, 4 task slots. Supports ~4 concurrent Flink jobs.
- Limit: Adding new ETL jobs (e.g., risk score aggregation, compliance checks) requires more slots. Each job needs parallelism (default 1, can scale to 4).
- Scaling path: Add more TaskManagers. Increase TaskManager memory (currently 2GB default). Use Flink autoscaling if available. Monitor with Flink metrics (total/available slots).

**ClickHouse Single Instance:**
- Current capacity: ClickHouse 25.6 with 1 server, 4 CPU cores, 16GB RAM. Supports ~50 concurrent queries.
- Limit: Bureau and DWH consumers each issue queries per message. At 50 RPS, 100 concurrent queries saturates single instance.
- Scaling path: Add ClickHouse replicas (2-3 nodes) with load balancing. Shard tables by sk_id_curr. Implement query result caching (Memcached). Pre-aggregate frequently accessed data.

## Dependencies at Risk

**XGBoost Version Pin:**
- Risk: Training uses sklearn's XGBClassifier, which is pinned to a specific XGBoost version. If version becomes unmaintained or incompatible with newer sklearn, retraining breaks.
- Impact: Cannot upgrade sklearn/scikit-learn without testing XGBoost compatibility. Model serialization (joblib/pickle) may be incompatible across versions.
- Migration plan: Use ONNX export for model portability. Test XGBoost upgrade path. Document minimum sklearn/XGBoost versions. Pin in requirements.txt with range (e.g., xgboost>=1.5,<2.0).

**Feast Version Compatibility:**
- Risk: Feast 0.40.1 is used but newer versions (0.47+) have breaking API changes (KafkaSource constructor, batch_source parameter).
- Impact: Code has try-except fallbacks in `feature_views.py` (lines 66-80) for version compatibility. This is brittle and may mask bugs.
- Migration plan: Test upgrade to Feast 0.47 or later. Remove try-except fallbacks after upgrade. Use DataSourceV3 API if available.

**Confluent Kafka Version:**
- Risk: confluent-kafka Python library is used but version is not pinned. New versions may change Consumer/Producer API.
- Impact: No retry/backoff logic in consumers. Burst message failures cause pod restarts.
- Migration plan: Pin confluent-kafka to minimum version (e.g., >=1.7.0). Test upgrade path. Consider migrating to aiokafka for better async support.

**PyFlink Stability:**
- Risk: PyFlink (1.17) is used for Flink CDC and bureau aggregation. PyFlink has lower community adoption than Scala Flink.
- Impact: Bug fixes and features lag Scala. Documentation is sparse. Community support is limited.
- Migration plan: Test PyFlink 1.18+ for stability. Consider rewriting critical jobs (CDC ETL) in Scala if critical path. Monitor PyFlink GitHub issues for blocking bugs.

## Missing Critical Features

**No Feature Monitoring/Observability:**
- Problem: No metrics for feature freshness, nulls, data quality. Stream processor batch sizes are not tracked.
- Blocks: Cannot diagnose feature starvation issues. No alerting for schema changes or missing features.
- Solution: Add Prometheus metrics for batch size, latency, feature nulls. Implement data profiling in stream_processor.py. Add dashboards in Grafana.

**No Model Retraining Trigger:**
- Problem: Model is trained manually. No automated retraining on data drift or scheduled cadence.
- Blocks: Cannot adapt to concept drift. Manual process is error-prone.
- Solution: Implement Airflow/Prefect DAG for scheduled retraining (weekly). Add data drift detection (Evidently/Great Expectations) to trigger retraining. Automate model promotion (MLflow transition to Staging/Production).

**No A/B Testing Framework:**
- Problem: Cannot test new models or features safely. No comparison of old vs new thresholds.
- Blocks: Cannot measure impact of model updates. Risk of regression undetected.
- Solution: Implement traffic splitting (Flagger/Istio). Log predictions from both models for offline comparison. Build Bayesian experiment framework (e.g., via custom Prometheus queries).

**No Dead Letter Queue for Failed Predictions:**
- Problem: Flink jobs silently drop failed records. Bureau aggregation errors are logged but not exported.
- Blocks: Cannot replay or investigate failures. Data loss undetected.
- Solution: Add explicit DLQ topics (hc.application_ext_raw.dlq, hc.application_features.dlq). Implement error metrics per failure type. Build alerting on DLQ growth.

## Test Coverage Gaps

**No Cross-Validation Testing:**
- Untested area: Hyperparameter stability across different data splits. Feature importance consistency.
- Files: `application/training/train_register.py` (no CV loop), test files missing CV assertions
- Risk: Model may overfit to specific train/test split. No confidence intervals on metrics.
- Priority: HIGH - affects model stability and regulatory compliance (need reproducible results).

**No Flink CDC Integration Tests:**
- Untested area: Real Debezium CDC envelope parsing. Date transformation UDFs with edge cases (leap years, null values, extreme dates).
- Files: `tests/` has no CDC tests. `application/flink/jobs/cdc_application_etl.py`, `cdc_udfs.py` untested.
- Risk: Silent data corruption (wrong dates, missing features). Breaks production scoring.
- Priority: HIGH - critical path from database to scoring.

**No Feast Stream Processor End-to-End Tests:**
- Untested area: Batch coordination logic (all 3 sources ready). Lua script atomicity. Redis connection failure handling.
- Files: `application/feast_repo/stream_processor.py` has no e2e tests. `tests/` has unit tests only.
- Risk: Race condition bugs like "feature_ready lost under load" go undetected. Causes silent "under-review" decisions.
- Priority: HIGH - core to feature materialization.

**No Scoring Service Feature Validation Tests:**
- Untested area: Feature mapping from Feast names to model columns. Missing feature handling. Feast unavailability fallback.
- Files: `application/scoring/service.py` (lines 212-368) has no tests. `tests/` lacks scoring integration.
- Risk: Mismatch between model columns and Feast features. Silent prediction failures.
- Priority: MEDIUM - blocks production scoring service.

**No Bureau Aggregation Feature Correctness Tests:**
- Untested area: 60+ feature calculations. Edge cases (empty bureau, all overdue, null ext_source). Correctness against manual calculation.
- Files: `application/flink/jobs/bureau_aggregation_udfs.py` has unit tests. No property-based tests for correctness.
- Risk: Feature values are incorrect but within expected ranges. Model makes bad decisions silently.
- Priority: MEDIUM - impacts loan approval decisions.

**No Load/Stress Tests for 150 RPS Target:**
- Untested area: End-to-end latency at target SLA (sub-10 minutes). Feature store throughput under sustained load. Flink backpressure behavior.
- Files: `tests/test_load/` has Locust tests but may not simulate realistic distributions.
- Risk: Hitting scaling limits in production. SLA breaches undetected until production impact.
- Priority: MEDIUM - validates infrastructure readiness.

---

*Concerns audit: 2026-04-15*
