"""Rendering: terminal output via rich, Markdown report saving, exit codes."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .collector import CommandResult, ResolvedCommand
from .profiles import Profile

console = Console()
err_console = Console(stderr=True)

STATUS_RE = re.compile(r"Status:\s*\**\s*(OK|WARNING|CRITICAL)", re.IGNORECASE)
EXIT_CODES = {"OK": 0, "WARNING": 1, "CRITICAL": 2}


def status_exit_code(analysis: str) -> int:
    match = STATUS_RE.search(analysis)
    return EXIT_CODES.get(match.group(1).upper(), 0) if match else 0


def print_context(context: Dict[str, str], profile: Profile, model: str) -> None:
    console.print(Panel(
        f"[bold]{context['hostname']}[/bold] · {context['os_release']} · "
        f"kernel {context['kernel']} · up {context['uptime']}\n"
        f"profile [cyan]{profile.name}[/cyan] · model [magenta]{model}[/magenta] · "
        f"{context['timestamp']}",
        title="qwen", border_style="dim",
    ))


def print_dry_run(resolved: List[ResolvedCommand], tier_name: str) -> None:
    table = Table(title=f"Dry run — safety tier: {tier_name}", show_lines=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Label")
    table.add_column("Command", style="cyan")
    table.add_column("Timeout", style="dim")
    for i, item in enumerate(resolved, 1):
        table.add_row(str(i), item.label, item.command,
                      f"{item.spec.timeout or '-'}s" if item.spec.timeout else "default")
    console.print(table)


def print_raw(results: List[CommandResult]) -> None:
    for result in results:
        style = "red" if result.failed else "green"
        title = f"$ {result.command}" + (f"  [{result.error}]" if result.failed else "")
        console.print(Panel(result.output or "(no output)", title=title,
                            border_style=style, title_align="left"))


def render_analysis(analysis: str) -> None:
    console.print()
    console.print(Markdown(analysis))


def save_markdown(
    profile: Profile,
    context: Dict[str, str],
    results: List[CommandResult],
    analysis: Optional[str],
    model: str,
    path: Optional[Path] = None,
) -> Path:
    if path is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = Path(f"qwen-{profile.name}-{timestamp}.md")
    lines = [
        f"# qwen report — {profile.name}",
        "",
        f"- **Host:** {context['hostname']}",
        f"- **OS:** {context['os_release']} (kernel {context['kernel']})",
        f"- **Uptime:** {context['uptime']}",
        f"- **Time:** {context['timestamp']}",
        f"- **Model:** {model}",
        "",
    ]
    if analysis:
        lines += ["## AI Analysis", "", analysis.strip(), ""]
    lines += ["## Collected Data", ""]
    for result in results:
        status = f" — FAILED: {result.error}" if result.failed else ""
        lines += [
            "<details>",
            f"<summary><code>{result.command}</code>{status}</summary>",
            "",
            "```text",
            result.output or "(no output)",
            "```",
            "",
            "</details>",
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
