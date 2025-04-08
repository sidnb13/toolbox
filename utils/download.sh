#!/bin/bash

# Create scripts directory if it doesn't exist
mkdir -p $(git rev-parse --show-toplevel)/scripts

URL="https://raw.githubusercontent.com/sidnb13/toolbox/refs/heads/master/utils"

# Download both files to scripts directory
curl -o scripts/ai_commit.py $URL/ai_commit.py
curl -o scripts/install_ai_commit.sh $URL/install_ai_commit.sh

# Run the installer
bash $(git rev-parse --show-toplevel)/scripts/install_ai_commit.sh

echo "✅ Installation complete! Files are in $(git rev-parse --show-toplevel)/scripts/"
