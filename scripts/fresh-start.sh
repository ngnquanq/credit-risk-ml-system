#!/bin/bash
set -e

echo "=============================================="
echo "  Fresh Start: Complete System Deployment"
echo "=============================================="
echo ""


# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Load environment variables from .env file
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    export $(cat .env | grep -v '^#' | xargs)
    echo "Environment variables loaded"
else
    echo -e "${YELLOW}Warning: .env file not found. Docker credentials will need to be set manually.${NC}"
fi

# ==============================================================================
# STEP 1: CREATE DOCKER NETWORK
# ==============================================================================
echo -e "${BLUE}[1/15] Creating Docker Network...${NC}"
docker network create --subnet=172.18.0.0/16 hc-network || echo "Network already exists"
echo -e "${GREEN} Network created${NC}\n"
sleep 2

# ==============================================================================
# STEP 2: SPIN UP CORE SERVICES (API + Operational Database + Storage)
# ==============================================================================
echo -e "${BLUE}[2/15] Starting Core Services (API, Postgres, MinIO)...${NC}"
docker compose --env-file ./services/core/.env.core \
    -f ./services/core/docker-compose.operationaldb.yml \
    -f ./services/core/docker-compose.api.yml \
    -f ./services/data/docker-compose.storage.yml \
    up -d

echo -e "${YELLOW}Waiting for core services to be ready (30s)...${NC}"
sleep 30
echo -e "${GREEN} Core services started${NC}\n"

# ==============================================================================
# STEP 3: SPIN UP CDC AND EVENT BUS (Kafka + Debezium)
# ==============================================================================
echo -e "${BLUE}[3/15] Starting CDC and Event Bus (Kafka + Debezium)...${NC}"
docker compose --env-file ./services/core/.env.core \
    --env-file ./services/data/.env.data \
    -f ./services/data/docker-compose.streaming.yml \
    -f ./services/data/docker-compose.cdc.yml \
    up -d

echo -e "${YELLOW}Waiting for Kafka and Debezium to be ready (60s)...${NC}"
sleep 60
echo -e "${GREEN} CDC and Event Bus started${NC}\n"

# ==============================================================================
# STEP 4: CREATE KAFKA TOPICS
# ==============================================================================
echo -e "${BLUE}[4/15] Creating Kafka Topics...${NC}"
python ./services/data/scripts/kafka/create_topics.py
echo -e "${GREEN} Kafka topics created${NC}\n"
sleep 5

# ==============================================================================
# STEP 5: SPIN UP DATA WAREHOUSE (ClickHouse + Query Services)
# ==============================================================================
echo -e "${BLUE}[5/15] Starting Data Warehouse (ClickHouse)...${NC}"
docker compose --env-file ./services/core/.env.core \
    --env-file ./services/data/.env.data \
    -f ./services/data/docker-compose.warehouse.yml \
    up -d

echo -e "${YELLOW}Waiting for ClickHouse to be ready (30s)...${NC}"
sleep 30
echo -e "${GREEN} Data Warehouse started${NC}\n"

# ==============================================================================
# STEP 6: LOAD DATA INTO CLICKHOUSE
# ==============================================================================
echo -e "${BLUE}[6/15] Loading Data into ClickHouse...${NC}"
echo "Loading internal data..."
bash ./services/data/scripts/dwh/ch_load_internal.sh

echo "Loading external data..."
bash ./services/data/scripts/dwh/ch_load_external.sh
echo -e "${GREEN} Data loaded into ClickHouse${NC}\n"

# ==============================================================================
# STEP 7: RUN DBT TRANSFORMATIONS
# ==============================================================================
echo -e "${BLUE}[7/15] Running dbt Transformations (Silver + Gold)...${NC}"
cd ml_data_mart/
dbt debug --project-dir . --profiles-dir .
dbt run --project-dir . --profiles-dir . --target gold
cd ..
echo -e "${GREEN} dbt transformations completed${NC}\n"

# ==============================================================================
# STEP 8: SPIN UP QUERY SERVICES
# ==============================================================================
echo -e "${BLUE}[8/15] Starting Query Services (DWH + External)...${NC}"
docker compose --env-file ./services/data/.env.data \
    -f ./services/data/docker-compose.query-services.yml \
    up -d

echo -e "${YELLOW}Waiting for query services (15s)...${NC}"
sleep 15
echo -e "${GREEN} Query services started${NC}\n"

# ==============================================================================
# STEP 9: SPIN UP FLINK
# ==============================================================================
echo -e "${BLUE}[9/15] Starting Flink and Submitting Jobs...${NC}"
docker compose --env-file ./services/data/.env.data \
    -f services/data/docker-compose.flink.yml \
    up -d

