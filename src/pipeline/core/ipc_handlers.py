import json
import sys
import time

from log import log_error, log_event, log_info, set_ipc_mode


def await_ipc_selection(request: dict) -> tuple[int | None, float]:
    """Sends a selection request over IPC and blocks until stdin receives the choice."""
    t0 = time.perf_counter()

    log_event("action_required", {
        "frame": request["frame_name"],
        "preview": request["preview_path"],
        "count": request["total_candidates"],
    })

    log_info(f"Opened {request['frame_name']} preview: {request['preview_path']}")

    choice = None
    while True:
        raw_line = sys.stdin.readline()
        if not raw_line:
            break

        line = raw_line.strip()
        if not line:
            continue

        try:
            cmd = json.loads(line)
            if cmd.get("type") == "selection":
                val = cmd.get("choice")
                if val == "skip":
                    log_info("Skipped boundary selection")
                    choice = None
                else:
                    choice = int(val)
                    log_info(f"Selected {choice} for {request['frame_name']}")
                break
        except (json.JSONDecodeError, ValueError):
            pass

    wait_time = time.perf_counter() - t0
    return choice, wait_time


def listen_for_ipc_commands(run_pipeline_callback):
    """Main IPC event loop listening on stdin."""
    set_ipc_mode(True)
    log_info("Backend ready")

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            cmd = json.loads(raw_line)
        except json.JSONDecodeError:
            log_error("Bad JSON received")
            continue

        action = cmd.get("action")

        if action == "run_pipeline":
            try:
                run_pipeline_callback(cmd, ipc_mode=True)
            except (RuntimeError, ValueError, OSError) as error:
                log_error(str(error))
        else:
            log_error(f"Unknown action: {action}")

    log_info("Backend exiting")
