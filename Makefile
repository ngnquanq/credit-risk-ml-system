.PHONY: help up down logs health deploy

# Home Credit ML Platform - Organized Docker Services
NETWORK_NAME := hc-network
COMPOSE_FILE := ./services/docker-compose.yml

# Core service files
CORE_COMPOSE := ./services/core/docker-compose.yml

# Data platform service files
DATA_STORAGE_COMPOSE := ./services/data/docker-compose.storage.yml
DATA_WAREHOUSE_COMPOSE := ./services/data/docker-compose.warehouse.yml
DATA_STREAMING_COMPOSE := ./services/data/docker-compose.streaming.yml
DATA_CDC_COMPOSE := ./services/data/docker-compose.cdc.yml
DATA_BATCH_COMPOSE := ./services/data/docker-compose.batch.yml

# ML platform service files
ML_FEATURE_STORE_COMPOSE := ./services/ml/docker-compose.feature-store.yml
ML_REGISTRY_COMPOSE := ./services/ml/docker-compose.registry.yml
ML_SERVING_COMPOSE := ./services/ml/docker-compose.serving.yml
ML_BATCH_COMPOSE := ./services/ml/docker-compose.batch.yml

# Operations service files
OPS_DASHBOARD_COMPOSE := ./services/ops/docker-compose.dashboard.yml
OPS_GATEWAY_COMPOSE := ./services/ops/docker-compose.gateway.yml
OPS_ORCHESTRATION_COMPOSE := ./services/ops/docker-compose.orchestration.yml

MINIKUBE_PROFILE ?= mlops
MINIKUBE_DRIVER ?= docker
MINIKUBE_K8S_VERSION ?= v1.28.3
MINIKUBE_CPUS ?= 16
MINIKUBE_MEMORY ?= 20000
MINIKUBE_DISK ?= 80g
K8S_CONTEXT ?= $(MINIKUBE_PROFILE)
EXECUTE_K8S_APPLY ?= false

PYTHON := python

help: ## Show this help message
	@echo "Home Credit ML Platform - Docker Services"
	@echo ""
	@echo "Full Platform Commands:"
	@echo "  up              - Start all services"
	@echo "  down            - Stop all services"
	@echo "  logs            - View all service logs"
	@echo ""
	@echo "Category Commands (Docker Compose):"
	@echo "  up-core                  - Start core infrastructure (Postgres, API, MinIO)"
	@echo "  up-data                  - Start data platform (Kafka, ClickHouse, Flink, CDC)"
	@echo "  up-operation             - Start operations (ELK, Prometheus, Superset, socat)"
	@echo "  fix-dbt-permissions      - Fix ml_data_mart permissions for Airflow containers"
	@echo "  fix-airflow-permissions  - Fix Airflow DAGs/logs permissions for local editing"
	@echo ""
	@echo "Kubernetes ML Platform Commands:"
	@echo "  k8s-up                     - Start Minikube profile (mlops) with addons"
	@echo "  k8s-ml-platform            - Deploy complete ML platform (one-off command)"
	@echo "  k8s-training-data-storage  - Deploy training data storage (MinIO)"
	@echo "  k8s-kubeflow               - Deploy Kubeflow Pipelines"
	@echo "  k8s-ray                    - Deploy Ray cluster for hyperparameter tuning"
	@echo "  k8s-model-registry         - Deploy MLflow model registry"
	@echo "  k8s-kserve                 - Deploy KServe serving infrastructure"
	@echo "  k8s-mlflow-watcher         - Deploy MLflow watcher (auto Bento builds)"
	@echo "  k8s-model-serving          - Deploy model serving (bundle storage + watcher)"
	@echo "  k8s-feature-registry       - Deploy Feast feature registry"
	@echo "  k8s-monitoring             - Deploy Prometheus + Grafana monitoring"
	@echo "  k8s-logging                - Deploy EFK logging stack"
	@echo "  k8s-automation             - Deploy Jenkins automation server for CI/CD"
	@echo ""
	@echo "Utility Commands:"
	@echo "  create-network            - Create platform network"
	@echo "  core-apply-migrations     - Apply core DB migrations (idempotent)"
	@echo "  core-reset-db             - Drop and recreate core DB (destructive)"

