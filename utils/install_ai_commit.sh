#!/bin/bash
# Installer for AI Commit Message Generator

set -e

install_hook() {
    # Get the directory where this script is located
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # Check if ai_commit.py exists
    if [ ! -f "$SCRIPT_DIR/ai_commit.py" ]; then
        echo "Error: ai_commit.py not found in $SCRIPT_DIR"
        exit 1
    fi

    # Check if we're in a git repository
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "Error: Not in a git repository. Run this from within a git repository."
        exit 1
    fi

    # Get the git hooks directory
    GIT_DIR=$(git rev-parse --git-dir)
    HOOKS_DIR="$GIT_DIR/hooks"

    # Create hooks directory if it doesn't exist
    mkdir -p "$HOOKS_DIR"

    # Create the prepare-commit-msg hook
    HOOK_PATH="$HOOKS_DIR/prepare-commit-msg"

    echo "#!/bin/sh" >"$HOOK_PATH"
    echo "# AI Commit Message Generator" >>"$HOOK_PATH"
    echo "python \"$SCRIPT_DIR/ai_commit.py\" \"\$@\"" >>"$HOOK_PATH"

    # Make it executable
    chmod +x "$HOOK_PATH"

    echo "✅ Successfully installed AI commit message generator!"
    echo "Hook installed at: $HOOK_PATH"

    # Check for OPENAI_API_KEY
    if [ -z "$OPENAI_API_KEY" ]; then
        echo ""
        echo "⚠️ OPENAI_API_KEY not found in environment!"
        echo "Add your OpenAI API key to a .env file in your repository:"
        echo "echo \"OPENAI_API_KEY=your_key_here\" >> .env"
        echo ""
        echo "Or set it as an environment variable:"
        echo "export OPENAI_API_KEY=your_key_here"
    fi
}

# Install the hook
install_hook
