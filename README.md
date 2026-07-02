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

# Architecture — AI Sysadmin Assistant for Linux

A lightweight CLI wrapper around Ollama (`qwen2.5-coder:7b` by default) that collects system state via configurable command profiles, builds a structured prompt, and returns a concise, actionable analysis. It never replaces Linux tools — it reads their output and reasons about it.

---

## 1. Core Design Principles

1. **Profiles are data, not code.** Every capability is a YAML file. Adding `--gpu` means adding `gpu.yaml` — zero application changes.
2. **Read-only by default.** The tool observes; it never mutates unless a profile is explicitly marked and the user explicitly confirms.
3. **Pipeline, not framework.** One linear flow: `load profile → collect → build prompt → infer → render`. Each stage is a small module with one job, swappable later (SSH collector, MCP renderer, etc.).
4. **Degrade gracefully.** A failed command becomes context ("command X failed: permission denied"), not a crash. The LLM often finds failures informative.
5. **Raw output is always recoverable.** AI analysis is a layer on top of collected data, never a replacement for it.

---

## 2. Directory Layout

```
qwen-assistant/
├── pyproject.toml              # packaging; installs `qwen` entry point
├── README.md
├── src/
│   └── qwen_assistant/
│       ├── __init__.py
│       ├── cli.py              # Typer app: arg parsing, dispatch only
│       ├── config.py           # global settings (model, ollama URL, paths)
│       ├── profiles.py         # discover / load / validate YAML profiles
│       ├── collector.py        # run commands, capture output, timeouts
│       ├── context.py          # gather host facts (hostname, OS, kernel…)
│       ├── prompt.py           # assemble structured prompt from template
│       ├── ollama_client.py    # thin HTTP client for /api/generate (+ CLI fallback)
│       ├── report.py           # render to terminal (rich) / markdown / save
│       ├── safety.py           # read-only enforcement, confirmation gates
│       └── profiles/           # built-in profiles shipped with the package
│           ├── con-stat.yaml
│           ├── disk.yaml
│           ├── fs.yaml
│           ├── net.yaml
│           ├── health.yaml
│           ├── logs.yaml
│           ├── services.yaml
│           └── security.yaml
├── templates/
│   ├── system.j2               # system prompt (persona + output contract)
│   └── analysis.j2             # user prompt (context + outputs + instructions)
└── tests/
    ├── test_profiles.py        # schema validation of every shipped profile
    ├── test_collector.py
    └── test_prompt.py
```

**User-level config** (survives upgrades, overrides built-ins by name):

```
~/.config/qwen/
├── config.yaml                 # model, ollama host, defaults
└── profiles/                   # user profiles; same schema as built-ins
    ├── proxmox.yaml
    └── tailscale.yaml
```

Profile resolution order: `~/.config/qwen/profiles/` → packaged `profiles/`. First match wins, so users can shadow built-ins.

---

## 3. CLI Interface

Built with **Typer**. Two invocation styles, same code path:

```bash
qwen health                      # canonical: profile as positional arg
qwen --profile health            # explicit form
qwen --health                    # convenience alias, auto-generated per profile
qwen logs immich                 # profile + argument (substituted into commands)
```

Options:

| Flag | Behavior |
|---|---|
| `--profile <name>` | Select profile (or use positional) |
| `--ai / --no-ai` | AI analysis on/off (default: on) |
| `--raw` | Print collected command output verbatim before/instead of analysis |
| `--dry-run` | Show resolved commands, execute nothing |
| `--save [path]` | Write report as Markdown (default: `./qwen-<profile>-<ts>.md`) |
| `--model <name>` | Override model for this run (default `qwen2.5-coder:7b`) |
| `--verbose` | Show commands as they run, timings, prompt size, token stats |
| `--yes` | Skip confirmation for privileged profiles (never for destructive) |

Utility subcommands:

```bash
qwen list                        # table of available profiles + descriptions
qwen show <profile>              # print profile YAML (resolved path, commands)
qwen validate                    # schema-check all profiles
qwen doctor                      # check ollama reachable, model pulled, deps present
```

Flag combinations compose naturally: `qwen disk --raw --no-ai` is a plain data dump; `qwen health --save --verbose` is a saved, narrated health report.

