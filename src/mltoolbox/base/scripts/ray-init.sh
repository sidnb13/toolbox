#!/bin/bash
set -e

# Configuration
CONTAINER_ID=${CONTAINER_ID:-$(hostname)}
RAY_HEAD_ADDRESS=${RAY_HEAD_ADDRESS:-localhost:6379}
RAY_JOIN_RETRIES=${RAY_JOIN_RETRIES:-10}
RAY_JOIN_RETRY_INTERVAL=${RAY_JOIN_RETRY_INTERVAL:-3}

# Check if already connected to Ray
if pgrep -f "ray::IDLE" >/dev/null || pgrep -f "raylet" >/dev/null; then
    echo "ℹ️ Ray worker already running in this container. Skipping registration."
    exit 0
fi

# Always use localhost for connection check, regardless of RAY_HEAD_ADDRESS
echo "🔍 Checking for Ray head node at ${RAY_HEAD_ADDRESS} (via localhost)..."

# Wait for Ray head node to be available
retry=0
while ! nc -z localhost 6379 >/dev/null 2>&1; do
    retry=$((retry + 1))
    if [ $retry -gt $RAY_JOIN_RETRIES ]; then
        echo "❌ Ray head node not available after $RAY_JOIN_RETRIES retries. Running standalone."
        exit 0
    fi
    echo "⏳ Waiting for Ray head node (attempt $retry/$RAY_JOIN_RETRIES)..."
    sleep $RAY_JOIN_RETRY_INTERVAL
done

echo "✅ Ray head node detected, registering container ${CONTAINER_ID}"

# Detect number of GPUs available in the container
if command -v nvidia-smi &>/dev/null; then
    NUM_GPUS=$(nvidia-smi --list-gpus | wc -l)
    echo "🔍 Detected ${NUM_GPUS} GPUs in container"
else
    NUM_GPUS=0
    echo "⚠️ nvidia-smi not found, assuming 0 GPUs"
fi

# Register container-specific resource with count equal to GPU count
# This makes container ID resource match number of GPUs
RESOURCE_JSON="{\"${CONTAINER_ID}\": ${NUM_GPUS}}"

# Start Ray worker process
RAY_HOST=$(echo $RAY_HEAD_ADDRESS | cut -d: -f1)
RAY_PORT=$(echo $RAY_HEAD_ADDRESS | cut -d: -f2)
RAY_CONNECT_ADDRESS="localhost:${RAY_PORT}"

ray start --address=${RAY_CONNECT_ADDRESS} \
    --resources="${RESOURCE_JSON}" \
    --num-gpus=${NUM_GPUS} \
    --node-ip-address=localhost

echo "🔗 Container ${CONTAINER_ID} registered with Ray cluster with ${NUM_GPUS} GPUs"

# Register container in shared directory for distributed blocking approach
SHARED_DIR=${SHARED_DIR:-"/shared"}
mkdir -p ${SHARED_DIR}
echo ${CONTAINER_ID} >> ${SHARED_DIR}/container_list.txt
echo "📝 Registered container in ${SHARED_DIR}/container_list.txt for distributed scheduling"