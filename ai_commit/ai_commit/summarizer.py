import asyncio

from .llm_backend_async import get_async_llm_backend


def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def split_diff_by_file(diff_text):
    # Splits a unified diff into per-file chunks
    files = []
    current = []
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git"):
            if current:
                files.append("".join(current))
                current = []
        current.append(line)
    if current:
        files.append("".join(current))
    return files


async def summarize_with_llm(prompt, llm, model):
    try:
        return await llm.complete(prompt, model)
    except Exception:
        return None


async def async_summarize_diff(diff_text):
    llm, model = get_async_llm_backend()
    files = split_diff_by_file(diff_text)
    if not files:
        return "No changes detected."
    file_summaries = []
    for file_diff in files:
        prompt = f"""
Summarize the following git diff for a single file in one concise sentence, following the format: [type] brief description. Types: [feat], [fix], [docs], [style], [refactor], [test], [chore], [delete], etc. Be descriptive but brief. Just return the commit message, nothing else.\n\nGit diff:\n{file_diff[:2000]}
"""
        summary = await summarize_with_llm(prompt, llm, model)
        if not summary:
            summary = "[chore] update file"
        file_summaries.append(summary)
    # Recursively summarize if too many summaries
    while len(file_summaries) > 5:
        new_summaries = []
        for batch in chunk_list(file_summaries, 5):
            batch_prompt = "\n".join(batch)
            prompt = f"""
Summarize the following commit messages into a single concise commit message (20 words or less), following the format: [type] brief description.\n\nMessages:\n{batch_prompt}
"""
            summary = await summarize_with_llm(prompt, llm, model)
            if not summary:
                summary = "[chore] update files"
            new_summaries.append(summary)
        file_summaries = new_summaries
    # Final summary
    if len(file_summaries) == 1:
        return file_summaries[0]
    else:
        final_prompt = "\n".join(file_summaries)
        prompt = f"""
Summarize the following commit messages into a single concise commit message (20 words or less), following the format: [type] brief description.\n\nMessages:\n{final_prompt}
"""
        summary = await summarize_with_llm(prompt, llm, model)
        if not summary:
            summary = "[chore] update files"
        return summary


def summarize_diff(diff_text):
    return asyncio.run(async_summarize_diff(diff_text))
