import json
import sys

def send(obj: dict):
    """Send a JSON message to the C++ editor via stdout. flush=True is critical."""
    print(json.dumps(obj), flush=True)

def send_progress(value: float, label: str = "", phase: int = 0):
    send({"type": "progress", "value": round(value, 2), "label": label, "phase": phase})

def send_log(text: str):
    send({"type": "log", "text" : text})

def send_done(data: dict = {}):
    send({"type": "done", "data": data})

def send_error(text: str):
    send({"type": "error", "text": text})

def is_ipc_mode() -> bool:
    """Returns True if launched by the C++ editor via --ipc flag."""
    return len(sys.argv) > 1 and sys.argv[1] == "--ipc"
