import json


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


def send_log(text: str):
    send({
        "type": "log",
        "text" : text
    })


def send_done(data: dict | None = None):
    if data is None:
        data = {}
    send({
        "type": "done",
        "data": data
    })


def send_error(text: str):
    send({"type": "error",
        "text": text
    })