# Network management
create-network: ## Create the platform network
	docker network create $(NETWORK_NAME) || true

# Full platform management
up: create-network ## Start all services
	docker compose -f $(COMPOSE_FILE) up -d

down: ## Stop all services
	docker compose -f $(COMPOSE_FILE) down

logs: ## View logs from all services
	docker compose -f $(COMPOSE_FILE) logs -f

restart: ## Restart all services
	docker compose -f $(COMPOSE_FILE) restart

# Category-based deployment
up-core: create-network ## Start core infrastructure services
	@docker compose --env-file services/core/.env.core -f services/core/docker-compose.operationaldb.yml -f services/core/docker-compose.api.yml -f ./services/data/docker-compose.storage.yml up -d
	@echo "Waiting for PostgreSQL to be ready..."
	@until docker exec ops_postgres pg_isready -U ops_admin -d operations > /dev/null 2>&1; do sleep 2; echo -n "."; done
	@echo " PostgreSQL ready!"

core-apply-migrations: ## Apply core DB migrations into running ops-postgres
	@echo "Applying core migrations to ops_postgres..."
	@until docker exec ops_postgres pg_isready -U ops_admin -d operations > /dev/null 2>&1; do sleep 2; echo -n "."; done
	@docker exec -i ops_postgres psql -U ops_admin -d operations -f /migrations/001_create_loan_applications.sql || true
	@docker exec -i ops_postgres psql -U ops_admin -d operations -f /migrations/002_create_application_status_log.sql || true
	@echo "✅ Core migrations applied"

core-reset-db: ## Destructive: reset core DB volume and re-init with migrations
	@echo "This will remove ops-postgres volume and reinitialize the database."
	@cd services && docker compose --env-file .env.core -f core/docker-compose.operationaldb.yml -f core/docker-compose.api.yml down -v
	@$(MAKE) up-core
	@$(MAKE) core-apply-migrations

up-data: create-network
	 docker compose --env-file services/data/.env.data \
	   --env-file services/core/.env.core \
	   -f services/data/docker-compose.warehouse.yml \
	   -f services/data/docker-compose.streaming.yml \
	   -f services/data/docker-compose.cdc.yml \
	   up -d
	 python ./services/data/scripts/kafka/create_topics.py || true
	 bash ./services/data/scripts/dwh/ch_load_internal.sh
	 bash ./services/data/scripts/dwh/ch_load_external.sh
	 cd ml_data_mart/ && dbt debug --project-dir . --profiles-dir . && dbt run --project-dir . --profiles-dir . --target gold && cd ..
	 docker compose --env-file services/data/.env.data \
		-f services/data/docker-compose.query-services.yml up -d 
	docker compose --env-file services/data/.env.data \
		-f services/data/docker-compose.flink.yml up -d

fix-dbt-permissions: ## Fix permissions for ml_data_mart (for Airflow containers)
	@bash services/ops/scripts/orchestration/helper/fix-dbt-permissions.sh

fix-airflow-permissions: ## Fix permissions for Airflow orchestration directories (DAGs, logs, etc.)
	@bash services/ops/scripts/orchestration/helper/fix-airflow-permissions.sh

trigger-export-dag: ## Trigger ClickHouse to MinIO export DAG
	@echo "Triggering clickhouse_to_minio_export DAG..."
	docker exec airflow-scheduler airflow dags trigger clickhouse_to_minio_export

up-operation:
	@echo "Fixing dbt permissions for Airflow containers..."
	@bash services/ops/scripts/orchestration/helper/fix-dbt-permissions.sh
	@echo "Fixing Airflow permissions for DAGs and logs..."
	@bash services/ops/scripts/orchestration/helper/fix-airflow-permissions.sh
	docker compose -f services/ops/docker-compose.logging.yml up -d
	docker compose -f services/ops/docker-compose.monitoring.yml up -d
	docker compose -f services/ops/docker-compose.dashboard.yml up -d
	docker compose -f services/ops/docker-compose.gateway.yml up -d
	docker compose --env-file services/ops/.env.ops -f services/ops/docker-compose.orchestration.yml up -d
	docker compose --env-file services/ops/.env.ops -f services/ops/docker-compose.automation.yml up -d

