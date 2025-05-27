import asyncio
import os
import re

from .llm_backend_async import get_async_llm_backend

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


async def async_file_level_summary(diff_chunk, filename, llm, model=None):
    prompt = f"""
You are an expert software engineer. For the following file ({filename}) git diff excerpt, summarize:
- What was the main purpose or intent?
- What functional or structural changes were made ("fixed bug in...", "refactored to...", etc)?
- Be concise, ~10-30 words, like a human commit message for this file only.

DIFF:
{diff_chunk}
"""
    return await llm.complete(prompt, model=model)


async def async_reduce_summaries(file_summaries, codebase_context, llm, model):
    joined = "\n".join([f"{fname}: {summary}" for fname, summary in file_summaries])
    prompt = f"""
You are an expert software developer writing git commit messages. The following is a list of summaries of changed files:
{joined}

Project context:
{codebase_context}

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

Then write a single, short (max 1 line, {COMMIT_MSG_WORD_LIMIT} words), human-like commit message that best describes the overall intent and effect of all these changes together. Use correct tense and summarize as if for your teammates.

Format: <type>: <description>
Example: "feat: add user authentication system"
Example: "fix: resolve memory leak in data processing"
Example: "docs: update API documentation"
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
        for commit_type in conventional_types
    )

    if not has_prefix:
        # Fallback: try to determine type based on keywords in the message
        message_lower = result.lower()
        if any(
            word in message_lower
            for word in ["add", "implement", "create", "introduce"]
        ):
            result = f"feat: {result}"
        elif any(
            word in message_lower for word in ["fix", "resolve", "correct", "repair"]
        ):
            result = f"fix: {result}"
        elif any(word in message_lower for word in ["update", "change", "modify"]):
            result = f"chore: {result}"
        else:
            result = f"chore: {result}"

    return result


def map_reduce_summarize(diff, codebase_context=None):
    # Entrypoint: runs the async function using asyncio.
    return asyncio.run(
        async_map_reduce_summarize(diff, codebase_context=codebase_context)
    )


async def async_map_reduce_summarize(diff, codebase_context=None):
    llm, model = get_async_llm_backend()
    files = split_diff_by_file(diff)
    codebase_context = codebase_context or get_codebase_context()
    tasks = []
    for fname, filediff in files:
        truncated = filediff[:3000] + ("..." if len(filediff) > 3000 else "")
        tasks.append(async_file_level_summary(truncated, fname, llm, model=model))
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
            file_summaries, codebase_context, llm, model
        )
    except Exception:
        final_summary = "; ".join(s for _, s in file_summaries)
    return final_summary
