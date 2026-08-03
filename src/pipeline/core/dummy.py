import base64
import json
import re
import sys
import threading
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
PREVIEW_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
CUBE_OBJ = """# Dummy backend cube
v -0.5 -0.5 -0.5
v 0.5 -0.5 -0.5
v 0.5 0.5 -0.5
v -0.5 0.5 -0.5
v -0.5 -0.5 0.5
v 0.5 -0.5 0.5
v 0.5 0.5 0.5
v -0.5 0.5 0.5
f 1 2 3 4
f 5 8 7 6
f 1 5 6 2
f 2 6 7 3
f 3 7 8 4
f 5 1 4 8
"""

send_lock = threading.Lock()
session_lock = threading.Lock()
active_session = None


def send(event):
    with send_lock:
        print(json.dumps(event, separators=(",", ":")), flush=True)


def diagnostic(message):
    print(message, file=sys.stderr, flush=True)


def emit_cancelled(session):
    send({"type": "run_cancelled", "run_id": session["run_id"]})


def interruptible_delay(session, duration=0.08):
    return session["cancel"].wait(duration)


def run_worker(session):
    global active_session

    run_id = session["run_id"]
    try:
        workspace = (PROJECT_ROOT / "data" / "runs" / "dummy" / run_id).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        send({"type": "workspace_ready", "run_id": run_id, "workspace_path": str(workspace)})
        send({"type": "log", "run_id": run_id, "text": "Dummy run started: " + session["name"]})

        phase_labels = ("Capture", "Masking", "Spatial", "Geometry", "Export")
        for phase, label in enumerate(phase_labels, start=1):
            for value in (0.0, 0.5, 1.0):
                if session["cancel"].is_set():
                    emit_cancelled(session)
                    return
                send({
                    "type": "progress",
                    "run_id": run_id,
                    "phase": phase,
                    "value": value,
                    "label": label,
                })
                if interruptible_delay(session):
                    emit_cancelled(session)
                    return

            if phase == 2:
                preview = (workspace / "mask-preview.png").resolve()
                preview.write_bytes(PREVIEW_PNG)
                send({
                    "type": "selection_required",
                    "run_id": run_id,
                    "frame": "frame-0001",
                    "preview_path": str(preview),
                    "candidate_count": 3,
                })
                while not session["selection"].wait(0.05):
                    if session["cancel"].is_set():
                        emit_cancelled(session)
                        return
                if session["cancel"].is_set():
                    emit_cancelled(session)
                    return
                send({"type": "log", "run_id": run_id, "text": "Selection received"})

        output_model = (workspace / "model.obj").resolve()
        output_model.write_text(CUBE_OBJ, encoding="utf-8")
        if session["cancel"].is_set():
            emit_cancelled(session)
            return
        send({"type": "run_completed", "run_id": run_id, "output_model_path": str(output_model)})
    except Exception as error:
        send({"type": "run_failed", "run_id": run_id, "message": str(error)})
    finally:
        with session_lock:
            if active_session is session:
                active_session = None


def reject_start(run_id, message):
    if isinstance(run_id, str):
        send({"type": "run_failed", "run_id": run_id, "message": message})
    diagnostic(message)


def handle_command(command):
    global active_session

    if not isinstance(command, dict):
        diagnostic("Ignoring command: expected a JSON object")
        return

    action = command.get("action")
    run_id = command.get("run_id")

    if action == "start_run":
        name = command.get("name")
        if not isinstance(run_id, str) or not run_id or not RUN_ID_PATTERN.fullmatch(run_id):
            reject_start(run_id, "Invalid run_id")
            return
        if not isinstance(name, str):
            reject_start(run_id, "Invalid start_run name")
            return

        with session_lock:
            if active_session is not None:
                reject_start(run_id, "A run is already active")
                return
            session = {
                "run_id": run_id,
                "name": name,
                "cancel": threading.Event(),
                "selection": threading.Event(),
                "choice": None,
                "worker": None,
            }
            worker = threading.Thread(target=run_worker, args=(session,), name="dummy-backend-worker")
            session["worker"] = worker
            active_session = session
            worker.start()
        return

    if action == "submit_selection":
        choice = command.get("choice")
        if choice is not None and (isinstance(choice, bool) or not isinstance(choice, int)):
            diagnostic("Ignoring submit_selection: choice must be an integer or null")
            return
        with session_lock:
            session = active_session
            if session is None or run_id != session["run_id"]:
                diagnostic("Ignoring submit_selection: run_id does not match the active run")
                return
            session["choice"] = choice
            session["selection"].set()
        return

    if action == "cancel_run":
        with session_lock:
            session = active_session
            if session is None or run_id != session["run_id"]:
                diagnostic("Ignoring cancel_run: run_id does not match the active run")
                return
            session["cancel"].set()
        return

    diagnostic("Ignoring command: unsupported action")


def main():
    send({"type": "backend_ready"})
    for line in sys.stdin:
        try:
            command = json.loads(line)
        except json.JSONDecodeError as error:
            diagnostic("Ignoring invalid JSON command: " + str(error))
            continue
        handle_command(command)

    with session_lock:
        session = active_session
        if session is not None:
            session["cancel"].set()
            worker = session["worker"]
        else:
            worker = None
    if worker is not None:
        worker.join()


if __name__ == "__main__":
    main()