k8s-up: ## Start Minikube profile for ML platform (with addons)
	minikube start -p $(MINIKUBE_PROFILE) --kubernetes-version=$(MINIKUBE_K8S_VERSION) --driver=$(MINIKUBE_DRIVER) --cpus=$(MINIKUBE_CPUS) --memory=$(MINIKUBE_MEMORY) --disk-size=$(MINIKUBE_DISK)
	minikube -p $(MINIKUBE_PROFILE) addons enable ingress
	minikube -p $(MINIKUBE_PROFILE) addons enable metallb
	minikube -p $(MINIKUBE_PROFILE) addons enable metrics-server

k8s-training-data-storage: ## Deploy training data storage (MinIO for versioned training datasets)
	@echo "Deploying training data storage..."
	kubectl create ns training-data || true
	helm upgrade --install training-minio ./services/ml/k8s/training-data-storage -n training-data \
		-f services/ml/k8s/training-data-storage/minio.values.yaml
	@echo "✅ Training data storage deployed (namespace: training-data)"
	@echo "Load sample data: docker exec clickhouse_dwh clickhouse-client -q \"SET s3_truncate_on_insert=1; INSERT INTO FUNCTION s3('http://172.18.0.1:31900/training-data/snapshots/ds=2025-09-19/loan_applications.csv','minioadmin','minioadmin','CSVWithNames') SELECT a.*, t.TARGET FROM application_mart.mart_application AS a INNER JOIN application_mart.mart_application_train AS t ON a.SK_ID_CURR = t.SK_ID_CURR\""

k8s-kubeflow: ## Deploy Kubeflow Pipelines for training orchestration
	@echo "Deploying Kubeflow Pipelines v2.14.3..."
	@export PIPELINE_VERSION=2.14.3 && \
		kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/cluster-scoped-resources?ref=$$PIPELINE_VERSION" && \
		kubectl wait --for condition=established --timeout=60s crd/applications.app.k8s.io && \
		kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/dev?ref=$$PIPELINE_VERSION" && \
		kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/platform-agnostic?ref=$$PIPELINE_VERSION"
	@echo "Patching MinIO deployment with valid image..."
	@kubectl patch deployment minio -n kubeflow --type='json' -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/image", "value":"minio/minio:RELEASE.2024-01-01T16-36-33Z"}]' || true
	@echo "Removing GCP-specific proxy-agent (not needed for on-prem)..."
	@kubectl delete deployment proxy-agent -n kubeflow --ignore-not-found=true
	@echo "Waiting for Kubeflow Pipelines components to be ready (this may take several minutes)..."
	@echo "✅ Kubeflow Pipelines deployed"
	@echo "Port-forward: kubectl port-forward -n kubeflow svc/ml-pipeline-ui 8080:80"

k8s-ray: ## Deploy Ray cluster for distributed hyperparameter tuning
	@echo "Deploying Ray cluster (1 head + 2 workers)..."
	kubectl create ns ray || true
	helm upgrade --install kuberay-operator ./services/ml/k8s/kuberay-operator \
		-n ray -f services/ml/k8s/kuberay-operator/values.yaml
	kubectl apply -f services/ml/k8s/kuberay-operator/raycluster.yaml
	@echo "✅ Ray cluster deployed (namespace: ray)"
	@echo "Check status: kubectl get raycluster -n ray"

k8s-model-registry: ## Deploy MLflow model registry with Postgres + MinIO backend
	@echo "Deploying MLflow model registry..."
	kubectl create ns model-registry || true
	helm upgrade --install minio services/ml/k8s/model-registry/minio -n model-registry \
		-f services/ml/k8s/model-registry/minio/values.internal.yaml
	helm upgrade --install mlflow ./services/ml/k8s/model-registry/ -n model-registry \
		-f services/ml/k8s/model-registry/values.internal.yaml
	@echo "✅ MLflow registry deployed (namespace: model-registry)"
	@echo "Port-forward: kubectl port-forward -n model-registry svc/mlflow 5000:5000"

