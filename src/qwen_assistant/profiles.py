"""Profile discovery, loading, and schema validation.

Resolution order: ~/.config/qwen/profiles/ shadows the packaged profiles/ directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from pydantic import BaseModel, Field, model_validator

from . import safety
from .config import user_profile_dir

BUILTIN_PROFILE_DIR = Path(__file__).parent / "profiles"


class ProfileError(Exception):
    """Raised when a profile is missing or invalid."""


class ArgSpec(BaseModel):
    name: str
    required: bool = False
    default: str = ""


class SafetyConfig(BaseModel):
    read_only: bool
    requires_root: bool = False


class CommandSpec(BaseModel):
    run: str
    label: Optional[str] = None
    timeout: Optional[int] = None          # falls back to Settings.command_timeout
    on_error: str = Field(default="continue", pattern="^(continue|abort)$")
    when: Optional[str] = None             # only run if this arg is non-empty
    max_lines: Optional[int] = None        # falls back to Settings.max_lines


class Profile(BaseModel):
    name: str = ""
    description: str = ""
    category: str = "general"
    safety: SafetyConfig                   # mandatory by design
    requires: List[str] = Field(default_factory=list)
    args: List[ArgSpec] = Field(default_factory=list)
    commands: List[CommandSpec]
    prompt: str
    focus: List[str] = Field(default_factory=list)
    source_path: Optional[str] = None      # set by loader, not by YAML

    @model_validator(mode="after")
    def _no_destructive_in_read_only(self) -> "Profile":
        if self.safety.read_only:
            for cmd in self.commands:
                reason = safety.find_destructive(cmd.run)
                if reason:
                    raise ValueError(
                        f"command {cmd.run!r} looks destructive ({reason}) "
                        f"but the profile claims read_only: true"
                    )
        return self


def _profile_dirs() -> List[Path]:
    dirs = []
    if user_profile_dir().is_dir():
        dirs.append(user_profile_dir())
    dirs.append(BUILTIN_PROFILE_DIR)
    return dirs


def discover() -> Dict[str, Path]:
    """Map profile name -> YAML path. First hit (user dir) wins."""
    found: Dict[str, Path] = {}
    for directory in _profile_dirs():
        for path in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml")):
            found.setdefault(path.stem, path)
    return found


def profile_exists(name: str) -> bool:
    return name in discover()


def load(name: str) -> Profile:
    paths = discover()
    if name not in paths:
        available = ", ".join(sorted(paths)) or "(none)"
        raise ProfileError(f"unknown profile {name!r}. Available: {available}")
    return load_path(paths[name])


def load_path(path: Path) -> Profile:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"{path}: invalid YAML: {exc}")
    if not isinstance(data, dict):
        raise ProfileError(f"{path}: expected a YAML mapping at top level")
    data.setdefault("name", path.stem)
    data["source_path"] = str(path)
    try:
        return Profile(**data)
    except Exception as exc:
        raise ProfileError(f"{path}: {exc}")


def load_all() -> Tuple[List[Profile], List[str]]:
    """Load every discoverable profile. Returns (profiles, error messages)."""
    profiles, errors = [], []
    for name, path in sorted(discover().items()):
        try:
            profiles.append(load_path(path))
        except ProfileError as exc:
            errors.append(str(exc))
    return profiles, errors
