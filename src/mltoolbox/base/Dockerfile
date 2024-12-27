FROM nvidia/cuda:12.6.3-runtime-ubuntu22.04

ARG PYTHON_VERSION=3.12

# Combine environment variable settings
ENV TZ=Etc/UTC \
    PATH="/usr/local/bin:${PATH}" \
    PYTHONPATH="/usr/local/lib/python${PYTHON_VERSION}/dist-packages:${PYTHONPATH}" \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /workspace

# Install all necessary system packages including development tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    curl \
    git \
    openssh-client \
    sudo \
    wget \
    nvtop \
    nano \
    vim \
    zsh \
    net-tools \
    software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    python${PYTHON_VERSION} \
    python${PYTHON_VERSION}-dev \
    python${PYTHON_VERSION}-venv \
    nvidia-cuda-toolkit \
    nvidia-cuda-toolkit-gcc && \
    ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python && \
    rm -f /usr/lib/python${PYTHON_VERSION}/EXTERNALLY-MANAGED && \
    # Install zsh theme
    sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v1.1.5/zsh-in-docker.sh)" -- \
    -t robbyrussell \
    -p git && \
    chsh -s $(which zsh) && \
    echo "set -o vi" >> /root/.zshrc && \
    # Cleanup
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /tmp/* && \
    rm -rf /var/tmp/*

# Install pip and UV
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python && \
    curl -LsSf https://astral.sh/uv/install.sh | sh

# Install ray
RUN pip install -U ray[default]