k8s-kserve: ## Deploy KServe for model serving infrastructure
	@echo "Deploying KServe (cert-manager + CRDs + main components)..."
	kubectl create ns kserve || true
	@echo "Installing cert-manager..."
	kubectl apply -f services/ml/k8s/kserve/cert-manager.yaml
	@echo "Waiting for cert-manager webhook to be ready (this may take 60-90s)..."
	kubectl wait --for=condition=available --timeout=120s deployment/cert-manager-webhook -n cert-manager || true
	kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=webhook -n cert-manager --timeout=120s
	@echo "✅ cert-manager ready"
	@echo ""
	@echo "Installing KServe standard components..."
	kubectl apply -f services/ml/k8s/kserve/standard-install.yaml
	@echo ""
	@echo "Installing KServe CRDs..."
	cd services/ml/k8s/kserve/kserve-crd && (helm install kserve-crd . -n kserve 2>/dev/null || echo "kserve-crd already installed")
	@echo "Waiting for CRDs to be established..."
	@sleep 10
	@echo ""
	@echo "Installing KServe main components (creates Certificate and Issuer)..."
	cd services/ml/k8s/kserve/kserve-main && (helm install kserve . -n kserve 2>/dev/null || echo "kserve already installed")
	@echo "Waiting for certificate to be issued and controller to be ready..."
	@sleep 20
	@kubectl wait --for=condition=available --timeout=120s deployment/kserve-controller-manager -n kserve || true
	@echo ""
	@echo "Deploying bento-builder ConfigMap..."
	kubectl apply -f services/ml/k8s/kserve/bento-builder/configmap.yaml
	@echo "Configuring Kafka DNS resolution for scoring pods..."
	kubectl apply -f services/ml/k8s/kserve/kafka-broker-service.yaml
	@echo "✅ KServe deployed (namespace: kserve)"

k8s-mlflow-watcher: ## Deploy MLflow watcher (auto-triggers Bento builds on model promotion)
	@echo "Deploying MLflow watcher..."
	kubectl apply -f services/ml/k8s/mlflow-watcher/rbac.yaml
	kubectl -n model-registry apply \
		-f services/ml/k8s/mlflow-watcher/poller-values.yaml \
		-f services/ml/k8s/mlflow-watcher/poller-configmap.yaml \
		-f services/ml/k8s/mlflow-watcher/builder-configmap.yaml \
		-f services/ml/k8s/mlflow-watcher/deployment.yaml
	kubectl -n model-registry rollout status deploy/mlflow-watcher
	@echo "✅ MLflow watcher deployed (namespace: model-registry)"

k8s-model-serving: ## Deploy model serving components (bundle storage + serving watcher)
	@echo "Deploying model serving components..."
	kubectl create ns model-serving || true
	@echo "Note: Create DockerHub credentials secret if needed:"
	@echo "  kubectl create secret generic dockerhub-creds --from-literal=username=YOUR_USERNAME --from-literal=password=YOUR_PASSWORD -n model-serving"
	cd services/ml/k8s/model-serving/bundle-storage && \
		helm upgrade --install serving-minio . -n model-serving -f values.internal.yaml
	kubectl apply -f services/ml/k8s/model-serving/watcher-rbac.yaml
	kubectl apply -f services/ml/k8s/model-serving/watcher-configmap.yaml
	kubectl apply -f services/ml/k8s/model-serving/watcher-deployment.yaml
	kubectl rollout restart -n model-serving deployment/serving-watcher
	@echo "✅ Model serving deployed (namespace: model-serving)"

k8s-feature-registry: ## Deploy Feast feature registry + Redis online store
	@echo "Deploying Feast feature registry..."
	kubectl create ns feature-registry || true
	@echo "Note: Build and push Feast repo image first:"
	@echo "  docker build ./application/feast_repo/ -t ngnquanq/feast-repo:v15"
	@echo "  docker push ngnquanq/feast-repo:v15"
	kubectl apply -k ./services/ml/k8s/feature-store/
	@echo "✅ Feast feature registry deployed (namespace: feature-registry)"

k8s-monitoring: ## Deploy Prometheus + Grafana monitoring stack
	@echo "Deploying monitoring stack (Prometheus + Grafana + cAdvisor)..."
	kubectl create namespace monitoring || true
	cd services/ops/k8s/monitoring && \
		helm upgrade --install kube-prometheus-stack ./kube-prometheus-stack \
		-n monitoring \
		-f kube-prometheus-stack/values.custom.yaml
	kubectl apply -f services/ops/k8s/monitoring/kube-prometheus-stack/docker-cadvisor-servicemonitor.yaml
	@echo "✅ Monitoring stack deployed (namespace: monitoring)"
	@echo "Port-forward Grafana: kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80"
	@echo "Default credentials: admin/prom-operator"

