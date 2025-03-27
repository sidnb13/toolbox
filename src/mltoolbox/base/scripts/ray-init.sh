#!/bin/bash
set -e

# Configuration
CONTAINER_ID=${CONTAINER_ID:-$(hostname)}
RAY_HEAD_ADDRESS=${RAY_HEAD_ADDRESS:-localhost:6379}
RAY_JOIN_RETRIES=${RAY_JOIN_RETRIES:-10}
RAY_JOIN_RETRY_INTERVAL=${RAY_JOIN_RETRY_INTERVAL:-3}

echo "🔍 Checking for Ray head node at ${RAY_HEAD_ADDRESS}..."

# Wait for Ray head node to be available
retry=0
while ! nc -z ${RAY_HEAD_ADDRESS/:/ } >/dev/null 2>&1; do
    retry=$((retry + 1))
    if [ $retry -gt $RAY_JOIN_RETRIES ]; then
        echo "❌ Ray head node not available after $RAY_JOIN_RETRIES retries. Running standalone."
        exit 0
    fi
    echo "⏳ Waiting for Ray head node (attempt $retry/$RAY_JOIN_RETRIES)..."
    sleep $RAY_JOIN_RETRY_INTERVAL
done

echo "✅ Ray head node detected, registering container ${CONTAINER_ID}"

# Define resources for this container - each container registers with its container ID
RESOURCES="{\"${CONTAINER_ID}\": 1}"

# Start Ray worker process
ray start --address=${RAY_HEAD_ADDRESS} \
    --resources="${RESOURCES}" \
    --node-ip-address=localhost

echo "🔗 Container ${CONTAINER_ID} registered with Ray cluster"
