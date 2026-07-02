"""Command execution: arg substitution, timeouts, output capture.

Commands without shell metacharacters run with shell=False (shlex.split);
pipelines and redirections run through the shell. Declared args are
shell-quoted before substitution so user input cannot inject commands.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .profiles import CommandSpec, Profile

SHELL_META = re.compile(r"[|&;<>`$]")
ARG_PATTERN = re.compile(r"\{(\w+)\}")


class MissingRequirement(Exception):
    """A binary listed under `requires:` is not on PATH."""


@dataclass
class ResolvedCommand:
    spec: CommandSpec
    command: str
    label: str


@dataclass
class CommandResult:
    command: str
    label: str
    output: str = ""
    returncode: int = 0
    duration: float = 0.0
    failed: bool = False
    error: str = ""
    max_lines: Optional[int] = None  # per-command cap from the profile


def check_requirements(profile: Profile) -> None:
    missing = [binary for binary in profile.requires if not shutil.which(binary)]
    if missing:
        raise MissingRequirement(
            f"profile {profile.name!r} requires: {', '.join(missing)} (not found on PATH)"
        )


def _substitute(text: str, args: Dict[str, str], quote: bool) -> str:
    """Replace {name} only for declared args; leave other braces (e.g. docker
    --format '{{.Names}}') untouched."""
    def repl(match: "re.Match[str]") -> str:
        name = match.group(1)
        if name in args:
            value = str(args[name])
            return shlex.quote(value) if quote else value
        return match.group(0)

    return ARG_PATTERN.sub(repl, text)


def resolve(profile: Profile, args: Dict[str, str]) -> List[ResolvedCommand]:
    resolved = []
    for spec in profile.commands:
        if spec.when and not args.get(spec.when):
            continue
        command = _substitute(spec.run, args, quote=True)
        label = _substitute(spec.label or spec.run, args, quote=False)
        resolved.append(ResolvedCommand(spec=spec, command=command, label=label))
    return resolved


def _execute(command: str, timeout: int) -> CommandResult:
    start = time.monotonic()
    try:
        if SHELL_META.search(command):
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout
            )
        else:
            proc = subprocess.run(
                shlex.split(command), capture_output=True, text=True, timeout=timeout
            )
        output = proc.stdout
        if proc.stderr.strip():
            output = f"{output}\n[stderr]\n{proc.stderr}" if output.strip() else proc.stderr
        return CommandResult(
            command=command,
            label="",
            output=output.strip("\n"),
            returncode=proc.returncode,
            duration=time.monotonic() - start,
            failed=proc.returncode != 0,
            error=f"exit code {proc.returncode}" if proc.returncode != 0 else "",
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            command=command, label="", duration=time.monotonic() - start,
            failed=True, error=f"timed out after {timeout}s",
        )
    except FileNotFoundError as exc:
        return CommandResult(
            command=command, label="", duration=time.monotonic() - start,
            failed=True, error=f"not found: {exc.filename}",
        )


def collect(
    resolved: List[ResolvedCommand],
    default_timeout: int,
    on_command: Optional[Callable[[ResolvedCommand], None]] = None,
) -> List[CommandResult]:
    results: List[CommandResult] = []
    for item in resolved:
        if on_command:
            on_command(item)
        result = _execute(item.command, item.spec.timeout or default_timeout)
        result.label = item.label
        result.max_lines = item.spec.max_lines
        results.append(result)
        if result.failed and item.spec.on_error == "abort":
            break
    return results
