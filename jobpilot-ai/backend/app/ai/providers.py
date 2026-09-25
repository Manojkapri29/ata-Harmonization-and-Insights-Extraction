"""AI provider abstraction.

AI is OPTIONAL. With AI_PROVIDER=none every feature works with deterministic rules/templates.
When a provider is configured it is only used to *rephrase* text, and every output is checked by
`guard.py` so it can't introduce skills, numbers, employers or credentials that aren't in your source data.

Providers:
    openai     any OpenAI-compatible /chat/completions endpoint (OpenAI, Groq, Together, LM Studio, vLLM, ...)
    anthropic  Claude via the official `anthropic` SDK
    ollama     local models via Ollama's /api/chat
"""
from __future__ import annotations

import logging

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)


class AIError(Exception):
    pass


class AIProvider:
    name = "none"

    @property
    def available(self) -> bool:
        return False

    def generate(self, system: str, prompt: str, max_tokens: int = 2000) -> str:
        raise AIError("No AI provider configured (AI_PROVIDER=none). Rule-based generation is used instead.")

    def describe(self) -> dict:
        return {"provider": self.name, "available": self.available, "model": getattr(self, "model", "")}


class NoAI(AIProvider):
    pass


class OpenAICompatible(AIProvider):
    name = "openai"

    def __init__(self, api_key: str, base_url: str, model: str, timeout: int):
        self.api_key, self.base_url, self.model, self.timeout = api_key, base_url.rstrip("/"), model, timeout

    @property
    def available(self) -> bool:
        return bool(self.model and (self.api_key or "localhost" in self.base_url or "127.0.0.1" in self.base_url))

    def generate(self, system: str, prompt: str, max_tokens: int = 2000) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body = {"model": self.model, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"] or ""
        except (httpx.HTTPError, KeyError, IndexError) as e:
            raise AIError(f"OpenAI-compatible request failed: {e}") from e


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, effort: str, fallbacks: bool, timeout: int):
        self.api_key, self.model, self.effort, self.fallbacks, self.timeout = api_key, model, effort, fallbacks, timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, system: str, prompt: str, max_tokens: int = 4000) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key, timeout=float(self.timeout))
        kwargs = dict(model=self.model, max_tokens=max_tokens, system=system,
                      messages=[{"role": "user", "content": prompt}])
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        try:
            if self.fallbacks:
                # server-side fallback: if the model declines, the API retries on a fallback model in the same call
                response = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                                       **kwargs)
            else:
                response = client.messages.create(**kwargs)
        except anthropic.RateLimitError as e:
            raise AIError("Anthropic rate limit reached; try again shortly.") from e
        except anthropic.AuthenticationError as e:
            raise AIError("Anthropic API key was rejected. Check ANTHROPIC_API_KEY.") from e
        except anthropic.APIStatusError as e:
            raise AIError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AIError(f"Could not reach the Anthropic API: {e}") from e
        if response.stop_reason == "refusal":
            raise AIError("The model declined this request.")
        return "".join(b.text for b in response.content if b.type == "text")


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: int):
        self.base_url, self.model, self.timeout = base_url.rstrip("/"), model, timeout

    @property
    def available(self) -> bool:
        return bool(self.model)

    def generate(self, system: str, prompt: str, max_tokens: int = 2000) -> str:
        body = {"model": self.model, "stream": False, "options": {"num_predict": max_tokens},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        try:
            r = httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except (httpx.HTTPError, KeyError) as e:
            raise AIError(f"Ollama request failed ({self.base_url}): {e}") from e


def get_provider(override: dict | None = None) -> AIProvider:
    """Provider from env, optionally overridden by the Settings page (provider/model only; keys stay in env)."""
    s = get_settings()
    o = override or {}
    kind = (o.get("provider") or s.ai_provider or "none").lower()
    if kind == "openai":
        return OpenAICompatible(s.openai_api_key, o.get("base_url") or s.openai_base_url,
                                o.get("model") or s.openai_model, s.ai_timeout_seconds)
    if kind == "anthropic":
        return AnthropicProvider(s.anthropic_api_key, o.get("model") or s.anthropic_model, s.anthropic_effort,
                                 s.anthropic_fallbacks, s.ai_timeout_seconds)
    if kind == "ollama":
        return OllamaProvider(o.get("base_url") or s.ollama_base_url, o.get("model") or s.ollama_model,
                              s.ai_timeout_seconds)
    return NoAI()
