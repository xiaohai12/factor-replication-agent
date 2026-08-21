"""LLM client abstraction for the factor replication pipeline.

Supports three backends:
1. codex CLI (default) - uses `codex exec` subprocess, no API key needed
2. copilot CLI - uses the binary bundled with VS Code's GitHub Copilot Chat extension
   (~/Library/Application Support/Code/User/globalStorage/github.copilot-chat/copilotCli/copilot)
3. OpenRouter / OpenAI-compatible API - set OPENROUTER_API_KEY env var

Usage:
    from src.infra.llm import create_llm_client

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
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    # `LLMClient` is a documentary alias for "any concrete LLM client in this
    # module" (CodexCLIClient / CopilotCLIClient / OpenRouterClient); they share
    # no common base, so annotate the back-references as Any.
    from typing import Any as LLMClient


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


def extract_json_object_text(text: str) -> str:
    """Extract the first complete top-level JSON object from mixed text output."""
    if not text:
        raise ValueError("empty response")

    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()

    if stripped.startswith("{") and stripped.endswith("}"):
        json.loads(stripped)
        return stripped

    start = stripped.find("{")
    if start == -1:
        preview = stripped[:300].replace("\n", " ")
        raise ValueError(f"no JSON object start found in response: {preview!r}")

    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(stripped)):
        ch = stripped[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[start:idx + 1]
                json.loads(candidate)
                return candidate

    preview = stripped[:300].replace("\n", " ")
    raise ValueError(f"no complete JSON object found in response: {preview!r}")


def _find_codex_bin() -> str:
    """Return the codex binary path, checking PATH then known install locations."""
    import shutil
    if shutil.which("codex"):
        return "codex"
    candidates = [
        os.path.expanduser("~/.vscode/extensions/openai.chatgpt-*/bin/macos-aarch64/codex"),
        os.path.expanduser("~/.vscode/extensions/openai.chatgpt-*/bin/macos-x64/codex"),
        os.path.expanduser("~/.vscode/extensions/openai.chatgpt-*/bin/linux-x64/codex"),
        os.path.expanduser("~/.codex/plugins/.plugin-appserver/codex"),
        "/usr/local/bin/codex",
    ]
    import glob
    for pattern in candidates:
        matches = glob.glob(pattern)
        if matches:
            return sorted(matches)[-1]  # pick latest version
    return "codex"  # fall back; will error at call time with a clear message


class CodexCLIClient:
    """LLM client using `codex exec` CLI subprocess.

    Wraps codex CLI to provide an OpenAI-compatible interface.
    Uses --json flag for structured JSONL output parsing.
    Supports model selection via -m flag (e.g. gpt-5.5, gpt-5.6-terra, gpt-5.6-sol).
    Set stream_callback to receive incremental agent_message text as it arrives.
    """

    SUPPORTED_MODELS = ["gpt-5.5", "gpt-5.6-terra", "gpt-5.6-sol"]

    def __init__(self, model: str = "gpt-5.6-terra"):
        self.chat = _ChatNamespace(self)
        self.default_model = model
        self._bin = _find_codex_bin()
        self.stream_callback: Optional[callable] = None

    @staticmethod
    def _pdf_to_text(pdf_bytes: bytes) -> str:
        """Extract text from PDF using pymupdf."""
        import pymupdf
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(pages)

    def _create(
        self,
        model: str | None = None,
        messages: list[dict] | None = None,
        temperature: float = 0.0,
        response_format: dict | None = None,
        pdf_bytes: bytes | None = None,
        **kwargs,
    ) -> ChatCompletion:
        model = self.default_model
        messages = messages or []

        prompt_parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                prompt_parts.append(f"[SYSTEM INSTRUCTIONS]\n{content}\n")
            elif role == "user":
                if pdf_bytes:
                    pdf_text = self._pdf_to_text(pdf_bytes)
                    prompt_parts.append(f"[PAPER TEXT (extracted from PDF)]\n{pdf_text}\n")
                    pdf_bytes = None  # only prepend once
                prompt_parts.append(f"[USER REQUEST]\n{content}\n")

        full_prompt = "\n".join(prompt_parts)

        if response_format and response_format.get("type") == "json_object":
            full_prompt += "\n\nIMPORTANT: Respond with ONLY valid JSON. No markdown, no explanation, just the JSON object."

        stderr_out = ""
        try:
            cmd = [self._bin, "exec", "-s", "read-only", "--json"]
            if model != "default":
                cmd.extend(["-m", model])
            cmd.append("-")

            content = ""
            with subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ) as proc:
                proc.stdin.write(full_prompt)
                proc.stdin.close()

                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        if event.get("type") == "item.completed":
                            item = event.get("item", {})
                            if item.get("type") == "agent_message":
                                content += item.get("text", "")
                                if self.stream_callback and content:
                                    self.stream_callback(content)
                    except json.JSONDecodeError:
                        continue

                proc.wait()
                stderr_out = proc.stderr.read() if proc.stderr else ""

        except Exception as e:
            raise RuntimeError(f"codex exec failed: {e}")

        if not content:
            raise RuntimeError(
                f"codex exec returned no agent message. stderr: {stderr_out[-2000:]}"
            )

        if response_format and response_format.get("type") == "json_object":
            content = extract_json_object_text(content)

        return ChatCompletion(
            choices=[Choice(message=Message(role="assistant", content=content))],
            model=model,
            usage=_estimate_tokens(full_prompt, content),
        )


class CopilotCLIClient:
    """LLM client using the official GitHub Copilot CLI (`@github/copilot` npm package).

    Binary location (macOS, installed via VS Code's Copilot Chat extension shim):
      ~/Library/Application Support/Code/User/globalStorage/github.copilot-chat/copilotCli/copilot
    This shim forwards to the real `copilot` binary (installed separately via
    `npm install -g @github/copilot`) and authenticates via GitHub OAuth --
    e.g. `gh auth login`, or COPILOT_GITHUB_TOKEN/GH_TOKEN/GITHUB_TOKEN env vars.

    NOTE: an EARLIER version of this class invoked
    `extensions/copilot/dist/cli.js` directly (the internal, vendored Anthropic
    "Claude Code" CLI) -- that binary requires its OWN separate Anthropic
    account login (`claude auth login`), unrelated to your GitHub Copilot
    subscription, and can hang indefinitely if that Anthropic sign-in is
    blocked by an org Conditional Access policy. This class now uses the real
    GitHub-authenticated `copilot` CLI instead, which reuses your existing
    GitHub Copilot entitlement.

    Two modes:
      - LLM mode (default): disables all tools for pure text completion
      - Agent mode: enables all tools for full coding agent capabilities

    Set COPILOT_CLI_BIN env var to override the binary path.
    """

    _DEFAULT_BIN = os.path.expanduser(
        "~/Library/Application Support/Code/User/globalStorage/"
        "github.copilot-chat/copilotCli/copilot"
    )

    SUPPORTED_MODELS = ["claude-sonnet-5", "claude-opus-5", "gpt-5.6-terra", "gpt-5.6-sol"]

    def __init__(self, model: str = "claude-opus-5", agent_mode: bool = False):
        self.chat = _ChatNamespace(self)
        self.default_model = model
        self._agent_mode = agent_mode
        self._bin = os.environ.get("COPILOT_CLI_BIN", self._DEFAULT_BIN)
        self.stream_callback: Optional[callable] = None

    def _run_with_popen(self, cmd: list, work_dir: str | None = None) -> str:
        """Run a copilot CLI command via Popen, parsing JSONL events from stdout.

        Streams the growing assistant message text to stream_callback as
        `assistant.message_delta` events arrive, and returns the final
        `assistant.message` content once the run completes.
        """
        raw_lines: list[str] = []
        content = ""
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=work_dir,
        ) as proc:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                raw_lines.append(line)
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "assistant.message":
                    content = event.get("data", {}).get("content", "") or content
                    if self.stream_callback and content:
                        self.stream_callback(content)

            proc.wait()
            stderr_out = proc.stderr.read() if proc.stderr else ""
            if proc.returncode != 0 and not content:
                # Not truncated to a tiny prefix -- a benign Node ESM/CommonJS
                # interop warning is often the FIRST line of stderr, and a
                # short truncation used to hide the actual failure reason
                # that follows it, making failures undiagnosable from the UI.
                raise RuntimeError(
                    f"copilot CLI exited with code {proc.returncode}: {stderr_out[-2000:]}"
                )

        return content

    def _run_prompt(self, prompt: str, model: str) -> str:
        """Run in LLM mode: pure text completion with all tools disabled."""
        cmd = [
            self._bin,
            "-p", prompt,
            "--model", model,
            "--output-format", "json",
            "--log-level", "none",
            "--no-color",
            "--available-tools=",
        ]
        return self._run_with_popen(cmd)

    def _run_agent_sync(self, prompt: str, model: str, work_dir: str | None = None) -> str:
        """Run in agent mode: full coding agent with tools enabled."""
        cmd = [
            self._bin,
            "-p", prompt,
            "--model", model,
            "--output-format", "json",
            "--log-level", "none",
            "--no-color",
            "--allow-all-tools",
        ]
        if work_dir:
            cmd.extend(["--add-dir", work_dir])
        return self._run_with_popen(cmd, work_dir=work_dir)

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

            if response_format and response_format.get("type") == "json_object":
                content = extract_json_object_text(content)

            return ChatCompletion(
                choices=[Choice(message=Message(role="assistant", content=content))],
                model=model,
                usage=_estimate_tokens(full_prompt, content),
            )

        except json.JSONDecodeError as e:
            raise RuntimeError(f"copilot CLI returned invalid JSON: {e}")
        except Exception as e:
            if "copilot CLI" in str(e):
                raise
            raise RuntimeError(f"copilot CLI failed: {e}")


def _find_claude_bin() -> str:
    """Return the claude binary path, checking PATH then known install locations."""
    import shutil
    if shutil.which("claude"):
        return "claude"
    env_override = os.environ.get("CLAUDE_CODE_BIN")
    if env_override:
        return env_override
    import glob
    candidates = [
        os.path.expanduser("~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"),
        os.path.expanduser("~/Library/Application Support/Claude/claude-code-vm/*/claude"),
        "/usr/local/bin/claude",
    ]
    for pattern in candidates:
        matches = glob.glob(pattern)
        if matches:
            return sorted(matches)[-1]
    return "claude"


class ClaudeCodeCLIClient:
    """LLM client using the `claude` CLI (Claude Code).

    Streams output via --output-format stream-json so callers can show progress.
    Set stream_callback to receive incremental text as it arrives.

    Set CLAUDE_CODE_BIN env var to override the binary path (default: auto-detected).
    """

    SUPPORTED_MODELS = ["claude-sonnet-5", "claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"]

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.chat = _ChatNamespace(self)
        self.default_model = model
        self._bin = _find_claude_bin()
        self.stream_callback: Optional[callable] = None  # called with (partial_text: str)

    def _create(
        self,
        model: str | None = None,
        messages: list[dict] | None = None,
        temperature: float = 0.0,
        response_format: dict | None = None,
        pdf_bytes: bytes | None = None,
        **_kwargs,
    ) -> ChatCompletion:
        model = self.default_model
        messages = messages or []

        if response_format and response_format.get("type") == "json_object":
            json_instruction = "\n\nIMPORTANT: Respond with ONLY valid JSON. No markdown, no explanation, just the JSON object."
        else:
            json_instruction = ""

        if pdf_bytes:
            return self._create_with_pdf(model, messages, pdf_bytes, json_instruction, response_format)

        # Text-only path
        prompt_parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                prompt_parts.append(f"[SYSTEM INSTRUCTIONS]\n{content}\n")
            elif role == "user":
                prompt_parts.append(f"[USER REQUEST]\n{content}\n")
        full_prompt = "\n".join(prompt_parts) + json_instruction

        return self._run_stream_json(
            cmd=[self._bin, "--model", model, "--output-format", "stream-json",
                 "--no-session-persistence", "-p", "-"],
            stdin_text=full_prompt,
            response_format=response_format,
        )

    def _create_with_pdf(
        self,
        model: str,
        messages: list[dict],
        pdf_bytes: bytes,
        json_instruction: str,
        response_format,
    ) -> ChatCompletion:
        """Send PDF as a base64 document block via --input-format stream-json."""
        import base64

        system_text = ""
        user_text = ""
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            elif msg["role"] == "user":
                user_text = msg["content"]

        user_text += json_instruction

        b64 = base64.b64encode(pdf_bytes).decode()
        stdin_msg = json.dumps({
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                    {"type": "text", "text": user_text},
                ],
            },
        })

        cmd = [
            self._bin, "--model", model,
            "--output-format", "stream-json",
            "--input-format", "stream-json",
            "--verbose",
            "--no-session-persistence",
            "-p", "-",
        ]
        if system_text:
            cmd += ["--system-prompt", system_text]

        return self._run_stream_json(cmd=cmd, stdin_text=stdin_msg, response_format=response_format)

    def _run_stream_json(self, cmd: list, stdin_text: str, response_format) -> ChatCompletion:
        """Run claude CLI, read stream-json output, return ChatCompletion."""
        try:
            content = ""
            with subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ) as proc:
                proc.stdin.write(stdin_text)
                proc.stdin.close()

                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        etype = event.get("type")
                        if etype == "assistant":
                            for block in event.get("message", {}).get("content", []):
                                if block.get("type") == "text":
                                    content = block.get("text", "")
                                    if self.stream_callback and content:
                                        self.stream_callback(content)
                        elif etype == "result":
                            final = event.get("result", "")
                            if final:
                                content = final
                    except json.JSONDecodeError:
                        continue

                proc.wait()
                stderr_out = proc.stderr.read() if proc.stderr else ""
                if proc.returncode != 0 and not content:
                    # See CopilotCLIClient's identical fix: don't truncate to
                    # a tiny prefix that may only capture a benign warning.
                    raise RuntimeError(
                        f"claude CLI exited with code {proc.returncode}: {stderr_out[-2000:]}"
                    )

            if not content:
                raise RuntimeError("claude CLI returned empty response")

            if response_format and response_format.get("type") == "json_object":
                content = extract_json_object_text(content)

            return ChatCompletion(
                choices=[Choice(message=Message(role="assistant", content=content))],
                model=self.default_model,
                usage=_estimate_tokens(stdin_text, content),
            )

        except json.JSONDecodeError as e:
            raise RuntimeError(f"claude CLI returned invalid JSON: {e}")
        except Exception as e:
            if "claude CLI" in str(e):
                raise
            raise RuntimeError(f"claude CLI failed: {e}")


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


def extract_usage(response) -> dict:
    """Extract token usage from any response object (our wrapper or real OpenAI)."""
    usage = getattr(response, "usage", None)
    if not usage:
        return {}
    if isinstance(usage, dict):
        return usage
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
        "completion_tokens": getattr(usage, "completion_tokens", 0),
        "total_tokens": getattr(usage, "total_tokens", 0),
    }


def _estimate_tokens(prompt_text: str, response_text: str) -> dict:
    """Rough token estimate for CLI providers: ~4 chars per token."""
    pt = max(1, len(prompt_text) // 4)
    ct = max(1, len(response_text) // 4)
    return {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct, "estimated": True}


def create_llm_client(
    provider: str = "codex",
    api_key: str | None = None,
    model: str | None = None,
) -> CodexCLIClient | CopilotCLIClient | ClaudeCodeCLIClient | OpenRouterClient:
    """Factory to create an LLM client.

    Args:
        provider: "codex", "copilot", "claude" (Claude Code CLI), or "openrouter"
        api_key: API key for OpenRouter (or set OPENROUTER_API_KEY env var)
        model: Model name override

    Returns:
        Client with OpenAI-compatible .chat.completions.create() interface
    """
    if provider == "codex":
        return CodexCLIClient(model=model or "gpt-5.6-terra")
    elif provider == "copilot":
        return CopilotCLIClient(model=model or "claude-opus-5")
    elif provider == "claude":
        return ClaudeCodeCLIClient(model=model or "claude-sonnet-4-6")
    elif provider == "openrouter":
        return OpenRouterClient(api_key=api_key, model=model or "openai/gpt-4o")
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'codex', 'copilot', 'claude', or 'openrouter'.")
