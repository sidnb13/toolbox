import os

import openai


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return openai.OpenAI(api_key=api_key)


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


def summarize_with_llm(prompt):
    client = get_openai_client()
    if not client:
        return None
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None


def summarize_diff(diff_text):
    files = split_diff_by_file(diff_text)
    if not files:
        return "No changes detected."
    file_summaries = []
    for file_diff in files:
        prompt = f"""
Summarize the following git diff for a single file in one concise sentence, following the format: [type] brief description. Types: [feat], [fix], [docs], [style], [refactor], [test], [chore], [delete], etc. Be descriptive but brief. Just return the commit message, nothing else.\n\nGit diff:\n{file_diff[:2000]}
"""
        summary = summarize_with_llm(prompt)
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
            summary = summarize_with_llm(prompt)
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
        summary = summarize_with_llm(prompt)
        if not summary:
            summary = "[chore] update files"
        return summary
