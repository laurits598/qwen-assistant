"""Prompt assembly: noise filtering, head+tail truncation, Jinja2 templating."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

from jinja2 import Environment, FileSystemLoader

from .collector import CommandResult
from .config import Settings
from .profiles import Profile

TEMPLATE_DIR = Path(__file__).parent / "templates"

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
BLANKS_RE = re.compile(r"\n{3,}")

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def clean(text: str) -> str:
    text = ANSI_RE.sub("", text)
    return BLANKS_RE.sub("\n\n", text)


def truncate(text: str, max_lines: int, max_bytes: int) -> str:
    """Keep head + tail; errors cluster at the end of logs, so the tail is bigger."""
    lines = text.splitlines()
    if len(lines) > max_lines:
        head_n = max(1, max_lines // 4)
        tail_n = max_lines - head_n
        omitted = len(lines) - head_n - tail_n
        lines = lines[:head_n] + [f"... [{omitted} lines omitted] ..."] + lines[-tail_n:]
        text = "\n".join(lines)
    if len(text.encode("utf-8", errors="replace")) > max_bytes:
        half = max_bytes // 2
        text = text[:half] + "\n... [truncated] ...\n" + text[-half:]
    return text


def prepare_results(results: List[CommandResult], settings: Settings) -> List[CommandResult]:
    prepared = []
    for result in results:
        limit = result.max_lines or settings.max_lines
        output = truncate(clean(result.output), limit, settings.max_bytes)
        prepared.append(CommandResult(
            command=result.command, label=result.label, output=output,
            returncode=result.returncode, duration=result.duration,
            failed=result.failed, error=result.error,
        ))
    return prepared


def build(context: Dict[str, str], profile: Profile,
          results: List[CommandResult], settings: Settings) -> Tuple[str, str]:
    """Return (system_prompt, user_prompt)."""
    system_prompt = _env.get_template("system.j2").render()
    user_prompt = _env.get_template("analysis.j2").render(
        profile=profile,
        results=prepare_results(results, settings),
        **context,
    )
    return system_prompt, user_prompt


def approx_tokens(text: str) -> int:
    return len(text) // 4
