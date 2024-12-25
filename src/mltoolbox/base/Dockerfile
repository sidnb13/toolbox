FROM nvcr.io/nvidia/pytorch:24.12-py3

ARG PYTHON_VERSION=3.12

# Combine environment variable settings
ENV TZ=Etc/UTC \
    PATH="/usr/local/bin:${PATH}" \
    PYTHONPATH="/usr/local/lib/python${PYTHON_VERSION}/dist-packages:${PYTHONPATH}" \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /workspace

# Reduce to essential packages only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    curl \
    git \
    openssh-client \
    sudo \
    wget \
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
    # Cleanup
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /tmp/* && \
    rm -rf /var/tmp/*

# Install pip and UV
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python && \
    curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy entrypoint script
COPY scripts/entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]