k8s-logging: ## Deploy EFK logging stack (Elasticsearch + Filebeat + Kibana)
	@echo "Deploying EFK logging stack..."
	kubectl create ns logging || true
	@echo "Installing Elasticsearch..."
	cd services/ops/k8s/logging/elastic-stack && \
		helm upgrade --install elasticsearch ./elasticsearch -n logging -f elasticsearch-values.custom.yaml
	kubectl create secret generic elasticsearch-master-credentials -n logging \
		--from-literal=username=elastic --from-literal=password=changeme || true
	@echo "Waiting for Elasticsearch to be ready..."
	@sleep 30
	@echo "Installing Kibana..."
	cd services/ops/k8s/logging/elastic-stack && \
		helm upgrade --install kibana ./kibana -n logging -f kibana-values.custom.yaml --no-hooks
	@echo "Installing Filebeat..."
	cd services/ops/k8s/logging/elastic-stack && \
		helm upgrade --install filebeat ./filebeat -n logging -f filebeat-values.custom.yaml
	@echo "✅ EFK logging stack deployed (namespace: logging)"
	@echo "Port-forward Kibana: kubectl port-forward -n logging svc/kibana-kibana 5601:5601"

k8s-automation: ## Deploy Jenkins automation server for CI/CD
	@echo "Deploying Jenkins automation server..."
	kubectl create ns automation || true
	cd services/ops/k8s/automation && \
		helm upgrade --install jenkins ./jenkins \
		-n automation \
		-f jenkins-values.custom.yaml
	@echo "Waiting for Jenkins to be ready..."
	@kubectl wait --for=condition=available --timeout=300s deployment/jenkins -n automation || true
	@echo "✅ Jenkins deployed (namespace: automation)"
	@echo "Port-forward: kubectl port-forward -n automation svc/jenkins 8080:8080"
	@echo "Default credentials: admin / jenkins-admin-password (⚠️ Change in production!)"

