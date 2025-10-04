#!/bin/bash
# Delete cached Docker Hub tags to force fresh builds

set -e

DOCKER_USERNAME="ngnquanq"
IMAGE_NAME="credit-risk-scoring"
TAGS_TO_DELETE="v7 v8 v9 v10 v11 v12 latest"

echo "🗑️  Docker Hub Cache Cleanup Script"
echo "============================================================"
echo "Repository: $DOCKER_USERNAME/$IMAGE_NAME"
echo "Tags to delete: $TAGS_TO_DELETE"
echo "============================================================"
echo ""

# Check if DOCKER_PASSWORD is set
if [ -z "$DOCKER_PASSWORD" ]; then
    echo "❌ DOCKER_PASSWORD environment variable not set"
    echo ""
    echo "Please set your Docker Hub password:"
    echo "  export DOCKER_PASSWORD='your_password'"
    echo "  ./delete_dockerhub_tags.sh"
    echo ""
    echo "Or run with inline variable:"
    echo "  DOCKER_PASSWORD='your_password' ./delete_dockerhub_tags.sh"
    exit 1
fi

echo "🔑 Authenticating with Docker Hub..."
TOKEN=$(curl -s -H "Content-Type: application/json" -X POST \
  -d "{\"username\": \"$DOCKER_USERNAME\", \"password\": \"$DOCKER_PASSWORD\"}" \
  https://hub.docker.com/v2/users/login/ | jq -r .token)

if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
    echo "❌ Authentication failed! Check your username/password"
    exit 1
fi

echo "✅ Authenticated successfully"
echo ""

# Delete each tag
for tag in $TAGS_TO_DELETE; do
    echo "🗑️  Deleting tag: $tag..."

    response=$(curl -s -w "\n%{http_code}" -X DELETE \
      -H "Authorization: JWT $TOKEN" \
      "https://hub.docker.com/v2/repositories/$DOCKER_USERNAME/$IMAGE_NAME/tags/$tag/")

    http_code=$(echo "$response" | tail -1)

    if [ "$http_code" == "204" ]; then
        echo "   ✅ Deleted $tag"
    elif [ "$http_code" == "404" ]; then
        echo "   ⚠️  Tag $tag not found (already deleted or never existed)"
    else
        echo "   ❌ Failed to delete $tag (HTTP $http_code)"
        echo "$response" | head -1
    fi
done

echo ""
echo "============================================================"
echo "✅ Docker Hub cleanup complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "1. Delete InferenceServices to trigger rebuild:"
echo "   kubectl delete inferenceservice -n kserve --all"
echo ""
echo "2. Monitor the rebuild:"
echo "   kubectl get pods -n kserve --watch"
echo ""
echo "3. The new images will have protobuf 6.32.1 from MinIO!"
echo ""
