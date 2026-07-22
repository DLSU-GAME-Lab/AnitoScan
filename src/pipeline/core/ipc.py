"""Pure newline-delimited JSON line read/write transport mechanics for IPC."""

from __future__ import annotations

import json
import sys
import threading
from typing import Any

_SEND_LOCK = threading.Lock()


def send(obj: dict[str, Any]) -> None:
    """Send a JSON message object to stdout with immediate flushing."""
    with _SEND_LOCK:
        print(json.dumps(obj, separators=(",", ":")), flush=True)


def read_line() -> str | None:
    """Read a single stripped JSON line from stdin."""
    line = sys.stdin.readline()
    if not line:
        return None
    return line.strip()