---

## 4. YAML Profile Schema

```yaml
# ~/.config/qwen/profiles/con-stat.yaml
name: con-stat                    # optional; defaults to filename
description: Docker container overview
category: docker                  # for `qwen list` grouping

safety:
  read_only: true                 # false ⇒ warning banner + confirmation
  requires_root: false            # true ⇒ check euid / prepend sudo, confirm

requires:                         # skip-with-message if binary missing
  - docker

args:                             # optional positional args (e.g. `qwen logs immich`)
  - name: container
    required: false
    default: ""

commands:
  - run: docker ps --format json
    label: Running containers    # heading used in the prompt
    timeout: 10                   # seconds, default 15
    on_error: continue            # continue (default) | abort
  - run: docker stats --no-stream
    label: Live resource usage
  - run: docker system df
    label: Disk usage
  - run: docker logs --tail 50 {container}   # {arg} substitution
    when: container               # only runs if arg provided
    label: Recent logs for {container}

prompt: |
  Analyze my Docker environment.
  Identify unhealthy containers, restart loops, high memory usage,
  exposed ports, unused images, and optimization opportunities.

focus:                            # optional; appended as priority list
  - restart loops
  - memory pressure
  - publicly exposed ports
```

Schema notes:

- **Validation** via a small Pydantic model. `qwen validate` and CI run it against every profile; a malformed profile fails fast with a line-level error, not at runtime.
- **`{placeholders}`** are substituted only from declared `args` — never from arbitrary user input — and shell-quoted (`shlex.quote`) to prevent injection.
- **`safety` is mandatory.** A profile without a `safety` block fails validation. This forces authors to think about it.
- **`on_error: continue`** is the default: partial data + an error note beats no report.

---

## 5. Safety Model

Three tiers, enforced in `safety.py` before anything executes:

1. **read-only** (`read_only: true`, `requires_root: false`) — runs immediately. This is the default and covers ~all shipped profiles.
2. **privileged** (`requires_root: true`) — prints the command list and asks `Proceed? [y/N]` unless `--yes`.
3. **destructive** (`read_only: false`) — prints a red banner, requires typing the profile name to confirm. `--yes` does **not** bypass this. Not used by any shipped profile; exists so user-authored cleanup profiles have a guarded path.

Additional guards:

- A **denylist regex** (`rm -rf`, `mkfs`, `dd of=/dev/`, `> /dev/sd`, `systemctl stop`, etc.) rejects commands in profiles claiming `read_only: true` — catching mislabeled profiles at validation time.
- Commands run with `shell=False` where possible; pipelines are allowed but flagged in `--verbose`.
- Per-command **timeout** and a global run timeout prevent hangs (e.g., `journalctl` without `-n`).
- The LLM's *recommendations* are text only. The tool never executes model output. (Interactive "apply fix?" mode is future work and will reuse the destructive tier.)

---

## 6. Prompt-Building Strategy

Two-part prompt, rendered from Jinja2 templates so tuning requires no code changes.

**System prompt** (`system.j2`) — stable persona and output contract:

```
You are a senior Linux sysadmin reviewing diagnostic output from a homelab
server. Be concise and specific. Never invent data not present in the output.

Respond in this structure:
## Status: <OK | WARNING | CRITICAL>
## Key Findings        (most severe first: errors, warnings, bottlenecks,
                        security issues, misconfigurations)
## Recommendations     (numbered, each with the exact command to investigate
                        or fix; mark destructive commands with ⚠)
## Cleanup Opportunities (only if any)

If everything is healthy, say so in two sentences. Do not pad.
```

**User prompt** (`analysis.j2`) — per-run context and data:

````
# Context
Host: {{ hostname }} | OS: {{ os_release }} | Kernel: {{ kernel }}
Time: {{ timestamp }} | Profile: {{ profile.name }}

# Collected data
{% for r in results %}
## {{ r.label }}  (`{{ r.command }}`{% if r.failed %} — FAILED: {{ r.error }}{% endif %})
```text
{{ r.output }}
```
{% endfor %}

