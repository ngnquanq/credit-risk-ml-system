#!/bin/bash
# Restart script for Kubernetes deployments after minikube start
# This fixes CrashLoopBackOff issues caused by pods starting before API server is ready
#
# Usage: ./restart-k8s-after-minikube.sh

set -e

echo "=========================================="
echo "K8s Post-Minikube Restart Script"
echo "=========================================="
echo ""

# Change to script directory
cd "$(dirname "$0")"

# Step 1: Wait for cluster to be ready
echo "Step 1: Waiting for cluster to be ready..."
echo "  Checking API server availability..."
timeout=60
elapsed=0
while ! kubectl cluster-info &>/dev/null; do
    if [ $elapsed -ge $timeout ]; then
        echo "  ERROR: Cluster not ready after ${timeout}s"
        exit 1
    fi
    echo "  Waiting for API server... (${elapsed}s)"
    sleep 5
    elapsed=$((elapsed + 5))
done
echo "  ✓ API server is ready"
echo ""

# Step 2: Wait for core system pods
echo "Step 2: Waiting for core system pods..."
echo "  Checking CoreDNS..."
kubectl wait --for=condition=ready pod -l k8s-app=kube-dns -n kube-system --timeout=60s
echo "  ✓ CoreDNS is ready"
echo ""

# Step 3: Restart Kafka gateway with current IP
echo "Step 3: Restarting k8s_gateway with current Kafka IP..."
if [ -f "./restart-gateway.sh" ]; then
    bash ./restart-gateway.sh
    echo "  ✓ Gateway restarted"
else
    echo "  ⚠ Warning: restart-gateway.sh not found, skipping"
fi
echo ""

# Step 4: Restart deployments that commonly fail after minikube restart
echo "Step 4: Restarting K8s deployments..."

# Array of deployments to restart: "namespace/deployment-name"
DEPLOYMENTS=(
    "cert-manager/cert-manager-cainjector"
    "kserve/kserve-controller-manager"
    "kubeflow/workflow-controller"
    "kubeflow/cache-deployer-deployment"
    "kubeflow/metadata-grpc-deployment"
    "model-registry/mlflow-watcher"
    "ray/kuberay-operator"
    "feature-registry/feast-stream"
)

for deploy in "${DEPLOYMENTS[@]}"; do
    namespace="${deploy%%/*}"
    deployment="${deploy##*/}"

    # Check if deployment exists
    if kubectl get deployment "$deployment" -n "$namespace" &>/dev/null; then
        echo "  Restarting $namespace/$deployment..."
        kubectl rollout restart deployment "$deployment" -n "$namespace" 2>&1 | sed 's/^/    /'
    else
        echo "  ⚠ Skipping $namespace/$deployment (not found)"
    fi
done
echo ""

# Step 4.5: Restart KServe InferenceService serving pods
echo "Step 4.5: Restarting KServe InferenceService serving pods..."
echo "  Auto-detecting InferenceServices..."

# Get all InferenceServices across all namespaces
isvc_list=$(kubectl get inferenceservice -A -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}' 2>/dev/null || echo "")

if [ -z "$isvc_list" ]; then
    echo "  ℹ No InferenceServices found"
else
    while IFS=' ' read -r ns isvc_name; do
        if [ -n "$isvc_name" ]; then
            echo "  Found InferenceService: $ns/$isvc_name"

            # Get predictor deployment for this InferenceService
            predictor_deploy=$(kubectl get deployment -n "$ns" -l serving.kserve.io/inferenceservice="$isvc_name" -o name 2>/dev/null | head -1)

            if [ -n "$predictor_deploy" ]; then
                echo "    Restarting predictor deployment..."
                kubectl rollout restart "$predictor_deploy" -n "$ns" 2>&1 | sed 's/^/      /'
            else
                echo "    ⚠ No predictor deployment found"
            fi
        fi
    done <<< "$isvc_list"
fi
echo ""

# Step 5: Fix storage provisioner if needed
echo "Step 5: Checking storage provisioner..."
if kubectl get pod storage-provisioner -n kube-system &>/dev/null; then
    status=$(kubectl get pod storage-provisioner -n kube-system -o jsonpath='{.status.phase}')
    if [ "$status" != "Running" ]; then
        echo "  Storage provisioner is $status, restarting..."
        kubectl delete pod storage-provisioner -n kube-system
        echo "  ✓ Storage provisioner deleted (minikube will recreate)"
    else
        echo "  ✓ Storage provisioner is running"
    fi
else
    echo "  ℹ Storage provisioner not found (managed by minikube)"
fi
echo ""

# Step 6: Wait for critical deployments to be ready
echo "Step 6: Waiting for deployments to become ready..."
echo "  This may take 1-2 minutes..."

for deploy in "${DEPLOYMENTS[@]}"; do
    namespace="${deploy%%/*}"
    deployment="${deploy##*/}"

    if kubectl get deployment "$deployment" -n "$namespace" &>/dev/null; then
        echo "  Waiting for $namespace/$deployment..."
        kubectl rollout status deployment "$deployment" -n "$namespace" --timeout=120s 2>&1 | sed 's/^/    /' || echo "    ⚠ Timeout waiting for $deployment"
    fi
done
echo ""

# Step 7: Summary
echo "=========================================="
echo "Summary: Checking for remaining issues..."
echo "=========================================="
echo ""

# Check for CrashLoopBackOff pods
echo "Pods in CrashLoopBackOff:"
crashloop=$(kubectl get pods --all-namespaces | grep -E "CrashLoopBackOff|Error|ImagePullBackOff" || echo "None")
if [ "$crashloop" = "None" ]; then
    echo "  ✓ No pods in CrashLoopBackOff"
else
    echo "$crashloop" | sed 's/^/  /'
fi
echo ""

# Check critical services
echo "Critical service status:"
echo "  Kafka broker IP: $(docker inspect kafka_broker --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null || echo 'N/A')"
echo "  k8s_gateway: $(docker ps --filter name=k8s_gateway --format '{{.Status}}' || echo 'Not running')"
echo "  KServe controller: $(kubectl get pods -n kserve -l control-plane=kserve-controller-manager -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo 'N/A')"
echo "  MLflow watcher: $(kubectl get pods -n model-registry -l app=mlflow-watcher -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo 'N/A')"
echo "  Feast stream: $(kubectl get pods -n feature-registry -l app=feast-stream -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo 'N/A')"
echo ""

echo "=========================================="
echo "✓ Restart script completed!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Check logs if any services are still failing"
echo "  2. Run 'kubectl get pods --all-namespaces | grep -E \"CrashLoopBackOff|Error\"' to verify"
echo ""
