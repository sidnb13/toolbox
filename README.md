# Toolbox

Unified toolbox containing ML development tools, AI-powered utilities, and GPU monitoring tools for bootstrapping and managing research projects.

## Packages

This repository contains three main packages:

- **mltoolbox**: ML Development Environment Management Tools
- **ai_commit**: AI-powered commit message generation utility
- **instancebot**: Lambda Labs GPU availability watchdog

## Installation

### Install from GitHub (Recommended)

You can install individual packages or all packages directly from GitHub:

```bash
# Install only mltoolbox
pip install "toolbox[mltoolbox] @ git+https://github.com/sidbaskaran/toolbox.git"

# Install only ai-commit
pip install "toolbox[ai-commit] @ git+https://github.com/sidbaskaran/toolbox.git"

# Install only instancebot
pip install "toolbox[instancebot] @ git+https://github.com/sidbaskaran/toolbox.git"

# Install all packages
pip install "toolbox[all] @ git+https://github.com/sidbaskaran/toolbox.git"

# Install for development
pip install "toolbox[all,dev] @ git+https://github.com/sidbaskaran/toolbox.git"
```

### Local Development Installation

```bash
# Clone the repository
git clone https://github.com/sidbaskaran/toolbox.git
cd toolbox

# Install in development mode with all packages
pip install -e ".[all,dev]"

# Or install specific packages
pip install -e ".[mltoolbox]"
pip install -e ".[ai-commit]"
pip install -e ".[instancebot]"
```

## Usage

After installation, you'll have access to the following command-line tools:

- `mltoolbox`: ML development environment management
- `ai-commit`: AI-powered commit message generation
- `instancebot`: Lambda Labs GPU availability monitoring and Slack notifications

### Instancebot Usage

Monitor Lambda Labs GPU availability and get Slack notifications:

```bash
# Basic usage - watch for specific GPU types
instancebot --api-key YOUR_API_KEY --slack-webhook YOUR_WEBHOOK --type "H100" --type "A100"

# Watch with region filtering
instancebot --api-key YOUR_API_KEY --slack-webhook YOUR_WEBHOOK --type "H100" --region "us-west"

# Watch with GPU count filtering
instancebot --api-key YOUR_API_KEY --slack-webhook YOUR_WEBHOOK --type "A100" --min-gpus 8

# Run once without continuous monitoring
instancebot --api-key YOUR_API_KEY --slack-webhook YOUR_WEBHOOK --type "H100" --once

# Use environment variables (recommended)
export LAMBDA_API_KEY="your_api_key"
export SLACK_WEBHOOK_URL="your_webhook_url"
instancebot --type "H100" --type "A100"
```

## Package Structure

```
src/
├── mltoolbox/          # ML development tools
│   ├── cli/
│   ├── utils/
│   ├── templates/
│   └── base/
├── ai_commit/          # AI commit message generator
│   └── ai_commit/
│       ├── cli.py
│       ├── llm_backend_async.py
│       └── map_reduce_summarizer.py
└── instancebot/        # Lambda Labs GPU watchdog
    ├── cli.py
    └── lambda_watchdog.py
```
