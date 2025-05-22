import os

import aiohttp

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None


class AsyncLLMBackend:
    async def complete(self, prompt, model=None):
        raise NotImplementedError()


class AsyncTogetherLlamaBackend(AsyncLLMBackend):
    DEFAULT_MODEL = "togethercomputer/llama-3-70b-8192-turbo"
    ENDPOINT = "https://api.together.xyz/v1/chat/completions"

    def __init__(self):
        self.api_key = os.getenv("TOGETHER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "TOGETHER_API_KEY environment variable must be set for TogetherAI backend."
            )

    async def complete(self, prompt, model=None):
        model = model or self.DEFAULT_MODEL
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 512,
            "temperature": 0.3,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.ENDPOINT, headers=headers, json=payload, timeout=60
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["choices"][0]["message"]["content"]


class AsyncOpenAIBackend(AsyncLLMBackend):
    def __init__(self):
        if AsyncOpenAI is None:
            raise ImportError("openai-python is not installed.")
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable must be set for OpenAI backend."
            )
        self.client = AsyncOpenAI(api_key=self.api_key)

    async def complete(self, prompt, model=None):
        model = model or "gpt-3.5-turbo"
        response = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.3,
        )
        return response.choices[0].message.content


def get_async_llm_backend():
    model_descr = os.getenv(
        "AI_COMMIT_MODEL", "togethercomputer/llama-3-70b-8192-turbo"
    )
    if (
        model_descr.startswith("together")
        or model_descr.startswith("llama")
        or "togethercomputer" in model_descr.lower()
    ):
        return AsyncTogetherLlamaBackend(), model_descr
    elif model_descr.startswith("gpt-") or model_descr.startswith("openai"):
        return AsyncOpenAIBackend(), model_descr
    else:
        return AsyncTogetherLlamaBackend(), model_descr
