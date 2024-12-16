FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

ARG PYTHON_VERSION=3.12
ARG GIT_EMAIL
ARG GIT_NAME

# Combine environment variable settings
ENV TZ=Etc/UTC \
    PATH="/usr/local/bin:${PATH}" \
    PYTHONPATH="/usr/local/lib/python${PYTHON_VERSION}/dist-packages:${PYTHONPATH}" \
    GIT_EMAIL=${GIT_EMAIL} \
    GIT_NAME=${GIT_NAME} \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    curl \
    git \
    nano \
    nvtop \
    openssh-client \
    software-properties-common \
    sudo \
    vim \
    wget \
    zsh \
    && rm -rf /var/lib/apt/lists/*

# Install Python
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    python${PYTHON_VERSION} \
    python${PYTHON_VERSION}-dev \
    python${PYTHON_VERSION}-venv \
    && ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# Install pip and UV
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python && \
    curl -LsSf https://astral.sh/uv/install.sh | sh

# Install NVIDIA development tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    nvidia-cuda-toolkit \
    nvidia-cuda-toolkit-gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install requirements
COPY requirements.txt /tmp/
RUN /root/.local/bin/uv pip install --system --no-cache-dir -r /tmp/requirements.txt

# Setup Git configuration
RUN git config --global user.email "${GIT_EMAIL}" && \
    git config --global user.name "${GIT_NAME}"

# Copy entrypoint script
COPY scripts/entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]