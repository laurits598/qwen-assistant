"""Host facts included in every prompt: hostname, OS, kernel, uptime, timestamp."""

from __future__ import annotations

import platform
import socket
from datetime import datetime
from pathlib import Path
from typing import Dict


def _os_release() -> str:
    path = Path("/etc/os-release")
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    return platform.platform()


def _uptime() -> str:
    path = Path("/proc/uptime")
    if not path.is_file():
        return "unknown"
    seconds = float(path.read_text().split()[0])
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    return f"{days}d {hours}h {minutes}m"


def gather() -> Dict[str, str]:
    return {
        "hostname": socket.gethostname(),
        "os_release": _os_release(),
        "kernel": platform.release(),
        "uptime": _uptime(),
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
