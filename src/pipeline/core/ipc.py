import json
import sys
import threading
from typing import Optional


_SEND_LOCK = threading.Lock()


def send(obj: dict):
    """Write one compact, typed JSON message to protocol stdout."""
    if not isinstance(obj, dict) or not isinstance(obj.get("type"), str):
        raise ValueError("IPC messages must be dictionaries with a string 'type'")

    encoded = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    with _SEND_LOCK:
        sys.stdout.write(encoded + "\n")
        sys.stdout.flush()


def send_progress(value: float, label: str = "", phase: int = 0, run_id=None):
    payload = {
        "type": "progress",
        "value": round(value, 2),
        "label": label,
        "phase": phase,
    }
    if run_id is not None:
        payload["run_id"] = run_id
    send(payload)


def send_log(text: str, run_id=None):
    payload = {"type": "log", "text": text}
    if run_id is not None:
        payload["run_id"] = run_id
    send(payload)


def send_done(data: Optional[dict] = None):
    send({"type": "done", "data": data or {}})


def send_error(text: str, run_id=None):
    payload = {"type": "error", "text": text}
    if run_id is not None:
        payload["run_id"] = run_id
    send(payload)
