.PHONY: check-ports

check-ports:
	@echo "Checking port mappings for all running containers..."
	@for name in $$(docker ps --format '{{.Names}}'); do \
		echo "--- Ports for container: $${name} ---"; \
		docker port "$${name}"; \
	done
	@echo "--- End of port check ---"