import sys

import ipc

_IPC_MODE = False
_CURRENT_PHASE = 0


def set_ipc_mode(enabled: bool):
    global _IPC_MODE
    _IPC_MODE = enabled


def set_phase(phase: int):
    global _CURRENT_PHASE
    _CURRENT_PHASE = phase


def log_info(msg: str):
    """Standard informational logs."""
    if _IPC_MODE:
        ipc.send_log(msg)
    else:
        print(f"[*] {msg}")


def log_error(msg: str):
    """Error logging."""
    if _IPC_MODE:
        ipc.send_error(msg)
    else:
        print(f"[!] ERROR: {msg}", file=sys.stderr)


def log_progress(value: float, label: str):
    """Unified progress reporter for terminal and IPC streams. Used in modules."""
    if _IPC_MODE:
        ipc.send_progress(value=value, label=label, phase=_CURRENT_PHASE)
    else:
        percent = int(value * 100)
        # Use carriage return to overwrite progress line cleanly on CLI
        sys.stdout.write(f"\r[*] {label} ({percent}%)")
        sys.stdout.flush()
        if value >= 1.0:
            print()  # Final newline when task completes


def log_event(event_type: str, data: dict):
    """Generic event sender for IPC, prints gracefully in CLI.
       Used in pipeline.py and ipc_handlers.py."""
    if _IPC_MODE:
        payload = {"type": event_type}
        payload.update(data)
        ipc.send(payload)
    else:
        details = ", ".join(f"{k}={v}" for k, v in data.items())
        print(f"[*] EVENT [{event_type}]: {details}")


def log_done(run_name: str, output_path: str):
    """Unified completion signal. Used in pipeline.py"""
    if _IPC_MODE:
        ipc.send_done({"run_name": run_name, "output": output_path})
    else:
        print(f"[*] Done: Pipeline complete for '{run_name}'. Output saved to: {output_path}")
