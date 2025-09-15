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

PYTHON := python

help: ## Show this help message
	@echo "Home Credit ML Platform - Docker Services"
	@echo ""
	@echo "Full Platform Commands:"
	@echo "  up              - Start all services"
	@echo "  down            - Stop all services"
	@echo "  logs            - View all service logs"
	@echo "  health          - Check service health"
	@echo ""
	@echo "Category Commands:"
	@echo "  up-core         - Start core infrastructure"
	@echo "  up-data         - Start data platform services"
	@echo "  up-ml           - Start ML platform services"
	@echo "  up-ops          - Start operations services"
	@echo ""
	@echo "Individual Service Commands:"
	@echo "  up-storage      - Start data storage (MinIO)"
	@echo "  up-warehouse    - Start data warehouse (ClickHouse)"
	@echo "  up-streaming    - Start streaming (Kafka)"
	@echo "  up-cdc          - Start CDC services (requires streaming)"
	@echo "  up-flink        - Start Flink cluster"
	@echo "  up-query        - Start ext + dwh query services"
	@echo "  up-redis        - Start Redis for Feast online store"
	@echo "  run-flink-job   - Build and submit PyFlink job"
	@echo "  up-batch        - Start Spark batch processing cluster"
	@echo "  setup-cdc       - Start streaming + CDC + create connectors"
	@echo "  deploy-complete - Full deployment with automated setup"
	@echo "  up-feature-store - Start feature store"
	@echo "  up-registry     - Start model registry"
	@echo "  up-serving      - Start model serving"
	@echo "  up-dashboard    - Start Superset dashboard"
	@echo ""
	@echo "Utility Commands:"
	@echo "  create-network  - Create platform network"
	@echo "  check-ports     - Check container port mappings"
	@echo "  core-apply-migrations - Apply core DB migrations (idempotent)"
	@echo "  core-reset-db   - Drop and recreate core DB (destructive)"

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
	@cd services && docker compose --env-file .env --env-file .env.core -f core/docker-compose.yml up -d
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
	@cd services && docker compose --env-file .env --env-file .env.core -f core/docker-compose.yml down -v
	@$(MAKE) up-core
	@$(MAKE) core-apply-migrations

up-data: create-network ## Start all data platform services
	docker compose -f $(DATA_STORAGE_COMPOSE) -f $(DATA_WAREHOUSE_COMPOSE) -f $(DATA_STREAMING_COMPOSE) -f $(DATA_CDC_COMPOSE) up -d

up-ml: create-network ## Start all ML platform services
	docker compose -f $(ML_FEATURE_STORE_COMPOSE) -f $(ML_REGISTRY_COMPOSE) -f $(ML_SERVING_COMPOSE) -f $(ML_BATCH_COMPOSE) up -d

up-ops: create-network ## Start all operations services
	docker compose -f $(OPS_DASHBOARD_COMPOSE) -f $(OPS_GATEWAY_COMPOSE) -f $(OPS_ORCHESTRATION_COMPOSE) up -d

# Individual service management
up-storage: create-network ## Start data storage services
	docker compose -f $(DATA_STORAGE_COMPOSE) up -d

up-warehouse: create-network ## Start data warehouse services  
	docker compose -f $(DATA_WAREHOUSE_COMPOSE) up -d

up-streaming: create-network ## Start streaming services
	@cd services && docker compose --env-file .env --env-file .env.data -f data/docker-compose.streaming.yml up -d
	@echo "Waiting for Kafka to be ready..."
	@until docker exec kafka_broker kafka-topics --bootstrap-server localhost:9092 --list > /dev/null 2>&1; do sleep 2; echo -n "."; done
	@echo " Kafka ready!"

up-cdc: create-network ## Start CDC services (requires streaming to be running)
	@cd services && docker compose --env-file .env --env-file .env.core --env-file .env.data -f data/docker-compose.streaming.yml -f data/docker-compose.cdc.yml up -d
	@echo "Waiting for Debezium to be ready..."
	@until curl -f http://localhost:8083/connectors > /dev/null 2>&1; do sleep 2; echo -n "."; done
	@echo " Debezium ready!"

up-flink: create-network ## Start Flink cluster (JobManager + TaskManager)
	@cd services && docker compose --env-file .env --env-file .env.data -f data/docker-compose.flink.yml up -d
	@echo "Flink UI: http://localhost:8085"

up-query: create-network ## Start external and DWH query services
	@cd services && docker compose --env-file .env --env-file .env.data -f data/docker-compose.query-services.yml up -d

up-redis: create-network ## Start Redis (Feast online store)
	@cd services && docker compose --env-file .env --env-file .env.data -f data/docker-compose.redis.yml up -d

