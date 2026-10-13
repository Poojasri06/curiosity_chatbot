"""AI providers.

The rest of the service only talks to `LLMProvider`. Free-tier services such as Google
Gemini and Groq share one OpenAI-compatible client, so switching provider is a settings
change (LLM_PROVIDER, LLM_API_KEY), not a code change.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Protocol

import httpx

from .config import PROVIDER_DEFAULTS, Settings
from .prompts import build_messages

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
THINK_TAGS = re.compile(r"<think>.*?</think>", re.S | re.I)


class ProviderError(Exception):
    """The AI provider could not answer. Messages never contain the API key."""


class LLMProvider(Protocol):
    name: str

    def generate(self, message: str, context: list[str]) -> str:
        """Return an answer to `message`, using `context` (retrieved text) if given."""
        ...


class EchoProvider:
    """Test provider: repeats the question. Lets the service run without any API key."""

    name = "echo"

    def generate(self, message: str, context: list[str]) -> str:
        return f"(echo) You asked: {message}"


class OpenAICompatibleProvider:
    """Calls any service that implements POST {base_url}/chat/completions."""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
        retry_delay: float = 0.5,
    ):
        self.name = name
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._retry_delay = retry_delay
        self._client = client or httpx.Client(timeout=timeout)

    def generate(self, message: str, context: list[str]) -> str:
        payload = {
            "model": self._model,
            "messages": build_messages(message, context),
            "temperature": 0.3,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        response = None
        for attempt in (1, 2):
            try:
                response = self._client.post(self._url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise ProviderError(f"{self.name} request failed: {type(exc).__name__}") from None
                time.sleep(self._retry_delay)
                continue
            if response.status_code in RETRY_STATUSES and attempt == 1:
                time.sleep(self._retry_delay)
                continue
            break
        if response.status_code != 200:
            raise ProviderError(f"{self.name} returned HTTP {response.status_code}")
        return self._read_answer(response)

    def _read_answer(self, response: httpx.Response) -> str:
        try:
            text = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError(f"{self.name} sent an unexpected response") from None
        text = THINK_TAGS.sub("", text or "").strip()
        if not text:
            raise ProviderError(f"{self.name} sent an empty answer")
        return text


def get_provider(settings: Settings, client: httpx.Client | None = None) -> LLMProvider:
    name = settings.llm_provider
    if name == "echo":
        return EchoProvider()
    if name not in PROVIDER_DEFAULTS:
        available = ", ".join(["echo", *sorted(PROVIDER_DEFAULTS)])
        raise ValueError(f"Unknown LLM_PROVIDER '{name}'. Available: {available}")
    defaults = PROVIDER_DEFAULTS[name]
    base_url = settings.llm_base_url or defaults["base_url"]
    model = settings.llm_model or defaults["model"]
    if not base_url or not model:
        raise ValueError(f"LLM_PROVIDER={name} needs LLM_BASE_URL and LLM_MODEL.")
    if not settings.llm_api_key:
        hint = defaults["key_env"] or "LLM_API_KEY"
        raise ValueError(f"LLM_PROVIDER={name} needs an API key: set LLM_API_KEY (or {hint}).")
    return OpenAICompatibleProvider(
        name, base_url, settings.llm_api_key, model, timeout=settings.llm_timeout, client=client
    )
