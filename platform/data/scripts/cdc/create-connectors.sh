#!/bin/bash
echo "Creating Debezium connectors..."

# Wait for Debezium to be ready
until curl -f http://cdc-debezium:8083/connector-plugins >/dev/null 2>&1; do
  echo "Waiting for Debezium to be ready..."
  sleep 5
done

echo "Debezium is ready. Creating PostgreSQL connector..."

curl -X POST http://cdc-debezium:8083/connectors \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"${CDC_CONNECTOR_NAME}\",
    \"config\": {
      \"connector.class\": \"io.debezium.connector.postgresql.PostgresConnector\",
      \"database.hostname\": \"${OPS_DB_HOST}\",
      \"database.port\": \"${OPS_DB_PORT}\",
      \"database.user\": \"${OPS_DB_USER}\",
      \"database.password\": \"${OPS_DB_PASSWORD}\",
      \"database.dbname\": \"${OPS_DB_NAME}\",
      \"database.server.name\": \"${CDC_TOPIC_PREFIX}\",
      \"plugin.name\": \"${CDC_PLUGIN_NAME}\",
      \"publication.name\": \"${CDC_PUBLICATION_NAME}\",
      \"slot.name\": \"${CDC_SLOT_NAME}\",
      \"table.include.list\": \"public.loan_applications\",
      \"snapshot.mode\": \"${CDC_SNAPSHOT_MODE}\"
    }
  }"

echo ""
echo "✅ Debezium connector setup completed!"