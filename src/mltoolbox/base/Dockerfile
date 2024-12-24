FROM nvcr.io/nvidia/pytorch:24.12-py3

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

WORKDIR /workspace

# Combine all apt operations and cleanup in a single layer
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
    zsh && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    python${PYTHON_VERSION} \
    python${PYTHON_VERSION}-dev \
    python${PYTHON_VERSION}-venv \
    nvidia-cuda-toolkit \
    nvidia-cuda-toolkit-gcc && \
    ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python && \
    # Install zsh theme
    sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v1.1.5/zsh-in-docker.sh)" -- \
    -t robbyrussell \
    -p git && \
    # Cleanup
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /tmp/* && \
    rm -rf /var/tmp/*

# Install pip and UV in a single layer
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    # Setup Git configuration
    git config --global user.email "${GIT_EMAIL}" && \
    git config --global user.name "${GIT_NAME}"

# Copy and install requirements
COPY requirements.txt /tmp/
RUN /root/.local/bin/uv pip install --system --no-cache-dir -r /tmp/requirements.txt && \
    rm -f /tmp/requirements.txt

# Copy entrypoint script
COPY scripts/entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]