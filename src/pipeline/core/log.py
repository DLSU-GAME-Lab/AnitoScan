import os
import sys
import threading

import ipc

_IPC_MODE = False
_CURRENT_PHASE = 0
_STATE_LOCK = threading.Lock()
_CURRENT_RUN_ID = os.environ.get("ANITOSCAN_RUN_ID")


def set_ipc_mode(enabled: bool):
    global _IPC_MODE
    _IPC_MODE = enabled


def set_phase(phase: int):
    global _CURRENT_PHASE
    _CURRENT_PHASE = phase


def set_run_id(run_id):
    global _CURRENT_RUN_ID
    with _STATE_LOCK:
        _CURRENT_RUN_ID = run_id
        if run_id is None:
            os.environ.pop("ANITOSCAN_RUN_ID", None)
        else:
            os.environ["ANITOSCAN_RUN_ID"] = str(run_id)


def get_run_id():
    with _STATE_LOCK:
        return _CURRENT_RUN_ID


def log_info(msg: str):
    """Standard informational logs."""
    if _IPC_MODE:
        ipc.send_log(msg, run_id=get_run_id())
    else:
        print(f"[*] {msg}")


def log_error(msg: str):
    """Diagnostics always go to stderr and never contaminate protocol stdout."""
    print(f"[!] ERROR: {msg}", file=sys.stderr, flush=True)


def log_progress(value: float, label: str):
    """Unified progress reporter for terminal and IPC streams."""
    if _IPC_MODE:
        ipc.send_progress(
            value=value,
            label=label,
            phase=_CURRENT_PHASE,
            run_id=get_run_id(),
        )
    else:
        percent = int(value * 100)
        sys.stdout.write(f"\r[*] {label} ({percent}%)")
        sys.stdout.flush()
        if value >= 1.0:
            print()


def log_event(event_type: str, data: dict):
    """Send a typed event in IPC mode, adding the active run identifier."""
    if _IPC_MODE:
        payload = {"type": event_type}
        payload.update(data)
        run_id = get_run_id()
        if run_id is not None:
            payload["run_id"] = run_id
        ipc.send(payload)
    else:
        details = ", ".join(f"{key}={value}" for key, value in data.items())
        print(f"[*] EVENT [{event_type}]: {details}")


def log_done(run_name: str, output_path: str):
    """Unified completion signal. Used in pipeline.py."""
    if _IPC_MODE:
        data = {"run_name": run_name, "output": output_path}
        run_id = get_run_id()
        if run_id is not None:
            data["run_id"] = run_id
        ipc.send_done(data)
    else:
        print(f"[*] Done: Pipeline complete for '{run_name}'. Output saved to: {output_path}")
