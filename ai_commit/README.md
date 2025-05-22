# ai_commit


# ai_commit – LLM MapReduce Commit Messages

**Short, high-level overview:**

This is a standalone AI-powered commit message utility.
It splits staged git diffs by file, summarizes each in parallel using an LLM (default: TogetherAI Llama-3.3 70B Turbo), then reduces to a single concise commit message that reflects overall intent and project context.

Install (from your project):
```
pip install "git+https://github.com/sidbaskaran/toolbox.git#subdirectory=ai_commit"
```

**One-line install as a git commit hook:**
```
ai-commit install-hook
```

Default model: TogetherAI Llama-3.3 70B Turbo (set `TOGETHER_API_KEY`). For OpenAI models, set `AI_COMMIT_MODEL` and `OPENAI_API_KEY`.

## Using as a pre-commit hook

To use ai_commit with [pre-commit](https://pre-commit.com/), add this to your `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/sidbaskaran/toolbox
  rev: <commit-or-tag>
  hooks:
    - id: ai-commit
```

Or, for local development:

```yaml
- repo: local
  hooks:
    - id: ai-commit
      name: ai-commit
      entry: ai-commit
      language: python
      types: [python]
      files: .*
      description: "AI-powered commit message generator"
```

## Dry run

To preview the commit message without making a commit, run:

```
ai-commit --dry-run
```

This will show the staged diff and the generated commit message, but will not write or commit anything.

## Editor integration (prepare-commit-msg hook)

To have the AI-generated commit message appear in your editor when you run `git commit`, install the hook:

```
ai-commit install-hook
```

This sets up a `prepare-commit-msg` hook, so the message is pre-filled for you to review/edit before saving.

## Hook types explained

| Hook type            | When it runs         | What it does / When to use it                |
|--------------------- |---------------------|----------------------------------------------|
| pre-commit           | Before commit editor | Checks/edits files before commit (not message) |
| commit-msg           | After editor closes  | Edits/creates commit message after editing   |
| prepare-commit-msg   | Before editor opens  | Pre-fills commit message in editor (RECOMMENDED for ai_commit) |

**ai_commit** is designed to be used as a `prepare-commit-msg` hook for the best experience.