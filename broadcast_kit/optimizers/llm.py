"""Lightweight LLM provider abstraction for optimizers.

Configure via env:

- BROADCAST_KIT_LLM_PROVIDER: openai | anthropic | ollama  (default: openai)
- BROADCAST_KIT_LLM_MODEL: model id  (defaults per provider)
- OPENAI_API_KEY / ANTHROPIC_API_KEY: auth
- OLLAMA_BASE_URL: defaults to http://localhost:11434

The provider returns a structured JSON object given a system + user prompt.
We use the simplest correct call per provider (no SDK lock-in beyond urllib).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import request as urllib_request

from .base import OptimizerError


DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "ollama": "llama3.3:70b",
}


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    api_key: str | None
    base_url: str | None
    temperature: float = 0.4
    max_tokens: int = 2000


def load_llm_config() -> LLMConfig:
    provider = os.getenv("BROADCAST_KIT_LLM_PROVIDER", "openai").strip().lower()
    if provider not in DEFAULT_MODELS:
        raise OptimizerError(
            f"unsupported BROADCAST_KIT_LLM_PROVIDER={provider}; expected one of {list(DEFAULT_MODELS)}"
        )
    model = os.getenv("BROADCAST_KIT_LLM_MODEL") or DEFAULT_MODELS[provider]
    api_key: str | None = None
    base_url: str | None = None
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
    elif provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    return LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=float(os.getenv("BROADCAST_KIT_LLM_TEMPERATURE", "0.4")),
        max_tokens=int(os.getenv("BROADCAST_KIT_LLM_MAX_TOKENS", "2000")),
    )


def call_llm_json(system: str, user: str, config: LLMConfig | None = None) -> dict[str, Any]:
    """Call the configured LLM and parse the response as JSON.

    Each provider call asks for a JSON-only response; we strip optional
    fenced code blocks and parse. Raises OptimizerError on transport or
    parse failure.
    """
    config = config or load_llm_config()
    if config.provider == "openai":
        raw = _call_openai(system, user, config)
    elif config.provider == "anthropic":
        raw = _call_anthropic(system, user, config)
    elif config.provider == "ollama":
        raw = _call_ollama(system, user, config)
    else:
        raise OptimizerError(f"unsupported provider: {config.provider}")
    return _parse_json(raw)


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int = 90) -> dict[str, Any]:
    req = urllib_request.Request(
        url,
        headers=headers,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise OptimizerError(f"LLM HTTP call failed: {exc}") from exc


def _call_openai(system: str, user: str, config: LLMConfig) -> str:
    if not config.api_key:
        raise OptimizerError("OPENAI_API_KEY is required for provider=openai")
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "response_format": {"type": "json_object"},
    }
    data = _post_json(f"{config.base_url}/chat/completions", headers, payload)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise OptimizerError(f"OpenAI response missing content: {data}") from exc


def _call_anthropic(system: str, user: str, config: LLMConfig) -> str:
    if not config.api_key:
        raise OptimizerError("ANTHROPIC_API_KEY is required for provider=anthropic")
    headers = {
        "x-api-key": config.api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model,
        "system": system + "\n\nReturn ONLY a JSON object. No prose. No fenced code block.",
        "messages": [{"role": "user", "content": user}],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    data = _post_json(f"{config.base_url}/messages", headers, payload)
    try:
        return data["content"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise OptimizerError(f"Anthropic response missing content: {data}") from exc


def _call_ollama(system: str, user: str, config: LLMConfig) -> str:
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system + "\n\nReturn ONLY a JSON object."},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": config.temperature,
            "num_predict": config.max_tokens,
        },
    }
    data = _post_json(f"{config.base_url}/api/chat", headers, payload)
    try:
        return data["message"]["content"]
    except KeyError as exc:
        raise OptimizerError(f"Ollama response missing content: {data}") from exc


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` fence
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OptimizerError(f"LLM did not return valid JSON: {exc}; raw={raw[:400]}") from exc
    if not isinstance(obj, dict):
        raise OptimizerError(f"LLM JSON root must be object; got {type(obj).__name__}")
    return obj