k8s-ml-platform: ## Deploy complete ML platform (one-off setup: training storage, Kubeflow, Ray, registry, KServe, watchers, Feast, monitoring, logging)
	@echo "========================================="
	@echo "Deploying Complete ML Platform to K8s"
	@echo "========================================="
	@echo ""
	@echo "Step 1/10: Training data storage..."
	@if $(MAKE) k8s-training-data-storage; then \
		echo "✅ Step 1/10 complete"; \
	else \
		echo "❌ Step 1/10 failed - aborting deployment"; \
		exit 1; \
	fi
	@echo ""
	@echo "Step 2/10: Kubeflow Pipelines..."
	@if $(MAKE) k8s-kubeflow; then \
		echo "✅ Step 2/10 complete"; \
	else \
		echo "❌ Step 2/10 failed - aborting deployment"; \
		exit 1; \
	fi
	@echo ""
	@echo "Step 3/10: Ray cluster..."
	@if $(MAKE) k8s-ray; then \
		echo "✅ Step 3/10 complete"; \
	else \
		echo "❌ Step 3/10 failed - aborting deployment"; \
		exit 1; \
	fi
	@echo ""
	@echo "Step 4/10: MLflow model registry..."
	@if $(MAKE) k8s-model-registry; then \
		echo "✅ Step 4/10 complete"; \
	else \
		echo "❌ Step 4/10 failed - aborting deployment"; \
		exit 1; \
	fi
	@echo ""
	@echo "Step 5/10: KServe serving infrastructure..."
	@if $(MAKE) k8s-kserve; then \
		echo "✅ Step 5/10 complete"; \
	else \
		echo "❌ Step 5/10 failed - aborting deployment"; \
		exit 1; \
	fi
	@echo ""
	@echo "Step 6/10: MLflow watcher..."
	@if $(MAKE) k8s-mlflow-watcher; then \
		echo "✅ Step 6/10 complete"; \
	else \
		echo "❌ Step 6/10 failed - aborting deployment"; \
		exit 1; \
	fi
	@echo ""
	@echo "Step 7/10: Model serving components..."
	@if $(MAKE) k8s-model-serving; then \
		echo "✅ Step 7/10 complete"; \
	else \
		echo "❌ Step 7/10 failed - aborting deployment"; \
		exit 1; \
	fi
	@echo ""
	@echo "Step 8/10: Feast feature registry..."
	@if $(MAKE) k8s-feature-registry; then \
		echo "✅ Step 8/10 complete"; \
	else \
		echo "❌ Step 8/10 failed - aborting deployment"; \
		exit 1; \
	fi
	@echo ""
	@echo "Step 9/10: Monitoring stack..."
	@if $(MAKE) k8s-monitoring; then \
		echo "✅ Step 9/10 complete"; \
	else \
		echo "❌ Step 9/10 failed - aborting deployment"; \
		exit 1; \
	fi
	@echo ""
	@echo "Step 10/10: Logging stack..."
	@if $(MAKE) k8s-logging; then \
		echo "✅ Step 10/10 complete"; \
	else \
		echo "❌ Step 10/10 failed - aborting deployment"; \
		exit 1; \
	fi
	@echo ""
	@echo "========================================="
	@echo "✅ ML Platform Deployment Complete!"
	@echo "========================================="
	@echo ""
	@echo "Port-forwarding commands:"
	@echo "  MLflow:     kubectl port-forward -n model-registry svc/mlflow 5000:5000"
	@echo "  Kubeflow:   kubectl port-forward -n kubeflow svc/ml-pipeline-ui 8080:80"
	@echo "  Grafana:    kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80"
	@echo "  Kibana:     kubectl port-forward -n logging svc/kibana-kibana 5601:5601"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Build & push Feast repo image: docker build ./application/feast_repo/ -t ngnquanq/feast-repo:v15 && docker push ngnquanq/feast-repo:v15"
	@echo "  2. Create DockerHub secret: kubectl create secret generic dockerhub-creds --from-literal=username=YOUR_USER --from-literal=password=YOUR_PASS -n model-serving"
	@echo "  3. Load training data: See output from k8s-training-data-storage"
	@echo "  4. Submit training pipeline: Upload services/ml/k8s/training-pipeline/training_pipeline.yaml to Kubeflow UI"

## =========================================
## Jenkins CI/CD Automation
## =========================================

up-jenkins: ## Start Jenkins CI/CD server (Docker Compose)
	@echo "Starting Jenkins automation server..."
	docker compose -f services/ops/docker-compose.automation.yml up -d
	@echo "Waiting for Jenkins to initialize..."
	@sleep 30
	@echo "✅ Jenkins running at http://localhost:8071"
	@echo ""
	@echo "Initial admin password:"
	@docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword 2>/dev/null || echo "Jenkins still initializing, try: docker logs jenkins"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Open http://localhost:8071 and complete setup wizard"
	@echo "  2. Install suggested plugins"
	@echo "  3. Create Multibranch Pipeline job pointing to services/ops/scripts/automation/jenkinsfiles/flink-cicd.Jenkinsfile"

down-jenkins: ## Stop Jenkins server
	@echo "Stopping Jenkins..."
	docker compose -f services/ops/docker-compose.automation.yml down
	@echo "✅ Jenkins stopped"

jenkins-logs: ## View Jenkins logs
	docker logs -f jenkins

jenkins-validate: ## Run Flink validation checks locally (mimics Jenkins)
	@echo "Running validation checks (syntax only, no UDF tests)..."
	@python3 -m py_compile application/flink/jobs/cdc_application_etl.py
	@python3 -m py_compile application/flink/jobs/bureau_aggregation_etl.py
	@python3 -m py_compile application/flink/jobs/cdc_udfs.py
	@python3 -m py_compile application/flink/jobs/bureau_aggregation_udfs.py
	@echo "✅ All Flink jobs have valid syntax"

jenkins-build: ## Build Flink Docker image locally (mimics Jenkins)
	@echo "Building Flink Docker image..."
	@cd application/flink && docker build -t hc-flink-jobs:$(shell git rev-parse --short HEAD) .
	@echo "✅ Image built: hc-flink-jobs:$(shell git rev-parse --short HEAD)"
