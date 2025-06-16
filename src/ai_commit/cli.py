import argparse
import asyncio
import os
import subprocess
import sys

from dotenv import load_dotenv
from llm_backend_async import MODEL_PROVIDER_MAP, get_async_llm_backend
from map_reduce_summarizer import map_reduce_summarize


async def test_api_key(llm):
    """Make a minimal test request to verify the API key works."""
    try:
        await llm.complete("test")
        return True
    except Exception as e:
        print(f"Error: API key validation failed: {str(e)}")
        return False


async def validate_api_key():
    """Validate that the appropriate API key is set and works."""
    model_descr = os.getenv("AI_COMMIT_MODEL", "gpt-4.1-nano")
    for prefix, backend_cls in MODEL_PROVIDER_MAP.items():
        if model_descr.startswith(prefix):
            try:
                llm, _ = get_async_llm_backend()
                if await test_api_key(llm):
                    return
                sys.exit(1)
            except ValueError as e:
                print(f"Error: {str(e)}")
                sys.exit(1)
    print(
        f"Error: No backend found for model '{model_descr}'. Supported prefixes: {list(MODEL_PROVIDER_MAP.keys())}"
    )
    sys.exit(1)


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
    load_dotenv(override=True)
    asyncio.run(validate_api_key())

    parser = argparse.ArgumentParser(description="AI-powered commit message generator.")
    parser.add_argument(
        "commit_msg_file", nargs="?", help="Path to commit message file (from git hook)"
    )
    parser.add_argument("install_hook", nargs="?", help=argparse.SUPPRESS)
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be committed, but don't actually write the commit message.",
    )
    args, unknown = parser.parse_known_args()

    # Support legacy 'install-hook' positional
    if (args.install_hook == "install-hook") or (
        args.commit_msg_file == "install-hook"
    ):
        git_dir = subprocess.check_output(
            ["git", "rev-parse", "--git-dir"], universal_newlines=True
        ).strip()
        hook_path = os.path.join(git_dir, "hooks", "prepare-commit-msg")
        script = """#!/bin/sh\nai-commit \"$1\"\n"""
        with open(hook_path, "w") as f:
            f.write(script)
        os.chmod(hook_path, 0o755)
        print(
            f"[ai-commit] Installed prepare-commit-msg hook at {hook_path} (it will now auto-summarize your commits and pre-fill the message in your editor!)"
        )
        return

    if args.dry_run:
        diff = get_staged_diff()
        if not diff.strip():
            print("No staged changes detected.")
            return
        try:
            commit_message = map_reduce_summarize(diff)
        except Exception as e:
            print(f"[ai-commit-msg] Error during commit message generation: {e}")
            return
        print("\n[ai-commit-msg] Staged files:")
        for status, fname in get_staged_files():
            print(f"  {status}\t{fname}")
        print("\n[ai-commit-msg] Staged diff:\n")
        print(diff)
        print(
            "\n[ai-commit-msg] DRY RUN: Would generate the following commit message:\n"
        )
        print(commit_message)
        return

    if not args.commit_msg_file:
        print(
            "ai-commit-msg: This script should be run as a commit-msg hook, as 'ai-commit install-hook', or with --dry-run."
        )
        sys.exit(1)

    commit_msg_file = args.commit_msg_file
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
