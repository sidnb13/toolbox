import os
import subprocess
import sys

from dotenv import load_dotenv

from .map_reduce_summarizer import map_reduce_summarize

load_dotenv()


def get_staged_files():
    # Returns list of (status, filename) tuples
    output = subprocess.check_output(
        ["git", "diff", "--cached", "--name-status"], universal_newlines=True
    )
    files = []
    for line in output.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 2:
            status, filename = parts
            files.append((status, filename))
        elif len(parts) == 3:  # e.g. R100	old	new
            status, old, new = parts
            files.append((status, f"{old} -> {new}"))
    return files


def get_staged_diff():
    return subprocess.check_output(
        ["git", "diff", "--cached", "--no-color"], universal_newlines=True
    )


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "install-hook":
        git_dir = subprocess.check_output(
            ["git", "rev-parse", "--git-dir"], universal_newlines=True
        ).strip()
        hook_path = os.path.join(git_dir, "hooks", "commit-msg")
        script = """#!/bin/sh\nai-commit \"$1\"\n"""
        with open(hook_path, "w") as f:
            f.write(script)
        os.chmod(hook_path, 0o755)
        print(
            f"[ai-commit] Installed commit-msg hook at {hook_path} (it will now auto-summarize your commits!)"
        )
        return

    if len(sys.argv) < 2:
        print(
            "ai-commit-msg: This script should be run as a commit-msg hook or as 'ai-commit install-hook'."
        )
        sys.exit(1)

    commit_msg_file = sys.argv[1]
    # Read current commit message (may be empty)
    with open(commit_msg_file) as f:
        current_msg = f.read().strip()
    # Skip if message is already provided (e.g. merge commit)
    if current_msg and not current_msg.startswith("#"):
        return
    diff = get_staged_diff()
    if not diff.strip():
        print("No staged changes detected.")
        return
    try:
        commit_message = map_reduce_summarize(diff)
    except Exception as e:
        print(f"[ai-commit-msg] Error during commit message generation: {e}")
        return
    if commit_message:
        with open(commit_msg_file, "w") as f:
            f.write(commit_message + "\n\n")
            if current_msg:
                f.write(current_msg)
        print(f"[ai-commit-msg] Generated commit message: {commit_message}")
    else:
        print("[ai-commit-msg] Failed to generate commit message.")


if __name__ == "__main__":
    main()
