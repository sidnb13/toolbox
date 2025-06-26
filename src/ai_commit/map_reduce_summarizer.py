import asyncio
import os
import re
import subprocess

from llm_backend_async import get_async_llm_backend

COMMIT_MSG_WORD_LIMIT = int(os.getenv("AI_COMMIT_MSG_WORD_LIMIT", 10))


def split_diff_by_file(diff):
    """Split a git diff into (filename, diff_for_file) tuples."""
    files = []
    cur_file = None
    cur_lines = []
    filename_pattern = re.compile(r"^diff --git a/(.*?) b/(.*?)$")
    for line in diff.splitlines():
        m = filename_pattern.match(line)
        if m:
            if cur_file and cur_lines:
                files.append((cur_file, "\n".join(cur_lines)))
            cur_file = m.group(2)
            cur_lines = [line]
        else:
            if cur_file:
                cur_lines.append(line)
    if cur_file and cur_lines:
        files.append((cur_file, "\n".join(cur_lines)))
    return files


def get_codebase_context():
    # Tries to read README.md or other top-level files for context; truncated to avoid prompt bloat
    context = ""
    if os.path.exists("README.md"):
        with open("README.md") as f:
            content = f.read(2000)  # up to 2k chars
            context += f"README.md (truncated):\n{content}\n"
    return context


# New: Compute diff stats for each file
def get_diff_stats(diff):
    stats = {}
    filename = None
    added = 0
    removed = 0
    change_type = None
    filename_pattern = re.compile(r"^diff --git a/(.*?) b/(.*?)$")
    for line in diff.splitlines():
        m = filename_pattern.match(line)
        if m:
            if filename is not None:
                stats[filename] = {
                    "added": added,
                    "removed": removed,
                    "change_type": change_type,
                }
            filename = m.group(2)
            added = 0
            removed = 0
            change_type = None
        elif line.startswith("+++ b/") or line.startswith("--- a/"):
            continue
        elif line.startswith("@@"):
            continue
        elif line.startswith("+") and not line.startswith("+++ "):
            added += 1
        elif line.startswith("-") and not line.startswith("--- "):
            removed += 1
        elif line.startswith("new file mode"):
            change_type = "A"
        elif line.startswith("deleted file mode"):
            change_type = "D"
    if filename is not None:
        stats[filename] = {
            "added": added,
            "removed": removed,
            "change_type": change_type,
        }
    return stats


async def async_file_level_summary(
    diff_chunk, filename, llm, model=None, diff_stats=None, word_limit=30
):
    stats_str = ""
    if diff_stats and filename in diff_stats:
        s = diff_stats[filename]
        stats_str = f"\n[Stats] +{s['added']} -{s['removed']} ChangeType: {s['change_type'] or 'M'}"
    prompt = f"""
You are an expert software engineer. For the following file ({filename}) git diff excerpt, summarize:
- What was the main purpose or intent?
- What functional or structural changes were made (e.g., 'fixed bug in...', 'refactored to...', etc)?
- Why were these changes made? (if possible)
- Be concise, {word_limit} words max, like a human commit message for this file only.
- Include the most important details, not just generic statements.
- If the change is trivial (formatting, comments), say so.
- Use the diff stats for context: {stats_str}

DIFF:
{diff_chunk}
"""
    return await llm.complete(prompt, model=model)


def get_recent_commit_messages(n=5):
    try:
        output = subprocess.check_output(
            ["git", "log", f"-n{n}", "--pretty=format:%s"], universal_newlines=True
        )
        return output.strip().split("\n")
    except Exception:
        return []