# Task
{{ profile.prompt }}
{% if profile.focus %}Prioritize: {{ profile.focus | join(", ") }}{% endif %}
````

**Context-window management** (qwen2.5-coder:7b ⇒ keep prompts well under ~24k tokens):

- Per-command output cap (default 200 lines / 8 KB, configurable per command via `max_lines`). Truncation keeps **head + tail** ("first 50 / last 150") since errors cluster at the end of logs.
- Noise filters strip ANSI codes and collapse repeated blank lines before templating.
- `--verbose` reports the final prompt size so users can tune profiles.

**Determinism:** requests set `temperature: 0.2` — analysis should be stable, not creative.

---

## 7. Execution Flow

```
qwen con-stat --save
   │
   ├─ cli.py        parse args, resolve profile name
   ├─ profiles.py   load + validate YAML (user dir, then built-ins)
   ├─ safety.py     tier check → maybe confirm
   ├─ context.py    hostname, OS, kernel, uptime, timestamp
   ├─ collector.py  run each command (timeout, capture stdout+stderr+rc)
   │                  --dry-run stops here and prints the command list
   │                  --raw prints outputs here
   ├─ prompt.py     truncate, filter, render templates
   ├─ ollama_client POST /api/generate (stream); fallback: `ollama run` CLI
   │                  --no-ai stops before this
   └─ report.py     stream to terminal via rich; --save writes Markdown
                    (report = context header + findings + collapsed raw data)
```

Ollama integration detail: prefer the **HTTP API** (`http://localhost:11434/api/generate`) with streaming — it gives token-by-token terminal output, proper timeouts, and model options (`temperature`, `num_ctx`). Shell out to `ollama run` only as a fallback when the API is unreachable but the binary exists.

---

## 8. Implementation Plan

**Phase 1 — Walking skeleton (a weekend)**
`cli.py` + `profiles.py` + `collector.py` + `ollama_client.py` with one profile (`health.yaml`), plain-string prompt, plain-text output. Prove the loop: collect → prompt → answer.

**Phase 2 — Make it real**
Pydantic schema + `qwen validate`; safety tiers + denylist; Jinja2 templates; truncation/noise filtering; `--raw`, `--dry-run`, `--save`, `--model`, `--verbose`; rich terminal rendering; `qwen list/show/doctor`.

**Phase 3 — Profile library**
Ship disk, fs, net, services, logs (with `args`), con-stat, security, hardware. Each profile PR must pass `qwen validate` + a smoke test that runs it with `--dry-run`.

**Phase 4 — Quality**
Unit tests with recorded command fixtures (no docker needed in CI); prompt-size regression test; `pipx` install path; man page / `--help` polish.

**Extension seams (built in from Phase 1, implemented later):**

| Future feature | Seam already in place |
|---|---|
| Remote servers over SSH | `collector.py` behind a `Collector` interface; add `SSHCollector` (`--host`), same profile YAML |
| MCP tools | Pipeline stages are functions over typed dataclasses (`ProfileRun`, `CommandResult`) — trivially wrapped as MCP tools |
| Scheduled reports | `qwen health --save --no-color` is already cron-safe; add exit codes by status (0=OK, 1=WARN, 2=CRIT) |
| Historical comparison | `--save` writes to `~/.local/share/qwen/history/<profile>/<ts>.md` + JSON sidecar; later `qwen diff` |
| Plugins | Profile discovery is directory-scanning; add entry-point discovery for Python plugins providing collectors/renderers |
| RAG / knowledge base | `prompt.py` gets an optional `extra_context` slot; index `~/.config/qwen/kb/` with embeddings later |
| HTML reports | `report.py` renders from a structured `Report` object; add an HTML renderer |
| Interactive shell | The pipeline is a function; a REPL loops over it keeping conversation state in Ollama's `context` field |

---

## 9. Dependencies

Deliberately minimal: `typer`, `pydantic`, `pyyaml`, `jinja2`, `httpx`, `rich`. All pure-Python, installable via `pipx install qwen-assistant` on any modern distro.

## 10. Naming Note

The `qwen` binary name may collide with future official Qwen tooling; `qwenadm` or `sysqwen` are safe alternatives — a one-line change in `pyproject.toml`.


