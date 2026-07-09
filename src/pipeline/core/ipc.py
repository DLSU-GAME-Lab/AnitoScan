import json
import sys

def send(obj: dict):
    """Send a JSON message to the C++ editor via stdout. flush=True is critical."""
    print(json.dumps(obj), flush=True)

def send_progress(value: float, label: str = "", phase: int = 0):
    send({
        "type": "progress",
        "value": round(value, 2),
        "label": label,
        "phase": phase
    })

def status_update(log: str="", progress: float | None=None, progress_msg: str | None = None, phase: int=0):
    print(f"[*] {log}")
    if is_ipc_mode():
        # send_log(log)
        if progress is not None:
            if progress_msg is None:
                progress_msg = log
            send_progress(progress, progress_msg, phase)

def status_error(text: str=""):
    print(f"[!] Error: {text}")
    if is_ipc_mode():
        send_error(text)


def send_log(text: str):
    send({
        "type": "log",
        "text" : text
    })

def send_done(data: dict = {}):
    send({
        "type": "done",
        "data": data
    })

def send_error(text: str):
    send({"type": "error",
        "text": text
    })

def is_ipc_mode() -> bool:
    """Returns True if launched by the C++ editor via --ipc flag."""
    return "--ipc" in sys.argv


def make_ipc_input_callback():
    def callback(preview_path: str, count: int, frame_name: str) -> int | None: 
        send({
            "type":     "action_required",
            "frame":    frame_name,
            "preview":  preview_path,
            "count":    count,
        })

        send_log(f"Opened {frame_name} preview: {preview_path}")

        for raw_line in sys.stdin:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                response = json.loads(raw_line)
                if response.get("type") == "selection":
                    choice = response.get("choice")
                    if choice == "skip":
                        send_log(f"Skipped boundary selection")
                        return None
                    send_log(f"Selected {int(choice)} for {frame_name}")
                    return int(choice)
            except (json.JSONDecodeError, ValueError):
                continue
        return None
    return callback
