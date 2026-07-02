# qwen — AI Sysadmin Assistant

Lightweight CLI wrapper around Ollama (`qwen2.5-coder:7b` by default). Collects system
state via YAML-defined command profiles, builds a structured prompt, and returns a
concise, actionable analysis. Read-only by default. See `ARCHITECTURE.md` for design.

## Install

```bash
pipx install .          # or: pip install .
ollama pull qwen2.5-coder:7b
qwen doctor             # verify setup
```

## Usage

```bash
qwen list                     # available profiles
qwen health                   # run a profile (positional)
qwen --con-stat               # alias form
qwen logs immich              # profile with argument
qwen disk --raw --no-ai       # plain data dump, no LLM
qwen health --dry-run         # show commands, execute nothing
qwen net --save               # write report as Markdown
qwen health --model llama3.1  # override model for this run
qwen show disk                # print a profile's YAML
qwen validate                 # schema-check all profiles
```

Exit codes: 0 = OK, 1 = WARNING, 2 = CRITICAL (parsed from the AI status line),
3 = AI analysis failed. Cron-friendly: `qwen health --save --yes`.

## Custom profiles

Drop a YAML file into `~/.config/qwen/profiles/` — same filename shadows a built-in.
No code changes needed:

```yaml
description: Tailscale status
category: network
safety:
  read_only: true
requires: [tailscale]
commands:
  - run: tailscale status
    label: Peers
  - run: tailscale netcheck
    label: Connectivity
    timeout: 30
prompt: |
  Analyze my Tailscale mesh. Flag offline peers, relayed (DERP) connections
  instead of direct ones, and DNS problems.
```

Profile arguments (`qwen logs immich`) are declared under `args:` and substituted
into commands as `{name}` — shell-quoted, so input can't inject commands.

Global settings in `~/.config/qwen/config.yaml`:

```yaml
model: qwen2.5-coder:7b
ollama_host: http://localhost:11434
temperature: 0.2
max_lines: 200
```

## Safety

Profiles declare `safety.read_only` and `safety.requires_root`. Privileged profiles
ask for confirmation (skippable with `--yes`); non-read-only profiles require typing
the profile name and are never bypassed by `--yes`. Validation rejects destructive
commands (rm -rf, mkfs, dd of=/dev/…, systemctl stop, docker prune, …) in profiles
claiming to be read-only. The tool never executes anything the model suggests.

## Development

```bash
pip install -e ".[dev]"   # or just: pip install -e . pytest
pytest
qwen validate
```
