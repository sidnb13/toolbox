#!/bin/bash
set -e # Exit on error

# Start a new SSH agent
eval $(ssh-agent -s)

# Get SSH key name from environment variable or use default
SSH_KEY_NAME=${SSH_KEY_NAME:-github}
# Add the SSH key if it exists
if [ -f "/root/.ssh/${SSH_KEY_NAME}" ]; then
    echo "🔑 Found SSH key '${SSH_KEY_NAME}', adding to agent..."
    ssh-add /root/.ssh/${SSH_KEY_NAME}
    echo "✅ Added SSH key to agent"
else
    echo "⚠️ SSH key '/root/.ssh/${SSH_KEY_NAME}' not found"
fi

# Test SSH connection
echo "🔍 Testing SSH connection to GitHub..."
ssh-keyscan -t rsa,ecdsa,ed25519 github.com >>/root/.ssh/known_hosts 2>/dev/null
ssh -T git@github.com 2>&1 || true

# Create NVIDIA device symlinks if nvidia-ctk is available
if command -v nvidia-ctk &>/dev/null; then
    echo "🔧 Creating NVIDIA device symlinks..."
    nvidia-ctk system create-dev-char-symlinks --create-all || true
fi

# Simplified workspace approach - always use PROJECT_NAME
if [ ! -z "${PROJECT_NAME}" ]; then
    echo "🚀 Using workspace directory: /workspace/${PROJECT_NAME}"
    cd /workspace/${PROJECT_NAME}
fi

# Print system information
echo "🖥️  Container System Information:"
if [[ "$(uname -s)" == "Linux" ]]; then
    # Report variant information
    echo "🧩 Using variant: ${VARIANT:-cuda}"

    # Only run CUDA checks on Linux
    if command -v nvidia-smi &>/dev/null; then
        echo "✅ CUDA is available"
        nvidia-smi
        # Get number of available GPUs
        GPU_COUNT=$(nvidia-smi --list-gpus | wc -l)
        echo "📊 Found ${GPU_COUNT} GPU(s)"
        # Set CUDA_VISIBLE_DEVICES to all available GPUs (0,1,2,etc.)
        export CUDA_VISIBLE_DEVICES=$(seq -s ',' 0 $((GPU_COUNT - 1)))
        echo "🎯 CUDA_VISIBLE_DEVICES set to: ${CUDA_VISIBLE_DEVICES}"
    else
        echo "⚠️  WARNING: CUDA is not available"
    fi
else
    echo "🍎 Running on macOS"
fi
echo "-----------------------------------"

# Setup Git configuration
echo "🔧 Setting up git configuration..."
export GIT_DISCOVERY_ACROSS_FILESYSTEM=1
git config --global --replace-all user.email "${GIT_EMAIL}" || true
git config --global --replace-all user.name "${GIT_NAME}" || true
git config --global --replace-all safe.directory '*' || true

# Save SSH agent environment variables to a file
echo "export SSH_AUTH_SOCK=$SSH_AUTH_SOCK" >/etc/profile.d/ssh-agent.sh
echo "export SSH_AGENT_PID=$SSH_AGENT_PID" >>/etc/profile.d/ssh-agent.sh
chmod +x /etc/profile.d/ssh-agent.sh

# Source SSH environment in shell config files
echo "source /etc/profile.d/ssh-agent.sh" >>/root/.bashrc
if [ -f /root/.zshrc ]; then
    echo "source /etc/profile.d/ssh-agent.sh" >>/root/.zshrc
fi

# Register with Ray cluster if RAY_HEAD_ADDRESS is set
if [ ! -z "${RAY_HEAD_ADDRESS}" ]; then
    # Check if the ray-init.sh script exists
    if [ -f /usr/local/bin/ray-init.sh ]; then
        echo "🌟 Registering with Ray cluster..."
        /usr/local/bin/ray-init.sh &
    else
        echo "⚠️ Ray initialization script not found, skipping Ray registration"
    fi
fi

