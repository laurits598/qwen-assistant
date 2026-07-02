"""CLI entry point.

Invocation styles (all equivalent):
    qwen health
    qwen --health
    qwen --profile health
    qwen run health
Plus utility subcommands: list, show, validate, doctor.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich.syntax import Syntax
from rich.table import Table

from . import __version__, collector, context, ollama_client, profiles, prompt, report, safety
from .config import config_dir, load_settings
from .report import console, err_console

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="AI-powered sysadmin assistant on top of Ollama.")

SUBCOMMANDS = {"run", "list", "show", "validate", "doctor"}


def _fail(message: str, code: int = 1) -> None:
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code)


def _map_args(profile: profiles.Profile, extra: List[str]) -> Dict[str, str]:
    """Map positional CLI extras onto the profile's declared args, in order."""
    if len(extra) > len(profile.args):
        _fail(f"profile {profile.name!r} takes at most {len(profile.args)} argument(s), "
              f"got {len(extra)}")
    values: Dict[str, str] = {}
    for i, spec in enumerate(profile.args):
        if i < len(extra):
            values[spec.name] = extra[i]
        elif spec.required:
            _fail(f"profile {profile.name!r} requires argument <{spec.name}>")
        else:
            values[spec.name] = spec.default
    return values


def _confirm_safety(profile: profiles.Profile, yes: bool) -> None:
    tier_name = safety.tier(profile.safety.read_only, profile.safety.requires_root)
    if tier_name == "read-only":
        return
    if tier_name == "privileged":
        if not safety.is_root():
            console.print("[yellow]This profile expects root; output may be "
                          "incomplete without sudo.[/yellow]")
        if yes:
            return
        if not typer.confirm(f"Profile {profile.name!r} requires elevated privileges. Proceed?"):
            raise typer.Exit(1)
        return
    # destructive: --yes never bypasses
    console.print(f"[bold red]Profile {profile.name!r} is NOT read-only. "
                  f"Its commands may modify this system.[/bold red]")
    typed = typer.prompt("Type the profile name to proceed")
    if typed != profile.name:
        _fail("confirmation did not match; aborting")


