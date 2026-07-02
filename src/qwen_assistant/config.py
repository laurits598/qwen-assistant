"""Global settings: hardcoded defaults overridden by ~/.config/qwen/config.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_MODEL = "qwen2.5-coder:7b"


def config_dir() -> Path:
    return Path(os.environ.get("QWEN_CONFIG_DIR", str(Path.home() / ".config" / "qwen")))


def user_profile_dir() -> Path:
    return config_dir() / "profiles"


@dataclass
class Settings:
    model: str = DEFAULT_MODEL
    ollama_host: str = "http://localhost:11434"
    temperature: float = 0.2
    num_ctx: int = 16384
    command_timeout: int = 15  # default per-command timeout (seconds)
    max_lines: int = 200       # per-command output line cap
    max_bytes: int = 8192      # per-command output byte cap


def load_settings() -> Settings:
    settings = Settings()
    cfg = config_dir() / "config.yaml"
    if cfg.is_file():
        try:
            data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise SystemExit(f"Invalid config file {cfg}: {exc}")
        for key, value in data.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
    return settings
