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
	@echo "  up-feature-store - Start feature store"
	@echo "  up-registry     - Start model registry"
	@echo "  up-serving      - Start model serving"
	@echo "  up-dashboard    - Start Superset dashboard"
	@echo ""
	@echo "Utility Commands:"
	@echo "  create-network  - Create platform network"
	@echo "  check-ports     - Check container port mappings"

# Network management
create-network: ## Create the platform network
	docker network create $(NETWORK_NAME) || true

# Full platform management
up: create-network ## Start all services
	docker-compose -f $(COMPOSE_FILE) up -d

down: ## Stop all services
	docker-compose -f $(COMPOSE_FILE) down

logs: ## View logs from all services
	docker-compose -f $(COMPOSE_FILE) logs -f

restart: ## Restart all services
	docker-compose -f $(COMPOSE_FILE) restart

# Category-based deployment
up-core: create-network ## Start core infrastructure services
	docker-compose -f $(CORE_COMPOSE) up -d

up-data: create-network ## Start all data platform services
	docker-compose -f $(DATA_STORAGE_COMPOSE) -f $(DATA_WAREHOUSE_COMPOSE) -f $(DATA_STREAMING_COMPOSE) -f $(DATA_CDC_COMPOSE) up -d

up-ml: create-network ## Start all ML platform services
	docker-compose -f $(ML_FEATURE_STORE_COMPOSE) -f $(ML_REGISTRY_COMPOSE) -f $(ML_SERVING_COMPOSE) -f $(ML_BATCH_COMPOSE) up -d

up-ops: create-network ## Start all operations services
	docker-compose -f $(OPS_DASHBOARD_COMPOSE) -f $(OPS_GATEWAY_COMPOSE) -f $(OPS_ORCHESTRATION_COMPOSE) up -d

# Individual service management
up-storage: create-network ## Start data storage services
	docker-compose -f $(DATA_STORAGE_COMPOSE) up -d

up-warehouse: create-network ## Start data warehouse services  
	docker-compose -f $(DATA_WAREHOUSE_COMPOSE) up -d

up-streaming: create-network ## Start streaming services
	docker-compose -f $(DATA_STREAMING_COMPOSE) up -d

up-cdc: create-network ## Start CDC services
	docker-compose -f $(DATA_CDC_COMPOSE) up -d

up-feature-store: create-network ## Start feature store services
	docker-compose -f $(ML_FEATURE_STORE_COMPOSE) up -d

up-registry: create-network ## Start model registry services
	docker-compose -f $(ML_REGISTRY_COMPOSE) up -d

up-serving: create-network ## Start model serving services
	docker-compose -f $(ML_SERVING_COMPOSE) up -d

up-batch: create-network ## Start batch processing services
	docker-compose -f $(ML_BATCH_COMPOSE) up -d

up-dashboard: create-network ## Start dashboard services
	docker-compose -f $(OPS_DASHBOARD_COMPOSE) up -d

up-gateway: create-network ## Start gateway services
	docker-compose -f $(OPS_GATEWAY_COMPOSE) up -d

up-orchestration: create-network ## Start orchestration services
	docker-compose -f $(OPS_ORCHESTRATION_COMPOSE) up -d

# Category-based shutdown
down-core: ## Stop core services
	docker-compose -f $(CORE_COMPOSE) down

down-data: ## Stop data platform services
	docker-compose -f $(DATA_STORAGE_COMPOSE) -f $(DATA_WAREHOUSE_COMPOSE) -f $(DATA_STREAMING_COMPOSE) -f $(DATA_CDC_COMPOSE) down

down-ml: ## Stop ML platform services
	docker-compose -f $(ML_FEATURE_STORE_COMPOSE) -f $(ML_REGISTRY_COMPOSE) -f $(ML_SERVING_COMPOSE) -f $(ML_BATCH_COMPOSE) down

down-ops: ## Stop operations services
	docker-compose -f $(OPS_DASHBOARD_COMPOSE) -f $(OPS_GATEWAY_COMPOSE) -f $(OPS_ORCHESTRATION_COMPOSE) down

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

# Environment-specific deployments
deploy-dev: up-core up-data up-ml ## Deploy development environment
	@echo "Development environment deployed"

deploy-staging: up-core up-data up-ml up-ops ## Deploy staging environment  
	@echo "Staging environment deployed"

deploy-prod: up ## Deploy production environment
	@echo "Production environment deployed"