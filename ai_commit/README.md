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