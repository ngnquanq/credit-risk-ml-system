#!/bin/bash
# Feast + Protobuf Debugging Script
# This script checks ALL the places where the version mismatch could be hiding

set -e

echo "=================================="
echo "FEAST + PROTOBUF DEBUG REPORT"
echo "=================================="
echo ""

# Find the latest credit-risk pod
POD=$(kubectl get pods -n kserve -l app=credit-risk-scoring --sort-by=.metadata.creationTimestamp -o name | tail -1 | cut -d/ -f2)
echo "🔍 Inspecting pod: $POD"
echo ""

# 1. Check what's actually installed in the container
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  INSTALLED PACKAGES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl exec -n kserve $POD -- uv pip list 2>/dev/null | grep -E "(feast|protobuf|mlflow)" || echo "❌ Failed to get package list"
echo ""

# 2. Check the Bento version and creation time
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  BENTO METADATA"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl exec -n kserve $POD -- cat /home/bentoml/bento/bento.yaml 2>/dev/null | head -10 || echo "❌ Failed to read bento.yaml"
echo ""

# 3. Check the actual requirements.txt that was used
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣  REQUIREMENTS.TXT (FROM BENTO)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl exec -n kserve $POD -- cat /home/bentoml/bento/env/python/requirements.txt 2>/dev/null | grep -E "(feast|protobuf|mlflow)" || echo "❌ Failed to read requirements.txt"
echo ""

# 4. Check GitHub bentofile.yaml
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣  GITHUB BENTOFILE.YAML"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -s https://raw.githubusercontent.com/ngnquanq/credit-risk-ml-system/feature/ml-model-v0.0/application/scoring/bentofile.yaml | grep -A 20 "python:" || echo "❌ Failed to fetch from GitHub"
echo ""

# 5. Check local bentofile.yaml
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣  LOCAL BENTOFILE.YAML"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat application/scoring/bentofile.yaml | grep -A 20 "python:"
echo ""

# 6. Check if protobuf has runtime_version
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣  PROTOBUF MODULE INSPECTION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl exec -n kserve $POD -- python -c "import google.protobuf; print('Protobuf version:', google.protobuf.__version__); print('Has runtime_version:', hasattr(google.protobuf, 'runtime_version'))" 2>&1
echo ""

# 7. Check Docker image tags
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7️⃣  DOCKER IMAGE INFO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get pod -n kserve $POD -o jsonpath='{.spec.containers[0].image}'
echo ""
echo ""

# 8. Check recent bento-builder logs
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8️⃣  LATEST BENTO BUILD LOG"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
LATEST_JOB=$(kubectl get jobs -n kserve --sort-by=.metadata.creationTimestamp -o name | tail -1 | cut -d/ -f2)
echo "Latest job: $LATEST_JOB"
kubectl logs -n kserve job/$LATEST_JOB 2>/dev/null | grep -E "(feast|protobuf|mlflow|Cloning)" | tail -20 || echo "❌ Job logs not available"
echo ""

# 9. Check serving-watcher logs
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "9️⃣  SERVING-WATCHER BUILD LOG"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl logs -n model-serving -l app=serving-watcher -c watcher 2>&1 | grep -E "(Building|Successfully|--no-cache)" | tail -10 || echo "❌ Watcher logs not available"
echo ""

# 10. Try to import feast and see the actual error
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔟 FEAST IMPORT TEST"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl exec -n kserve $POD -- python -c "import feast" 2>&1 | head -30
echo ""

echo "=================================="
echo "SUMMARY"
echo "=================================="
echo ""
echo "The issue is likely one of:"
echo "1. Docker is still using cached layers (check #7 and #9 for --no-cache)"
echo "2. Bento is old (check #2 for creation_time vs now)"
echo "3. GitHub bentofile.yaml not updated (compare #4 and #5)"
echo "4. Requirements resolver is upgrading packages (compare #3 to #4)"
echo ""
echo "Expected state:"
echo "  - protobuf >= 5.26.0 (NOT 4.25.8)"
echo "  - NO mlflow in requirements.txt"
echo "  - Bento creation_time should be recent"
echo ""
