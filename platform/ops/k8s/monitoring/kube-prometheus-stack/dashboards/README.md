# Grafana Dashboards

Community dashboards for Docker container monitoring.

## Installed Dashboards

### 1. cAdvisor Exporter (ID 14282) - **RECOMMENDED**
- **Source**: https://grafana.com/grafana/dashboards/14282
- **Metrics**: Container CPU, Memory, Network, Filesystem metrics from cAdvisor
- **Best for**: Detailed container-level monitoring (works with cAdvisor metrics only)
- **ConfigMap**: `cadvisor-dashboard-configmap.yaml`
- **Auto-loaded**: Yes

### 2. Docker + System Dashboard (ID 893)
- **Source**: https://grafana.com/grafana/dashboards/893
- **Metrics**: System overview, container stats (requires node_exporter for host metrics)
- **Best for**: General system monitoring
- **ConfigMap**: `docker-dashboard-configmap.yaml`
- **Auto-loaded**: Yes
- **Note**: Some panels (Uptime, Disk Space) require node_exporter metrics

## Access

1. Open Grafana: http://localhost:30300
2. Login: `admin` / `admin`
3. Navigate to **Dashboards** → **Browse**
4. Find "cAdvisor Exporter" or "Docker + System Dashboard"

## Adding More Dashboards

### Method 1: Via Grafana UI (Manual)
1. Go to **+** → **Import Dashboard**
2. Enter Grafana.com dashboard ID
3. Select **Prometheus** as datasource
4. Click **Import**

### Method 2: Via ConfigMap (Persistent)
1. Download dashboard JSON:
   ```bash
   curl -s https://grafana.com/api/dashboards/{ID}/revisions/1/download -o dashboards/my-dashboard.json
   ```

2. Create ConfigMap with label `grafana_dashboard: "1"`:
   ```bash
   kubectl create configmap my-dashboard \
     -n monitoring \
     --from-file=my-dashboard.json=dashboards/my-dashboard.json \
     --dry-run=client -o yaml | \
     kubectl label --local -f - grafana_dashboard=1 --dry-run=client -o yaml | \
     kubectl apply -f -
   ```

## Other Recommended Dashboards

- **179** - Docker Monitoring (alternative, lightweight)
- **11600** - Docker Container & Host Metrics (modern UI, requires node_exporter)
- **395** - Docker Dashboard (classic)
- **1860** - Node Exporter Full (requires node_exporter for host metrics)

## Notes

- Dashboards are auto-loaded by Grafana's sidecar container
- Label `grafana_dashboard: "1"` is required for auto-discovery
- Changes to ConfigMaps are picked up automatically (may take 1-2 minutes)
