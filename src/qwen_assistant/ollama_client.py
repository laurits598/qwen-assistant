"""Thin Ollama client: streaming HTTP API first, `ollama run` CLI as fallback."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Iterator, List, Optional

import httpx


class OllamaError(Exception):
    pass


def api_up(host: str) -> bool:
    try:
        return httpx.get(f"{host}/api/tags", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


def list_models(host: str) -> List[str]:
    try:
        data = httpx.get(f"{host}/api/tags", timeout=5).json()
        return [m["name"] for m in data.get("models", [])]
    except (httpx.HTTPError, KeyError, ValueError):
        return []


def cli_available() -> bool:
    return shutil.which("ollama") is not None


def stream_generate(
    prompt: str,
    system: str,
    model: str,
    host: str,
    temperature: float = 0.2,
    num_ctx: int = 16384,
) -> Iterator[str]:
    """Yield response chunks. Falls back to the ollama CLI if the API is down."""
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": True,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    try:
        with httpx.stream(
            "POST", f"{host}/api/generate", json=payload,
            timeout=httpx.Timeout(600.0, connect=5.0),
        ) as response:
            if response.status_code != 200:
                body = response.read().decode(errors="replace")
                raise OllamaError(f"Ollama API returned {response.status_code}: {body[:300]}")
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get("error"):
                    raise OllamaError(data["error"])
                chunk = data.get("response")
                if chunk:
                    yield chunk
                if data.get("done"):
                    return
    except httpx.ConnectError:
        yield from _cli_fallback(prompt, system, model)


def _cli_fallback(prompt: str, system: str, model: str) -> Iterator[str]:
    if not cli_available():
        raise OllamaError(
            "Ollama API is unreachable and the `ollama` CLI is not installed. "
            "Start the server (`ollama serve`) or install Ollama."
        )
    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    proc = subprocess.Popen(
        ["ollama", "run", model],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = proc.communicate(input=full_prompt, timeout=600)
    if proc.returncode != 0:
        raise OllamaError(f"ollama CLI failed: {stderr.strip()[:300]}")
    yield stdout
