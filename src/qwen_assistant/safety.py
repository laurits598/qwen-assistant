"""Safety tiers and destructive-command detection.

Tiers:
  read-only   -> runs immediately (read_only: true, requires_root: false)
  privileged  -> confirmation unless --yes (requires_root: true)
  destructive -> typed-name confirmation; --yes never bypasses (read_only: false)
"""

from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

# Patterns that must never appear in a profile claiming read_only: true.
DESTRUCTIVE_PATTERNS: List[Tuple[str, str]] = [
    (r"\brm\s+-\w*[rf]", "recursive/forced rm"),
    (r"\bmkfs(\.\w+)?\b", "filesystem creation"),
    (r"\bdd\b.*\bof=/dev/", "raw write to block device"),
    (r">\s*/dev/(sd|nvme|hd|vd)", "redirect to block device"),
    (r"\bsystemctl\s+(stop|disable|mask)\b", "stopping/disabling services"),
    (r"\b(shutdown|reboot|poweroff|halt)\b", "power state change"),
    (r"\bdocker\b.*\bprune\b", "docker prune"),
    (r"\bdocker\s+(rm|rmi|kill|stop)\b", "docker destructive subcommand"),
    (r"\biptables\s+-[DFX]\b", "firewall rule deletion/flush"),
    (r"\b(userdel|groupdel)\b", "account deletion"),
    (r"\b(truncate|shred)\b", "file destruction"),
    (r"\bapt(-get)?\s+(remove|purge|autoremove)\b", "package removal"),
    (r"\bchmod\b|\bchown\b", "permission/ownership change"),
    (r"\bcrontab\s+-r\b", "crontab removal"),
]

_COMPILED = [(re.compile(p), reason) for p, reason in DESTRUCTIVE_PATTERNS]


def find_destructive(command: str) -> Optional[str]:
    """Return a reason string if the command matches a destructive pattern, else None."""
    for pattern, reason in _COMPILED:
        if pattern.search(command):
            return reason
    return None


def tier(read_only: bool, requires_root: bool) -> str:
    if not read_only:
        return "destructive"
    if requires_root:
        return "privileged"
    return "read-only"


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0
