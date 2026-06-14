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

if [ -z "${OPS_DB_PASSWORD:-}" ]; then
    echo "ERROR: OPS_DB_PASSWORD is required"
    exit 1
fi

# Copy config to tmp, update with IP, then use it
cp /etc/pgbouncer/pgbouncer.ini /tmp/pgbouncer.ini
sed -i "s/host=ops-postgres/host=$PG_IP/g" /tmp/pgbouncer.ini
sed -i "s|/etc/pgbouncer/userlist.txt|/tmp/userlist.txt|g" /tmp/pgbouncer.ini
sed -i "s|<set-via-OPS_DB_PASSWORD>|${OPS_DB_PASSWORD}|g" /tmp/pgbouncer.ini
PASSWORD_MD5=$(printf "%s" "${OPS_DB_PASSWORD}ops_admin" | md5sum | awk '{ print $1 }')
printf '"ops_admin" "md5%s"\n' "$PASSWORD_MD5" > /tmp/userlist.txt

echo "✓ Updated pgbouncer.ini with IP: $PG_IP"
echo "Starting PgBouncer..."

# Start pgbouncer with updated config
exec /opt/pgbouncer/pgbouncer /tmp/pgbouncer.ini