run-flink-job: ## Build and run the self-contained PyFlink job submitter
	@cd services && docker compose --env-file .env --env-file .env.data -f data/docker-compose.flink.yml build flink-job
	@cd services && docker compose --env-file .env --env-file .env.data -f data/docker-compose.flink.yml up -d flink-job

# up-batch: create-network ## Start Spark batch processing cluster
# 	@cd services && docker compose --env-file .env --env-file .env.data -f data/docker-compose.batch.yml up -d
# 	@echo "Waiting for Spark Master to be ready..."
# 	@until curl -f http://localhost:8084 > /dev/null 2>&1; do sleep 2; echo -n "."; done
# 	@echo " Spark cluster ready!"
# 	@echo "Spark Master UI: http://localhost:8084"
# 	@echo "Jupyter Notebook: http://localhost:8888 (token: spark_notebook_token)"

setup-cdc: up-streaming up-cdc
	@echo "Creating Debezium connectors..."
	@cd services && bash -c "set -a && source .env && source .env.core && source .env.data && envsubst < data/create-connectors.sh" | bash

deploy-complete: up-core setup-cdc ## Deploy complete platform with automated CDC setup
	@echo "=== Complete Deployment Summary ==="
	@echo "✅ Core services (PostgreSQL + PgBouncer) running"
	@echo "✅ Streaming services (Kafka ecosystem) running" 
	@echo "✅ CDC services (Debezium) running"
	@echo "✅ Connectors created and active"
	@echo ""
	@echo "Testing data flow (optional)..."
	@cd services && docker exec ops_postgres psql -U ops_admin -d operations -c "INSERT INTO applications (user_id, application_data, status) VALUES (99998, '{\"test\": \"deployment_verification\", \"timestamp\": \"$$(date -Iseconds)\"}', 'TEST');" || true
	@echo "Complete deployment with CDC ready!"

up-feature-store: create-network ## Start feature store services
	docker compose -f $(ML_FEATURE_STORE_COMPOSE) up -d

up-registry: create-network ## Start model registry services
	docker compose -f $(ML_REGISTRY_COMPOSE) up -d

up-serving: create-network ## Start model serving services
	docker compose -f $(ML_SERVING_COMPOSE) up -d

up-batch: create-network ## Start batch processing services
	docker compose -f $(ML_BATCH_COMPOSE) up -d

up-dashboard: create-network ## Start dashboard services
	docker compose -f $(OPS_DASHBOARD_COMPOSE) up -d

up-gateway: create-network ## Start gateway services
	docker compose -f $(OPS_GATEWAY_COMPOSE) up -d

up-orchestration: create-network ## Start orchestration services
	docker compose -f $(OPS_ORCHESTRATION_COMPOSE) up -d

# Category-based shutdown
down-core: ## Stop core services
	docker compose -f $(CORE_COMPOSE) down

down-data: ## Stop data platform services
	docker compose -f $(DATA_STORAGE_COMPOSE) -f $(DATA_WAREHOUSE_COMPOSE) -f $(DATA_STREAMING_COMPOSE) -f $(DATA_CDC_COMPOSE) down

down-ml: ## Stop ML platform services
	docker compose -f $(ML_FEATURE_STORE_COMPOSE) -f $(ML_REGISTRY_COMPOSE) -f $(ML_SERVING_COMPOSE) -f $(ML_BATCH_COMPOSE) down

down-ops: ## Stop operations services
	docker compose -f $(OPS_DASHBOARD_COMPOSE) -f $(OPS_GATEWAY_COMPOSE) -f $(OPS_ORCHESTRATION_COMPOSE) down

# Health and monitoring
health: ## Check service health status
	@echo "=== Service Health Check ==="
	@echo "Network: $(NETWORK_NAME)"
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" --filter network=$(NETWORK_NAME)

check-ports: ## Check port mappings for all running containers
	@echo "Checking port mappings for all running containers..."
	@for name in $$(docker ps --format '{{.Names}}'); do \
		echo "--- Ports for container: $${name} ---"; \
		docker port "$${name}"; \
	done
	@echo "--- End of port check ---"

create-kafka-topics: ## Create default Kafka topics using Python SDK
	@echo "Creating Kafka topics (hc.application_pii, hc.application_features)"
	@python application/kafka/create_topics.py

# Environment-specific deployments
deploy-dev: up-core up-data up-ml ## Deploy development environment
	@echo "Development environment deployed"

deploy-staging: up-core up-data up-ml up-ops ## Deploy staging environment  
	@echo "Staging environment deployed"

deploy-prod: up ## Deploy production environment
	@echo "Production environment deployed"
