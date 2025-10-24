#!/bin/sh
# PgBouncer entrypoint wrapper
# Resolves PostgreSQL hostname to IP (c-ares in PgBouncer doesn't support Docker DNS)

set -e

echo "Resolving ops-postgres hostname to IP..."

# Resolve hostname to IP using getent (standard DNS, not c-ares)
PG_IP=$(getent hosts ops-postgres | awk '{ print $1 }')

if [ -z "$PG_IP" ]; then
    echo "ERROR: Could not resolve ops-postgres hostname"
    exit 1
fi

echo "✓ Resolved ops-postgres to: $PG_IP"

# Copy config to tmp, update with IP, then use it
cp /etc/pgbouncer/pgbouncer.ini /tmp/pgbouncer.ini
cp /etc/pgbouncer/userlist.txt /tmp/userlist.txt
sed -i "s/host=ops-postgres/host=$PG_IP/g" /tmp/pgbouncer.ini
sed -i "s|/etc/pgbouncer/userlist.txt|/tmp/userlist.txt|g" /tmp/pgbouncer.ini

echo "✓ Updated pgbouncer.ini with IP: $PG_IP"
echo "Starting PgBouncer..."

# Start pgbouncer with updated config
exec /opt/pgbouncer/pgbouncer /tmp/pgbouncer.ini
