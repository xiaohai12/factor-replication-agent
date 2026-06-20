"""LLM client abstraction for the factor replication pipeline.

Supports three backends:
1. codex CLI (default) - uses `codex exec` subprocess, no API key needed
2. copilot CLI - uses the binary bundled with VS Code's GitHub Copilot Chat extension
   (~/Library/Application Support/Code/User/globalStorage/github.copilot-chat/copilotCli/copilot)
3. OpenRouter / OpenAI-compatible API - set OPENROUTER_API_KEY env var

Usage:
    from src.llm import create_llm_client

    # Codex CLI (default)
    client = create_llm_client()

    # Copilot CLI (uses your GitHub Copilot subscription)
    client = create_llm_client(provider="copilot")

    # OpenRouter
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
    Supports model selection via -m flag (e.g. gpt-5.5, gpt-5.4).
    """

    # Models available through Codex CLI
    SUPPORTED_MODELS = ["gpt-5.5", "gpt-5.4"]

    def __init__(self, model: str = "gpt-5.4"):
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
        # Always use configured default model — ignore caller's model
        # (callers may pass "gpt-4o" which isn't valid for all providers)
        model = self.default_model
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
            # Use --json for structured JSONL event output
            cmd = ["codex", "exec", "-s", "read-only", "--json"]
            if model != "default":
                cmd.extend(["-m", model])
            cmd.append("-")

            result = subprocess.run(
                cmd,
                input=full_prompt,
                capture_output=True,
                text=True,
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

        except Exception as e:
            raise RuntimeError(f"codex exec failed: {e}")


class CopilotCLIClient:
    """LLM client using the Copilot CLI binary bundled with VS Code's GitHub Copilot extension.

    Binary location (macOS):
      /Applications/Visual Studio Code.app/Contents/Resources/app/extensions/copilot/dist/cli.js
    Invoked via ELECTRON_RUN_AS_NODE with the VS Code helper binary.

    Two modes:
      - LLM mode (default): disables all tools for pure text completion
      - Agent mode: enables all tools for full coding agent capabilities

    Uses your GitHub Copilot subscription. Auth is handled by VS Code OAuth.
    Set COPILOT_CLI_JS env var to override the cli.js path.
    Set COPILOT_CLI_NODE env var to override the node binary path.
    """

    _DEFAULT_CLI_JS = (
        "/Applications/Visual Studio Code.app/Contents/Resources/app/extensions/copilot/dist/cli.js"
    )
    _DEFAULT_NODE_BIN = (
        "/Applications/Visual Studio Code.app/Contents/Frameworks/"
        "Code Helper (Plugin).app/Contents/MacOS/Code Helper (Plugin)"
    )

    def __init__(self, model: str = "claude-opus-4-6", agent_mode: bool = False):
        self.chat = _ChatNamespace(self)
        self.default_model = model
        self._agent_mode = agent_mode
        self._cli_js = os.environ.get("COPILOT_CLI_JS", self._DEFAULT_CLI_JS)
        self._node_bin = os.environ.get("COPILOT_CLI_NODE", self._DEFAULT_NODE_BIN)

    # Models available through Copilot CLI
    SUPPORTED_MODELS = ["claude-opus-4-6", "claude-sonnet-4-6", "gpt-5.4"]

    def _build_base_env(self) -> dict:
        env = os.environ.copy()
        env["ELECTRON_RUN_AS_NODE"] = "1"
        return env

    def _run_prompt(self, prompt: str, model: str) -> str:
        """Run in LLM mode: pure text completion with all tools disabled.
        
        Uses stdin ('-') to pass the prompt to avoid OS ARG_MAX limits
        with large paper texts.
        """
        cmd = [
            self._node_bin,
            self._cli_js,
            "-p", "-",
            "--output-format", "json",
            "--model", model,
            "--disallowed-tools", "Read", "Write", "Bash", "Edit",
            "--disable-slash-commands",
            "--no-session-persistence",
        ]

        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            env=self._build_base_env(),
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"copilot CLI exited with code {result.returncode}: {result.stderr[:500]}"
            )

        # Parse JSON output (single JSON object with "result" field)
        try:
            output = json.loads(result.stdout)
            return output.get("result", "")
        except json.JSONDecodeError:
            # Fallback: try parsing as NDJSON
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    if event.get("type") == "result":
                        return event.get("result", "")
                except json.JSONDecodeError:
                    continue
            return result.stdout.strip()

    def _run_agent_sync(self, prompt: str, model: str, work_dir: str | None = None) -> str:
        """Run in agent mode: full coding agent with tools enabled."""
        cmd = [
            self._node_bin,
            self._cli_js,
            "-p", "-",
            "--output-format", "json",
            "--model", model,
            "--dangerously-skip-permissions",
            "--no-session-persistence",
        ]
        if work_dir:
            cmd.extend(["--add-dir", work_dir])

        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            env=self._build_base_env(),
            cwd=work_dir,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"copilot CLI agent exited with code {result.returncode}: {result.stderr[:500]}"
            )

        # Parse JSON output
        try:
            output = json.loads(result.stdout)
            return output.get("result", "")
        except json.JSONDecodeError:
            # Fallback: try NDJSON
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    if event.get("type") == "result":
                        return event.get("result", "")
                except json.JSONDecodeError:
                    continue
            return result.stdout.strip()

    def _create(
        self,
        model: str | None = None,
        messages: list[dict] | None = None,
        temperature: float = 0.0,
        response_format: dict | None = None,
        **kwargs,
    ) -> ChatCompletion:
        # Always use configured default model — ignore caller's model
        # (callers may pass "gpt-4o" which isn't valid for this CLI)
        model = self.default_model
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
            if self._agent_mode:
                content = self._run_agent_sync(full_prompt, model, work_dir=kwargs.get("work_dir"))
            else:
                content = self._run_prompt(full_prompt, model)

            if not content:
                raise RuntimeError("copilot CLI returned empty response")

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

        except json.JSONDecodeError as e:
            raise RuntimeError(f"copilot CLI returned invalid JSON: {e}")
        except Exception as e:
            if "copilot CLI" in str(e):
                raise
            raise RuntimeError(f"copilot CLI failed: {e}")


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
) -> CodexCLIClient | CopilotCLIClient | OpenRouterClient:
    """Factory to create an LLM client.

    Args:
        provider: "codex" (default), "copilot", or "openrouter"
        api_key: API key for OpenRouter (or set OPENROUTER_API_KEY env var)
        model: Model name override

    Returns:
        Client with OpenAI-compatible .chat.completions.create() interface
    """
    if provider == "codex":
        return CodexCLIClient(model=model or "gpt-5.4")
    elif provider == "copilot":
        return CopilotCLIClient(model=model or "claude-opus-4-6")
    elif provider == "openrouter":
        return OpenRouterClient(api_key=api_key, model=model or "openai/gpt-4o")
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'codex', 'copilot', or 'openrouter'.")