echo -e "${YELLOW}Waiting for Flink to be ready and jobs to submit (45s)...${NC}"
sleep 45
echo -e "${GREEN} Flink started and jobs submitted${NC}\n"

# ==============================================================================
# STEP 10: SPIN UP LOGGING AND MONITORING (Docker)
# ==============================================================================
echo -e "${BLUE}[10/15] Starting Logging and Monitoring (Filebeat, cAdvisor)...${NC}"
docker compose -f services/ops/docker-compose.logging.yml up -d
docker compose -f services/ops/docker-compose.monitoring.yml up -d
echo -e "${GREEN} Logging and monitoring started${NC}\n"
sleep 10

# ==============================================================================
# STEP 11: SPIN UP SUPERSET (BI Dashboard)
# ==============================================================================
echo -e "${BLUE}[11/15] Starting Superset (BI Dashboard)...${NC}"
docker compose -f services/ops/docker-compose.dashboard.yml up -d
echo -e "${YELLOW}Waiting for Superset (20s)...${NC}"
sleep 20
echo -e "${GREEN} Superset started${NC}\n"

# ==============================================================================
# STEP 12: CREATE MINIKUBE CLUSTER
# ==============================================================================
echo -e "${BLUE}[12/15] Creating Minikube Cluster...${NC}"
minikube start -p mlops --kubernetes-version=v1.28.3 --driver=docker \
    --cpus=20 --memory=20000 --disk-size=100g

echo "Enabling addons..."
minikube -p mlops addons enable ingress
minikube -p mlops addons enable metallb
minikube -p mlops addons enable metrics-server
echo -e "${GREEN} Minikube cluster created${NC}\n"

# ==============================================================================
# STEP 13: CREATE SOCAT GATEWAY (Docker K8s)
# ==============================================================================
echo -e "${BLUE}[13/15] Creating Socat Gateway (Docker K8s bridge)...${NC}"
docker compose -f services/ops/docker-compose.gateway.yml up -d
echo -e "${GREEN} Socat gateway created${NC}\n"
sleep 5

# ==============================================================================
# STEP 14: DEPLOY ML PLATFORM COMPONENTS (Kubernetes)
# ==============================================================================
echo -e "${BLUE}[14/15] Deploying ML Platform Components...${NC}"

# 14.1: Training Data Storage (MinIO)
echo "  Creating training-data namespace and deploying MinIO..."
kubectl create ns training-data || echo "Namespace already exists"
helm upgrade --install training-minio ./services/ml/k8s/training-data-storage -n training-data \
    -f services/ml/k8s/training-data-storage/minio.values.yaml
sleep 10

echo " Add data into training storage " 
docker exec clickhouse_dwh clickhouse-client -q "SET s3_truncate_on_insert=1; \
INSERT INTO FUNCTION s3('http://172.18.0.1:31900/training-data/snapshots/ds=2025-09-19/loan_applications.csv','minioadmin','minioadmin','CSVWithNames') \
SELECT a.*, t.TARGET \
FROM application_mart.mart_application AS a \
INNER JOIN application_mart.mart_application_train AS t \
ON a.SK_ID_CURR = t.SK_ID_CURR"
echo " Data added into training storage "
sleep 5

# 14.2: Kubeflow Pipelines
echo "  Installing Kubeflow Pipelines..."
export PIPELINE_VERSION=2.14.0
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/cluster-scoped-resources?ref=$PIPELINE_VERSION"
kubectl wait --for condition=established --timeout=60s crd/applications.app.k8s.io
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/platform-agnostic?ref=$PIPELINE_VERSION"
echo -e "${YELLOW}  Waiting for Kubeflow to be ready (120s)...${NC}"
sleep 120

# 14.3: Ray Cluster
echo "  Creating Ray Cluster..."
kubectl create ns ray || echo "Namespace already exists"
helm upgrade --install kuberay-operator ./services/ml/k8s/kuberay-operator \
    -n ray -f services/ml/k8s/kuberay-operator/values.yaml
sleep 10
kubectl apply -f services/ml/k8s/kuberay-operator/raycluster.yaml
sleep 20

# 14.4: Model Registry (MLflow)
echo "  Creating Model Registry (MLflow + MinIO + Postgres)..."
kubectl create ns model-registry || echo "Namespace already exists"
helm upgrade --install mlflow ./services/ml/k8s/model-registry/ -n model-registry \
    -f services/ml/k8s/model-registry/values.internal.yaml
helm upgrade --install minio services/ml/k8s/model-registry/minio -n model-registry \
    -f services/ml/k8s/model-registry/minio/values.internal.yaml
