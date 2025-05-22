import os

import openai
from together import AsyncTogether

DEFAULT_MODEL = "gpt-4.1-nano"


class AsyncLLMBackend:
    async def complete(self, prompt, model=None):
        raise NotImplementedError()


class AsyncOpenAIBackend(AsyncLLMBackend):
    DEFAULT_MODEL = "gpt-4-1106-preview"

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable must be set for OpenAI backend."
            )
        self.client = openai.AsyncOpenAI(api_key=self.api_key)

    async def complete(self, prompt, model=None):
        model = model or self.DEFAULT_MODEL
        response = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.3,
        )
        return response.choices[0].message.content


class AsyncTogetherBackend(AsyncLLMBackend):
    DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free"

    def __init__(self):
        self.api_key = os.getenv("TOGETHER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "TOGETHER_API_KEY environment variable must be set for TogetherAI backend."
            )
        self.client = AsyncTogether(api_key=self.api_key)

    async def complete(self, prompt, model=None):
        model = model or self.DEFAULT_MODEL
        response = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.3,
        )
        return response.choices[0].message.content


MODEL_PROVIDER_MAP = {
    "gpt-4.1": AsyncOpenAIBackend,
    "gpt-4.1-nano": AsyncOpenAIBackend,
    "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free": AsyncTogetherBackend,
}


def get_async_llm_backend():
    model_descr = os.getenv("AI_COMMIT_MODEL", DEFAULT_MODEL)
    for prefix, backend_cls in MODEL_PROVIDER_MAP.items():
        if model_descr.startswith(prefix):
            return backend_cls(), model_descr
    raise ValueError(
        f"No backend found for model '{model_descr}'. Supported prefixes: {list(MODEL_PROVIDER_MAP.keys())}"
    )
