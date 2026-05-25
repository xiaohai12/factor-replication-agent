"""LLM client abstraction for the factor replication pipeline.

Supports two backends:
1. codex CLI (default) - uses `codex exec` subprocess, no API key needed
2. OpenRouter / OpenAI-compatible API - set OPENROUTER_API_KEY env var

Usage:
    from src.llm import create_llm_client

    # Codex CLI (default)
    client = create_llm_client()

    # OpenRouter (later)
    client = create_llm_client(provider="openrouter", api_key="sk-...")

    # Use like OpenAI client
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[...],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Message:
    role: str
    content: str


@dataclass
class Choice:
    message: Message
    index: int = 0
    finish_reason: str = "stop"


@dataclass
class ChatCompletion:
    choices: list[Choice]
    model: str = ""
    usage: dict = field(default_factory=dict)


class _CompletionsNamespace:
    """Mimics openai.chat.completions interface."""

    def __init__(self, client: "LLMClient"):
        self._client = client

    def create(self, **kwargs) -> ChatCompletion:
        return self._client._create(**kwargs)


class _ChatNamespace:
    """Mimics openai.chat interface."""

    def __init__(self, client: "LLMClient"):
        self.completions = _CompletionsNamespace(client)


class CodexCLIClient:
    """LLM client using `codex exec` CLI subprocess.

    Wraps codex CLI to provide an OpenAI-compatible interface.
    Uses --json flag for structured JSONL output parsing.
    Note: Uses default model (no -m flag) since ChatGPT accounts
    only support the default model.
    """

    def __init__(self, model: str = "default"):
        self.chat = _ChatNamespace(self)
        self.default_model = model

    def _create(
        self,
        model: str | None = None,
        messages: list[dict] | None = None,
        temperature: float = 0.0,
        response_format: dict | None = None,
        **kwargs,
    ) -> ChatCompletion:
        model = model or self.default_model
        messages = messages or []

        # Build prompt from messages
        prompt_parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                prompt_parts.append(f"[SYSTEM INSTRUCTIONS]\n{content}\n")
            elif role == "user":
                prompt_parts.append(f"[USER REQUEST]\n{content}\n")

        full_prompt = "\n".join(prompt_parts)

        # If JSON mode requested, add explicit instruction
        if response_format and response_format.get("type") == "json_object":
            full_prompt += "\n\nIMPORTANT: Respond with ONLY valid JSON. No markdown, no explanation, just the JSON object."

        try:
            # Use --json for structured JSONL event output, no -m (use default model)
            cmd = ["codex", "exec", "-s", "read-only", "--json", "-"]

            result = subprocess.run(
                cmd,
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=120,
            )

            # Parse JSONL events from stdout to extract agent messages
            content = ""
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    if event.get("type") == "item.completed":
                        item = event.get("item", {})
                        if item.get("type") == "agent_message":
                            content += item.get("text", "")
                except json.JSONDecodeError:
                    continue

            if not content:
                raise RuntimeError(
                    f"codex exec returned no agent message. stdout: {result.stdout[:300]}"
                )

            # Clean up markdown code fences if present
            if content.startswith("```"):
                lines = content.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                content = "\n".join(lines)

            # Validate JSON if json_object mode
            if response_format and response_format.get("type") == "json_object":
                json.loads(content)  # Raises if invalid

            return ChatCompletion(
                choices=[Choice(message=Message(role="assistant", content=content))],
                model=model,
            )

        except subprocess.TimeoutExpired:
            raise RuntimeError("codex exec timed out after 120s")


class OpenRouterClient:
    """LLM client using OpenRouter API (OpenAI-compatible).

    Set OPENROUTER_API_KEY environment variable or pass api_key.
    """

    def __init__(self, api_key: str | None = None, model: str = "openai/gpt-4o"):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("pip install openai  # required for OpenRouter client")

        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "OpenRouter API key required. Set OPENROUTER_API_KEY env var or pass api_key="
            )

        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self._api_key,
        )
        self.chat = self._client.chat
        self.default_model = model


def create_llm_client(
    provider: str = "codex",
    api_key: str | None = None,
    model: str | None = None,
) -> CodexCLIClient | OpenRouterClient:
    """Factory to create an LLM client.

    Args:
        provider: "codex" (default) or "openrouter"
        api_key: API key for OpenRouter (or set OPENROUTER_API_KEY env var)
        model: Model name override

    Returns:
        Client with OpenAI-compatible .chat.completions.create() interface
    """
    if provider == "codex":
        return CodexCLIClient(model=model or "default")
    elif provider == "openrouter":
        return OpenRouterClient(api_key=api_key, model=model or "openai/gpt-4o")
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'codex' or 'openrouter'.")