# Container SSH Server Setup (always enabled)
CONTAINER_SSH_PORT=${CONTAINER_SSH_PORT:-2222}
echo "🔐 Setting up container SSH server on port ${CONTAINER_SSH_PORT}..."

# Install openssh-server if not present
if ! command -v sshd &>/dev/null; then
    echo "📦 Installing openssh-server..."
    apt-get update -qq && apt-get install -y -qq openssh-server && rm -rf /var/lib/apt/lists/*
fi

# Create required directories
mkdir -p /var/run/sshd /etc/ssh/sshd_config.d

# Configure SSH: key-only auth on custom port
cat > /etc/ssh/sshd_config.d/container.conf <<EOF
Port ${CONTAINER_SSH_PORT}
PermitRootLogin prohibit-password
PasswordAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile /root/.ssh/authorized_keys
EOF

# Create authorized_keys from mounted .pub files if it doesn't exist
if [ ! -f "/root/.ssh/authorized_keys" ] && [ -d "/root/.ssh" ]; then
    echo "📝 Creating authorized_keys from available public keys..."
    find /root/.ssh -name "*.pub" -exec cat {} \; > /root/.ssh/authorized_keys 2>/dev/null || true
fi

# Fix SSH permissions (SSH is strict about this)
if [ -d "/root/.ssh" ]; then
    chmod 700 /root/.ssh
    if [ -f "/root/.ssh/authorized_keys" ]; then
        chmod 600 /root/.ssh/authorized_keys
        KEY_COUNT=$(wc -l < /root/.ssh/authorized_keys 2>/dev/null || echo "0")
        echo "✅ authorized_keys configured with ${KEY_COUNT} key(s)"
    else
        echo "⚠️  No authorized_keys file created. SSH access may not work."
    fi
fi

# Start SSH daemon in background
echo "🚀 Starting SSH server on port ${CONTAINER_SSH_PORT}..."
/usr/sbin/sshd -D &
SSHD_PID=$!
echo "✅ SSH server started (PID: $SSHD_PID)"

# Jupyter Server Setup
if [ "${ENABLE_JUPYTER}" = "true" ]; then
    echo "📓 Setting up Jupyter server..."

    # Install jupyter if not present
    if ! command -v jupyter &>/dev/null; then
        echo "📦 Installing Jupyter notebook..."
        pip install -q jupyter notebook ipykernel
    fi

    # Start Jupyter with Colab-compatible settings
    echo "🚀 Starting Jupyter server on port ${JUPYTER_PORT:-8888}..."
    nohup jupyter notebook \
        --allow-root \
        --ip=0.0.0.0 \
        --port="${JUPYTER_PORT:-8888}" \
        --no-browser \
        --NotebookApp.allow_origin='https://colab.research.google.com' \
        --NotebookApp.port_retries=0 \
        --NotebookApp.allow_credentials=True \
        --NotebookApp.token='' \
        --notebook-dir="/workspace/${PROJECT_NAME}" \
        > /tmp/jupyter.log 2>&1 &

    JUPYTER_PID=$!
    echo "✅ Jupyter server started (PID: $JUPYTER_PID)"
    echo "   Logs: /tmp/jupyter.log"
    echo "   URL: http://localhost:${JUPYTER_PORT:-8888}"
    echo "   For Colab: Connect -> Connect to local runtime -> enter URL"
fi

# Run /usr/local/bin/install.sh with VARIANT if it exists
if [ -f /usr/local/bin/install.sh ]; then
    echo "🔧 Running /usr/local/bin/install.sh with VARIANT=${VARIANT:-cuda}..."
    VARIANT="${VARIANT:-cuda}" /usr/local/bin/install.sh
else
    echo "⚠️  /usr/local/bin/install.sh not found, skipping installation"
fi

# Run pre-commit install if pre-commit is available
if command -v pre-commit &>/dev/null; then
    echo "🔧 Running pre-commit install..."
    pre-commit install
else
    echo "⚠️  pre-commit not found, skipping pre-commit install"
fi

# Execute the command passed to docker run
exec "$@"
