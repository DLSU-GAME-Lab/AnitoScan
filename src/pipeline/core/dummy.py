import binascii
import json
import re
import struct
import sys
import threading
import zlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
INVALID_RUN_NAME_PATTERN = re.compile(r'[<>:"/\\|?*]|[\x00-\x1f]')

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


def write_preview(path):
    width = 480
    height = 270
    colors = ((220, 90, 90), (90, 190, 120), (90, 130, 220))
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            color = colors[min(x * len(colors) // width, len(colors) - 1)]
            shade = 25 if (x // 16 + y // 16) % 2 else 0
            rows.extend(min(channel + shade, 255) for channel in color)

    def chunk(kind, data):
        payload = kind + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", binascii.crc32(payload))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(rows)))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def write_manifest(session, state, phase, output_model=None, error=None):
    workspace = session.get("workspace")
    if workspace is None:
        return

    manifest = {
        "run_id": session["run_id"],
        "run_name": session["name"],
        "input_source": session["config"]["input"],
        "mode": session["config"]["mode"],
        "settings": {
            "minimum_frames": session["config"]["minimum_frames"],
            "capture_mode": session["config"]["capture_mode"],
            "quality": session["config"]["quality"],
            "force": session["config"]["force"],
            "iou_threshold": session["config"]["iou_threshold"],
            "drift_limit": session["config"]["drift_limit"],
            "yoloe_model_size": session["config"]["yoloe_model_size"],
        },
        "status": {
            "state": state,
            "phase": phase,
            "completed": session["completed"],
        },
        "paths": {
            "run_root": str(workspace),
        },
    }
    if output_model is not None:
        manifest["paths"]["output_model"] = str(output_model)
    if error is not None:
        manifest["error"] = error

    manifest_path = workspace / "manifest.json"
    temporary_path = workspace / "manifest.json.tmp"
    temporary_path.write_text(json.dumps(manifest, indent=4), encoding="utf-8")
    temporary_path.replace(manifest_path)


def emit_cancelled(session):
    write_manifest(session, "cancelled", session.get("phase", 0))
    send({"type": "run_cancelled", "run_id": session["run_id"]})


def interruptible_delay(session, duration=0.08):
    return session["cancel"].wait(duration)



def is_valid_run_name(name):
    return (
        isinstance(name, str)
        and bool(name)
        and name not in (".", "..")
        and not name.endswith((" ", "."))
        and INVALID_RUN_NAME_PATTERN.search(name) is None
    )


def run_worker(session):
    global active_session

    run_id = session["run_id"]
    try:
        workspace = (PROJECT_ROOT / "data" / "runs" / "dummy" / session["name"]).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        session["workspace"] = workspace
        write_manifest(session, "running", 0)
        send({"type": "workspace_ready", "run_id": run_id, "workspace_path": str(workspace)})
        send({"type": "log", "run_id": run_id, "text": "Dummy run started: " + session["name"]})

        phase_labels = ("Capture", "Masking", "Spatial", "Geometry", "Export")
        for phase, label in enumerate(phase_labels, start=1):
            session["phase"] = phase
            write_manifest(session, "running", phase)
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
                write_preview(preview)
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

            session["completed"].append(label.lower())
            write_manifest(session, "running", phase)

        output_model = (workspace / "model.obj").resolve()
        output_model.write_text(CUBE_OBJ, encoding="utf-8")
        if session["cancel"].is_set():
            emit_cancelled(session)
            return
        write_manifest(session, "completed", 5, output_model)
        send({"type": "run_completed", "run_id": run_id, "output_model_path": str(output_model)})
    except Exception as error:
        write_manifest(session, "failed", session.get("phase", 0), error=str(error))
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
        if not is_valid_run_name(name):
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
                "workspace": None,
                "phase": 0,
                "completed": [],
                "config": {
                    "input": command.get("input", ""),
                    "minimum_frames": command.get("minimum_frames", 45),
                    "mode": command.get("mode", "disk"),
                    "capture_mode": command.get("capture_mode", "auto"),
                    "quality": command.get("quality", "fast"),
                    "force": command.get("force", False),
                    "iou_threshold": command.get("iou_threshold", 0.5),
                    "drift_limit": command.get("drift_limit", 200),
                    "yoloe_model_size": command.get("yoloe_model_size", "s"),
                },
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