async def async_reduce_summaries(
    file_summaries, codebase_context, llm, model, diff_stats, word_limit=30, diff=None
):
    joined = "\n".join(
        [
            f"{fname}: {summary} [Stats: +{diff_stats.get(fname, {}).get('added', 0)} -{diff_stats.get(fname, {}).get('removed', 0)} Type: {diff_stats.get(fname, {}).get('change_type', 'M')}]"
            for fname, summary in file_summaries
        ]
    )
    recent_commits = get_recent_commit_messages(5)
    recent_commit_str = "\n".join(recent_commits)
    breaking_change = False
    # Check for breaking change in diff or summaries
    if diff and (
        "BREAKING CHANGE" in diff
        or any(
            any(
                word in s.lower()
                for word in [
                    "breaking change",
                    "remove",
                    "delete",
                    "rename",
                    "change signature",
                ]
            )
            for _, s in file_summaries
        )
    ):
        breaking_change = True
    prompt = f"""
You are an expert software developer writing git commit messages. The following is a list of summaries of changed files, with diff stats:
{joined}

Project context:
{codebase_context}

Recent commit messages for this repo:
{recent_commit_str}

First, determine the most appropriate conventional commit type from this list:
- feat: A new feature
- fix: A bug fix
- docs: Documentation only changes
- style: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc)
- refactor: A code change that neither fixes a bug nor adds a feature
- perf: A code change that improves performance
- test: Adding missing tests or correcting existing tests
- build: Changes that affect the build system or external dependencies
- ci: Changes to CI configuration files and scripts
- chore: Other changes that don't modify src or test files
- revert: Reverts a previous commit

If the changes are a breaking change (e.g., 'BREAKING CHANGE' in the diff, or major API removals/renames/signature changes), use an exclamation mark in the type (e.g., 'feat!:' or 'fix!:').

Then write a single, short (max 1 line, {word_limit} words), human-like commit message that best describes the overall intent and effect of all these changes together. Prioritize the most significant changes, ignore trivial ones. Use correct tense and summarize as if for your teammates.

Format: <type>: <description>
Example: "feat: add user authentication system"
Example: "fix: resolve memory leak in data processing"
Example: "docs: update API documentation"
Example: "feat!: remove deprecated API (BREAKING CHANGE)"
"""
    result = await llm.complete(prompt, model)

    # Ensure the result has a conventional commit prefix
    result = result.strip()
    conventional_types = [
        "feat",
        "fix",
        "docs",
        "style",
        "refactor",
        "perf",
        "test",
        "build",
        "ci",
        "chore",
        "revert",
    ]
    has_prefix = any(
        result.lower().startswith(f"{commit_type}:")
        or result.lower().startswith(f"{commit_type}!:")
        for commit_type in conventional_types
    )

    # Fallback: If the message is too generic or doesn't mention any file or change, generate a message from file names/types
    if (
        not has_prefix
        or len(result.split()) < 3
        or any(
            bad in result.lower()
            for bad in ["update", "refactor", "change", "fix", "build"]
        )
    ):
        # Use the most changed file as the main subject
        if file_summaries:
            most_changed = max(
                diff_stats.items(), key=lambda x: x[1]["added"] + x[1]["removed"]
            )[0]
            fallback_msg = f"chore: update {most_changed} and related files"
        else:
            fallback_msg = "chore: update project files"
        result = fallback_msg

    # Post-process: If breaking change detected, force exclamation mark
    if breaking_change and not any(
        result.startswith(f"{t}!:") for t in ["feat", "fix"]
    ):
        # Try to upgrade feat/fix to feat!/fix!
        for t in ["feat", "fix"]:
            if result.startswith(f"{t}:"):
                result = result.replace(f"{t}:", f"{t}!:", 1)
                break
        else:
            # If not feat/fix, just prepend feat!:
            result = f"feat!: {result} (BREAKING CHANGE)"
    return result


def map_reduce_summarize(diff, codebase_context=None, word_limit=None):
    # Entrypoint: runs the async function using asyncio.
    return asyncio.run(
        async_map_reduce_summarize(
            diff, codebase_context=codebase_context, word_limit=word_limit
        )
    )


async def async_map_reduce_summarize(diff, codebase_context=None, word_limit=None):
    llm_obj, model = get_async_llm_backend()
    async with llm_obj as llm:
        files = split_diff_by_file(diff)
        codebase_context = codebase_context or get_codebase_context()
        diff_stats = get_diff_stats(diff)
        word_limit = word_limit or int(os.getenv("AI_COMMIT_MSG_WORD_LIMIT", 30))
        tasks = []
        for fname, filediff in files:
            truncated = filediff[:3000] + ("..." if len(filediff) > 3000 else "")
            tasks.append(
                async_file_level_summary(
                    truncated,
                    fname,
                    llm,
                    model=model,
                    diff_stats=diff_stats,
                    word_limit=word_limit,
                )
            )
        # Execute all map tasks in parallel
        file_results = await asyncio.gather(*tasks, return_exceptions=True)
        file_summaries = []
        for i, res in enumerate(file_results):
            fname = files[i][0]
            summary = res
            if isinstance(res, Exception):
                summary = f"(LLM error for {fname}: {res})"
            file_summaries.append((fname, summary))
        try:
            final_summary = await async_reduce_summaries(
                file_summaries,
                codebase_context,
                llm,
                model,
                diff_stats,
                word_limit=word_limit,
                diff=diff,
            )
        except Exception:
            final_summary = "; ".join(s for _, s in file_summaries)
        return final_summary