sleep 30

# 14.5: KServe
echo "  Installing KServe..."
kubectl create ns kserve || echo "Namespace already exists"
kubectl apply -f services/ml/k8s/kserve/cert-manager.yaml

echo -e "${YELLOW}  Waiting for cert-manager to be ready...${NC}"
# Wait for cert-manager deployments
kubectl wait --for=condition=Available --timeout=180s deployment/cert-manager -n cert-manager || echo "Cert-manager timeout"
kubectl wait --for=condition=Available --timeout=180s deployment/cert-manager-webhook -n cert-manager || echo "Cert-manager webhook timeout"
kubectl wait --for=condition=Available --timeout=180s deployment/cert-manager-cainjector -n cert-manager || echo "Cert-manager cainjector timeout"

echo "  Cert-manager pods ready, waiting 30s for webhook stabilization..."
sleep 30

kubectl apply -f services/ml/k8s/kserve/standard-install.yaml
echo -e "${YELLOW}  Waiting for KServe CRDs to be established...${NC}"
sleep 30

cd services/ml/k8s/kserve/kserve-crd
helm install kserve-crd . -n kserve || echo "KServe CRD already installed"
sleep 10

cd ../kserve-main
helm install kserve . -n kserve || echo "KServe already installed"
cd ../../../../..

echo -e "${YELLOW}  Waiting for kserve-webhook-server-cert secret to be created by cert-manager...${NC}"
# Wait up to 120 seconds for the secret to be created
for i in {1..24}; do
  if kubectl get secret kserve-webhook-server-cert -n kserve &>/dev/null; then
    echo "  kserve-webhook-server-cert secret found"
    break
  fi
  echo "  Waiting for kserve-webhook-server-cert secret... ($i/24)"
  sleep 5
done

sleep 10

# Apply bento-builder configmap (optional, may not be needed for all setups)
kubectl apply -f services/ml/k8s/kserve/bento-builder/configmap.yaml || echo "Bento-builder configmap not applied (optional)"

# 14.6: MLflow Watcher
echo "  Deploying MLflow Watcher..."
kubectl apply -f services/ml/k8s/mlflow-watcher/rbac.yaml
kubectl apply -n model-registry \
    -f services/ml/k8s/mlflow-watcher/poller-values.yaml \
    -f services/ml/k8s/mlflow-watcher/poller-configmap.yaml \
    -f services/ml/k8s/mlflow-watcher/builder-configmap.yaml \
    -f services/ml/k8s/mlflow-watcher/deployment.yaml
sleep 10

# 14.7: Model Serving Components
echo "  Deploying Model Serving Components..."
kubectl create ns model-serving || echo "Namespace already exists"

if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    export $(cat .env | grep -v '^#' | xargs)
    echo "Environment variables loaded"
else
    echo -e "${YELLOW}Warning: .env file not found. Docker credentials will need to be set manually.${NC}"
fi

# Create Docker credentials secret from .env file
if [ -n "$DOCKERHUB_USERNAME" ] && [ -n "$DOCKERHUB_PASSWORD" ]; then
    echo "  Creating dockerhub-creds secret from .env..."
    kubectl create secret generic dockerhub-creds \
      --from-literal=username="$DOCKERHUB_USERNAME" \
      --from-literal=password="$DOCKERHUB_PASSWORD" \
      -n model-serving \
      --dry-run=client -o yaml | kubectl apply -f -
    echo "  Docker credentials secret created"
else
    echo -e "${YELLOW}  Warning: DOCKERHUB_USERNAME or DOCKERHUB_PASSWORD not set in .env${NC}"
    echo -e "${YELLOW}  Manually create secret with:${NC}"
    echo -e "${YELLOW}    kubectl create secret generic dockerhub-creds \\${NC}"
    echo -e "${YELLOW}      --from-literal=username=YOUR_USERNAME \\${NC}"
    echo -e "${YELLOW}      --from-literal=password=YOUR_PASSWORD -n model-serving${NC}"
fi

# Deploy MinIO for BentoML bundles
cd services/ml/k8s/model-serving/bundle-storage
helm install serving-minio . -n model-serving -f values.internal.yaml || echo "Serving MinIO already installed"
cd ..
sleep 10

# Deploy Docker registry (for model images)
kubectl apply -f registry-deployment.yaml

# Deploy serving watcher (automation) - note: this watches the MinIO bucket above
# RBAC is in model-serving, but watcher code is in kserve/serving-watcher
kubectl apply -f watcher-rbac.yaml

