#!/bin/bash

# Headless GPU Instance Setup Script
# No prompts, no colors, just installs Docker + NVIDIA drivers + Container Toolkit

set -e

# Detect OS
if [[ ! -f /etc/os-release ]]; then
    echo "ERROR: Cannot detect OS"
    exit 1
fi

. /etc/os-release
DISTRO=$ID

echo "Setting up GPU instance on $DISTRO..."

# Update system
echo "Updating system packages..."
case $DISTRO in
ubuntu | debian)
    export DEBIAN_FRONTEND=noninteractive
    sudo apt update -y
    sudo apt upgrade -y
    sudo apt install -y curl wget gnupg2 software-properties-common apt-transport-https ca-certificates lsb-release
    ;;
centos | rhel)
    sudo yum update -y
    sudo yum install -y curl wget gnupg2 yum-utils device-mapper-persistent-data lvm2
    ;;
fedora)
    sudo dnf update -y
    sudo dnf install -y curl wget gnupg2 dnf-utils device-mapper-persistent-data lvm2
    ;;
*)
    echo "ERROR: Unsupported distribution: $DISTRO"
    exit 1
    ;;
esac

# Install Docker
echo "Installing Docker..."
case $DISTRO in
ubuntu | debian)
    sudo apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true
    curl -fsSL https://download.docker.com/linux/$DISTRO/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/$DISTRO $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt update -y
    sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    ;;
centos | rhel)
    sudo yum remove -y docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine 2>/dev/null || true
    sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    sudo yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    ;;
fedora)
    sudo dnf remove -y docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-selinux docker-engine-selinux docker-engine 2>/dev/null || true
    sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
    sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    ;;
esac

sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER

# Install NVIDIA Container Toolkit
echo "Installing NVIDIA Container Toolkit..."
case $DISTRO in
ubuntu | debian)
    distribution=$(
        . /etc/os-release
        echo $ID$VERSION_ID
    )
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list |
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' |
        sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    sudo apt update -y
    sudo apt install -y nvidia-container-toolkit
    ;;
centos | rhel)
    distribution=$(
        . /etc/os-release
        echo $ID$VERSION_ID
    )
    curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.repo |
        sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo
    sudo yum install -y nvidia-container-toolkit
    ;;
fedora)
    distribution=$(
        . /etc/os-release
        echo $ID$VERSION_ID
    )
    curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.repo |
        sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo
    sudo dnf install -y nvidia-container-toolkit
    ;;
esac

sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Cleanup
case $DISTRO in
ubuntu | debian)
    sudo apt autoremove -y
    sudo apt autoclean
    ;;
centos | rhel | fedora)
    sudo yum clean all
    ;;
esac
