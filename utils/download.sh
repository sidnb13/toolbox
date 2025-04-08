#!/bin/bash

# Create scripts directory if it doesn't exist
mkdir -p $(git rev-parse --show-toplevel)/scripts

# Download both files to scripts directory
curl -o $(git rev-parse --show-toplevel)/scripts/ai_commit.py https://raw.githubusercontent.com/username/repo/main/ai_commit.py
curl -o $(git rev-parse --show-toplevel)/scripts/install.sh https://raw.githubusercontent.com/username/repo/main/install.sh

# Make them executable
chmod +x $(git rev-parse --show-toplevel)/scripts/ai_commit.py $(git rev-parse --show-toplevel)/scripts/install.sh

# Run the installer
$(git rev-parse --show-toplevel)/scripts/install.sh

echo "✅ Installation complete! Files are in $(git rev-parse --show-toplevel)/scripts/"