# Create ConfigMap from watcher.py and isvc-template.yaml
kubectl create configmap serving-watcher \
  --from-file=watcher.py=../kserve/serving-watcher/watcher.py \
  --from-file=isvc-template.yaml=../kserve/serving-watcher/isvc-template.yaml \
  -n model-serving \
  --dry-run=client -o yaml | kubectl apply -f -

# Deploy the watcher
kubectl apply -f ../kserve/serving-watcher/deployment.yaml
cd ../../../..
sleep 10

# 14.8: Feature Registry (Feast + Redis)
echo " Build and Push Feast Docker Images..."
docker build ./application/feast_repo/ -t ngnquanq/feast-repo:latest
docker push ngnquanq/feast-repo:latest
echo " Feast image push successful."
echo "  Deploying Feature Registry (Feast + Redis)..."
kubectl create ns feature-registry || echo "Namespace already exists"
kubectl apply -k ./services/ml/k8s/feature-store/
sleep 30

# 14.9: Monitoring (Prometheus + Grafana)
echo "  Deploying Monitoring Stack (Prometheus + Grafana)..."
kubectl create namespace monitoring || echo "Namespace already exists"
cd services/ml/k8s/monitoring
helm upgrade --install kube-prometheus-stack ./kube-prometheus-stack \
    -n monitoring \
    -f kube-prometheus-stack/values.custom.yaml
kubectl apply -f kube-prometheus-stack/docker-cadvisor-servicemonitor.yaml
cd ../../../..
sleep 30

# 14.10: Logging (EFK Stack)
echo "  Deploying Logging Stack (Elasticsearch + Filebeat + Kibana)..."
kubectl create ns logging || echo "Namespace already exists"
cd services/ml/k8s/logging/elastic-stack

helm upgrade --install elasticsearch ./elasticsearch -n logging -f \
    elasticsearch-values.custom.yaml
sleep 20

kubectl create secret generic elasticsearch-master-certs -n logging \
    --from-literal=username=elastic --from-literal=password=changeme --from-literal=ca.crt=dummy \
    --dry-run=client -o yaml | kubectl apply -f -

# Create dummy service account token secret for Kibana (required by helm chart even when not used)
kubectl create secret generic kibana-kibana-es-token -n logging \
    --from-literal=token=dummy-token-not-used \
    --dry-run=client -o yaml | kubectl apply -f -

# Install Kibana with --no-hooks to skip pre-install jobs that require actual certificates
helm upgrade --install kibana ./kibana -n logging -f kibana-values.custom.yaml --no-hooks || echo "Kibana already installed"
sleep 20

helm upgrade --install filebeat ./filebeat -n logging -f filebeat-values.custom.yaml || echo "Filebeat already installed"
cd ../../../../..

echo -e "${GREEN} ML Platform components deployed${NC}\n"

# # ==============================================================================
# # STEP 15: OPTIONAL - SPARK AND AIRFLOW
# # ==============================================================================
# echo -e "${BLUE}[15/15] Starting Optional Components (Spark, Airflow)...${NC}"

# # Spark Cluster
# echo "  Starting Spark Cluster..."
# docker compose -f ./services/data/docker-compose.batch.yml up -d
# sleep 10

# # Airflow
# echo "  Starting Airflow..."
# docker compose -f ./services/ops/docker-compose.orchestration.yml up -d
# sleep 20

# echo -e "${GREEN} Optional components started${NC}\n"

# # ==============================================================================
# # DEPLOYMENT COMPLETE
# # ==============================================================================
# echo ""
# echo "=============================================="
# echo -e "${GREEN} DEPLOYMENT COMPLETE!${NC}"
# echo "=============================================="
# echo ""
# echo "Services Overview:"
# echo "  " Core API: http://localhost (NGINX)"
# echo "  " Kafka UI: http://localhost:8080"
# echo "  " Debezium UI: http://localhost:8083"
# echo "  " Superset: http://localhost:8089 (admin/admin)"
# echo "  " Airflow: http://localhost:9055 (airflow/airflow)"
# echo "  " Flink: http://localhost:8081"
# echo ""
# echo "Next Steps:"
# echo "  1. Port-forward Kubeflow: kubectl port-forward -n kubeflow svc/ml-pipeline-ui 8888:80"
# echo "  2. Port-forward MLflow: kubectl port-forward -n model-registry svc/mlflow 5001:5000"
# echo "  3. Port-forward Grafana: kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80"
# echo "  4. Port-forward Kibana: kubectl port-forward -n logging svc/kibana-kibana 5601:5601"
# echo "  5. Create dockerhub-creds secret if deploying models"
# echo ""
# echo "=============================================="