@app.command(name="run")
def run_cmd(
    profile_arg: Optional[str] = typer.Argument(None, metavar="[PROFILE]"),
    extra: Optional[List[str]] = typer.Argument(None, metavar="[ARGS]..."),
    profile_opt: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name."),
    ai: bool = typer.Option(True, "--ai/--no-ai", help="Run AI analysis."),
    raw: bool = typer.Option(False, "--raw", help="Show collected command output."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show commands without executing."),
    save: bool = typer.Option(False, "--save", help="Save report as Markdown."),
    out: Optional[Path] = typer.Option(None, "--out", help="Report path (implies --save)."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override Ollama model."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    yes: bool = typer.Option(False, "--yes", "-y",
                             help="Skip confirmation for privileged profiles."),
) -> None:
    """Run a profile: collect data, analyze with the local model, report."""
    name = profile_opt or profile_arg
    if not name:
        _fail("no profile given. Try: qwen list")

    settings = load_settings()
    model = model or settings.model

    try:
        profile = profiles.load(name)
    except profiles.ProfileError as exc:
        _fail(str(exc))

    arg_values = _map_args(profile, list(extra or []))
    resolved = collector.resolve(profile, arg_values)
    tier_name = safety.tier(profile.safety.read_only, profile.safety.requires_root)

    if dry_run:
        report.print_dry_run(resolved, tier_name)
        raise typer.Exit(0)

    try:
        collector.check_requirements(profile)
    except collector.MissingRequirement as exc:
        _fail(str(exc))

    _confirm_safety(profile, yes)

    def on_command(item: collector.ResolvedCommand) -> None:
        if verbose:
            console.print(f"[dim]$ {item.command}[/dim]")

    with console.status(f"[cyan]collecting: {profile.name}[/cyan]") if not verbose else _null():
        results = collector.collect(resolved, settings.command_timeout, on_command)

    if verbose:
        for result in results:
            state = "[red]failed[/red]" if result.failed else "[green]ok[/green]"
            console.print(f"[dim]{result.duration:5.2f}s {state:>7} $ {result.command}[/dim]")

    ctx = context.gather()

    if raw:
        report.print_context(ctx, profile, model)
        report.print_raw(results)

    analysis: Optional[str] = None
    exit_code = 0
    if ai:
        system_prompt, user_prompt = prompt.build(ctx, profile, results, settings)
        if verbose:
            console.print(f"[dim]prompt: {len(user_prompt)} chars "
                          f"(~{prompt.approx_tokens(user_prompt)} tokens), model {model}[/dim]")
        if not raw:
            report.print_context(ctx, profile, model)
        chunks: List[str] = []
        try:
            with console.status(f"[magenta]{model} is thinking…[/magenta]"):
                stream = ollama_client.stream_generate(
                    user_prompt, system_prompt, model, settings.ollama_host,
                    settings.temperature, settings.num_ctx,
                )
                first = next(stream, None)
            if first is not None:
                chunks.append(first)
                for chunk in stream:
                    chunks.append(chunk)
        except ollama_client.OllamaError as exc:
            if raw:
                _fail(f"AI analysis failed ({exc}); raw output shown above.", 3)
            _fail(f"AI analysis failed: {exc}\nHint: retry with --raw --no-ai "
                  f"to see the collected data, or run `qwen doctor`.", 3)
        analysis = "".join(chunks)
        report.render_analysis(analysis)
        exit_code = report.status_exit_code(analysis)

    if save or out:
        path = report.save_markdown(profile, ctx, results, analysis, model, out)
        console.print(f"\n[green]report saved:[/green] {path.resolve()}")

    raise typer.Exit(exit_code)


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@app.command(name="list")
def list_cmd() -> None:
    """List available profiles."""
    loaded, errors = profiles.load_all()
    table = Table(title="Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Category", style="dim")
    table.add_column("Safety")
    table.add_column("Description")
    for profile in sorted(loaded, key=lambda p: (p.category, p.name)):
        tier_name = safety.tier(profile.safety.read_only, profile.safety.requires_root)
        tier_style = {"read-only": "green", "privileged": "yellow",
                      "destructive": "red"}[tier_name]
        table.add_row(profile.name, profile.category,
                      f"[{tier_style}]{tier_name}[/{tier_style}]", profile.description)
    console.print(table)
    for error in errors:
        err_console.print(f"[red]invalid profile:[/red] {error}")


@app.command(name="show")
def show_cmd(name: str) -> None:
    """Print a profile's YAML."""
    try:
        profile = profiles.load(name)
    except profiles.ProfileError as exc:
        _fail(str(exc))
    console.print(f"[dim]{profile.source_path}[/dim]")
    text = Path(profile.source_path).read_text(encoding="utf-8")
    console.print(Syntax(text, "yaml", background_color="default"))


@app.command(name="validate")
def validate_cmd() -> None:
    """Schema-check every discoverable profile."""
    loaded, errors = profiles.load_all()
    for profile in loaded:
        console.print(f"[green]ok[/green]      {profile.name}  [dim]{profile.source_path}[/dim]")
    for error in errors:
        err_console.print(f"[red]invalid[/red]  {error}")
    raise typer.Exit(1 if errors else 0)


@app.command(name="doctor")
def doctor_cmd() -> None:
    """Check that Ollama, the model, and profiles are ready."""
    settings = load_settings()
    ok = True

    loaded, errors = profiles.load_all()
    console.print(f"profiles: [green]{len(loaded)} valid[/green]"
                  + (f", [red]{len(errors)} invalid[/red]" if errors else ""))
    ok = ok and not errors

    console.print(f"config dir: {config_dir()} "
                  + ("[green](exists)[/green]" if config_dir().is_dir()
                     else "[dim](not created yet — defaults in use)[/dim]"))

    if ollama_client.api_up(settings.ollama_host):
        console.print(f"ollama API: [green]reachable[/green] at {settings.ollama_host}")
        models = ollama_client.list_models(settings.ollama_host)
        if any(m == settings.model or m.startswith(settings.model) for m in models):
            console.print(f"model: [green]{settings.model} available[/green]")
        else:
            console.print(f"model: [red]{settings.model} not pulled[/red] "
                          f"— run: ollama pull {settings.model}")
            ok = False
    else:
        console.print(f"ollama API: [red]unreachable[/red] at {settings.ollama_host}")
        if ollama_client.cli_available():
            console.print("ollama CLI: [yellow]found — CLI fallback possible, "
                          "but start the server for streaming[/yellow]")
        else:
            console.print("ollama CLI: [red]not installed[/red]")
        ok = False

    raise typer.Exit(0 if ok else 1)


def main() -> None:
    """Entry point with profile-alias preprocessing.

    `qwen --health` / `qwen health` are rewritten to `qwen run health` so every
    profile gets a flag alias without registering per-profile commands.
    """
    args = sys.argv[1:]
    if args:
        first = args[0]
        if first in ("--help", "-h", "--version"):
            if first == "--version":
                print(f"qwen-assistant {__version__}")
                raise SystemExit(0)
        elif first.startswith("-"):
            alias = first.lstrip("-")
            if profiles.profile_exists(alias):
                args = ["run", alias] + args[1:]
            else:
                args = ["run"] + args  # e.g. qwen --profile health --raw
        elif first not in SUBCOMMANDS:
            args = ["run"] + args      # e.g. qwen health
    from typer.main import get_command
    get_command(app).main(args=args, prog_name="qwen")
