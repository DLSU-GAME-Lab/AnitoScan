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
DUMMY_PHASE_DURATION_SECONDS = 10.0

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
    pixels = bytearray(width * height * 3)

    def set_pixel(x, y, color):
        if 0 <= x < width and 0 <= y < height:
            offset = (y * width + x) * 3
            pixels[offset:offset + 3] = bytes(color)

    def draw_line(start, end, color, thickness=1):
        x1, y1 = start
        x2, y2 = end
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        step_x = 1 if x1 < x2 else -1
        step_y = 1 if y1 < y2 else -1
        error = dx + dy
        while True:
            radius = thickness // 2
            for offset_y in range(-radius, radius + 1):
                for offset_x in range(-radius, radius + 1):
                    set_pixel(x1 + offset_x, y1 + offset_y, color)
            if x1 == x2 and y1 == y2:
                break
            doubled_error = 2 * error
            if doubled_error >= dy:
                error += dy
                x1 += step_x
            if doubled_error <= dx:
                error += dx
                y1 += step_y

    def fill_polygon(points, color):
        minimum_y = max(0, min(point[1] for point in points))
        maximum_y = min(height - 1, max(point[1] for point in points))
        for y in range(minimum_y, maximum_y + 1):
            intersections = []
            for index, first in enumerate(points):
                second = points[(index + 1) % len(points)]
                if first[1] == second[1]:
                    continue
                low, high = sorted((first, second), key=lambda point: point[1])
                if low[1] <= y < high[1]:
                    ratio = (y - low[1]) / (high[1] - low[1])
                    intersections.append(round(low[0] + ratio * (high[0] - low[0])))
            intersections.sort()
            for start, end in zip(intersections[0::2], intersections[1::2]):
                for x in range(start, end + 1):
                    set_pixel(x, y, color)

    def draw_box(bounds, color, label):
        left, top, right, bottom = bounds
        draw_line((left, top), (right, top), color, 3)
        draw_line((right, top), (right, bottom), color, 3)
        draw_line((right, bottom), (left, bottom), color, 3)
        draw_line((left, bottom), (left, top), color, 3)

        for y in range(top, top + 18):
            for x in range(left, left + 18):
                set_pixel(x, y, color)
        digit_patterns = {
            1: ("010", "110", "010", "010", "111"),
            2: ("110", "001", "010", "100", "111"),
            3: ("110", "001", "010", "001", "110"),
        }
        for row, pattern in enumerate(digit_patterns[label]):
            for column, enabled in enumerate(pattern):
                if enabled == "1":
                    for offset_y in range(2):
                        for offset_x in range(2):
                            set_pixel(left + 6 + column * 2 + offset_x, top + 4 + row * 2 + offset_y, (18, 22, 30))

    for y in range(height):
        blend = y / height
        background = (
            round(16 + 14 * blend),
            round(23 + 18 * blend),
            round(38 + 24 * blend),
        )
        for x in range(width):
            set_pixel(x, y, background)

    horizon = 205
    for x in range(0, width, 40):
        draw_line((width // 2, horizon), (x, height - 1), (41, 54, 72))
    for y in (216, 230, 248, 267):
        draw_line((0, y), (width - 1, y), (41, 54, 72))

    back_top_left = (166, 55)
    back_top_right = (270, 47)
    back_bottom_right = (277, 150)
    back_bottom_left = (172, 163)
    front_top_left = (196, 82)
    front_top_right = (300, 74)
    front_bottom_right = (307, 177)
    front_bottom_left = (202, 190)

    fill_polygon((back_top_left, back_top_right, front_top_right, front_top_left), (112, 151, 196))
    fill_polygon((back_top_left, front_top_left, front_bottom_left, back_bottom_left), (62, 91, 130))
    fill_polygon((front_top_left, front_top_right, front_bottom_right, front_bottom_left), (83, 119, 165))

    cube_edges = (
        (back_top_left, back_top_right),
        (back_top_right, back_bottom_right),
        (back_bottom_right, back_bottom_left),
        (back_bottom_left, back_top_left),
        (front_top_left, front_top_right),
        (front_top_right, front_bottom_right),
        (front_bottom_right, front_bottom_left),
        (front_bottom_left, front_top_left),
        (back_top_left, front_top_left),
        (back_top_right, front_top_right),
        (back_bottom_right, front_bottom_right),
        (back_bottom_left, front_bottom_left),
    )
    for edge in cube_edges:
        draw_line(*edge, (202, 219, 238), 2)

    draw_box((132, 64, 257, 207), (225, 86, 86), 1)
    draw_box((158, 40, 315, 198), (75, 205, 122), 2)
    draw_box((214, 30, 382, 170), (76, 139, 231), 3)

    rows = bytearray()
    for y in range(height):
        rows.append(0)
        start = y * width * 3
        rows.extend(pixels[start:start + width * 3])

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


def emit_progress_schedule(session, phase, schedule):
    previous_offset = 0.0
    for offset, value, label in schedule:
        delay = offset - previous_offset
        if delay > 0 and interruptible_delay(session, delay):
            emit_cancelled(session)
            return False
        if session["cancel"].is_set():
            emit_cancelled(session)
            return False
        send({
            "type": "progress",
            "run_id": session["run_id"],
            "phase": phase,
            "value": value,
            "label": label,
        })
        previous_offset = offset
    return True


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

        total_frames = max(1, int(session["config"]["minimum_frames"]))
        capture_schedule = [(0.0, 0.0, "Preparing capture...")]
        for step in range(1, 10):
            progress = step / 10
            frame = max(1, round(total_frames * progress))
            capture_schedule.append((
                float(step),
                progress,
                f"Copying frame {frame}/{total_frames}",
            ))
        capture_schedule.append((
            DUMMY_PHASE_DURATION_SECONDS,
            1.0,
            "Phase 1: Capture complete",
        ))

        masking_start_schedule = [
            (0.0, 0.0, "Starting Masking Phase..."),
            (1.0, 0.05, "Loading detection models..."),
            (2.0, 0.10, "Analyzing frame 1"),
        ]
        masking_finish_schedule = [(0.0, 0.10, "Selection received")]
        masking_progress = (0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.85)
        for offset, progress in enumerate(masking_progress, start=1):
            frame = max(1, round(total_frames * progress))
            masking_finish_schedule.append((
                float(offset),
                progress,
                f"Processed frame {frame}/{total_frames}",
            ))
        masking_finish_schedule.append((
            8.0,
            1.0,
            "Phase 2: Masking complete",
        ))

        spatial_schedule = [
            (0.0, 0.0, "Phase 3: Preparing images..."),
            (0.75, 0.05, f"Preparing image {max(1, round(total_frames / 3))} of {total_frames}"),
            (1.5, 0.10, f"Preparing image {max(1, round(total_frames * 2 / 3))} of {total_frames}"),
            (2.0, 0.15, "Phase 3: Running Bundle Adjustment..."),
            (10.0, 1.0, "Phase 3: Spatial initialization complete"),
        ]
        geometry_schedule = [
            (0.0, 0.0, "Phase 4: Preparing reconstruction..."),
            (1.0, 0.30, "Phase 4: Training 2DGS..."),
            (2.0, 0.38, "Training 1000/7000 iterations"),
            (3.0, 0.46, "Training 2000/7000 iterations"),
            (4.0, 0.54, "Training 3000/7000 iterations"),
            (5.0, 0.62, "Training 4000/7000 iterations"),
            (6.0, 0.70, "Training 5000/7000 iterations"),
            (7.0, 0.78, "Training 6000/7000 iterations"),
            (8.5, 0.85, "Phase 4: Extracting mesh..."),
            (10.0, 1.0, "Phase 4: Geometry complete"),
        ]
        export_schedule = [
            (0.0, 0.0, "Phase 5: Loading mesh..."),
            (1.0, 0.05, "Phase 5: Cleaning topology..."),
            (2.5, 0.15, "Phase 5: Decimating mesh..."),
            (4.0, 0.45, "Phase 5: Computing normals..."),
            (5.0, 0.50, "Phase 5: Unwrapping UVs..."),
            (7.0, 0.80, "Phase 5: Baking 4K texture..."),
            (9.0, 0.95, "Phase 5: Exporting OBJ..."),
            (10.0, 1.0, "Phase 5: Export complete"),
        ]

        phase_labels = ("Capture", "Masking", "Spatial", "Geometry", "Export")
        phase_schedules = {
            1: capture_schedule,
            3: spatial_schedule,
            4: geometry_schedule,
            5: export_schedule,
        }
        for phase, label in enumerate(phase_labels, start=1):
            session["phase"] = phase
            write_manifest(session, "running", phase)

            if phase == 2:
                if not emit_progress_schedule(session, phase, masking_start_schedule):
                    return

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

                if not emit_progress_schedule(session, phase, masking_finish_schedule):
                    return
            elif not emit_progress_schedule(session, phase, phase_schedules[phase]):
                return

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
