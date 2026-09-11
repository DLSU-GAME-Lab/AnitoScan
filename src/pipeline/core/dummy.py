import binascii
import struct
import zlib
from pathlib import Path

from cancellation import check_cancelled
from ipc_handlers import await_ipc_selection, listen_for_ipc_commands
from log import log_info, log_progress, set_phase
from manifest import load_manifest, update_manifest
from pipeline import run_pipeline_with_args

DUMMY_PHASE_DURATION_SECONDS = 10.0
DUMMY_TIME_SCALE = 0.5

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


def write_preview(path: Path) -> None:
    """Write the existing dummy masking-selection preview image."""
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
            0: ("111", "101", "101", "101", "111"),
            1: ("010", "110", "010", "010", "111"),
            2: ("110", "001", "010", "100", "111"),
        }
        for row, pattern in enumerate(digit_patterns[label]):
            for column, enabled in enumerate(pattern):
                if enabled == "1":
                    for offset_y in range(2):
                        for offset_x in range(2):
                            set_pixel(
                                left + 6 + column * 2 + offset_x,
                                top + 4 + row * 2 + offset_y,
                                (18, 22, 30),
                            )

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

    draw_box((132, 64, 257, 207), (225, 86, 86), 0)
    draw_box((158, 40, 315, 198), (75, 205, 122), 1)
    draw_box((214, 30, 382, 170), (76, 139, 231), 2)

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



def _emit_schedule(schedule, cancel_event) -> None:
    previous_offset = 0.0
    for offset, value, label in schedule:
        delay = (offset - previous_offset) * DUMMY_TIME_SCALE
        if delay > 0 and cancel_event is not None:
            cancel_event.wait(delay)
        check_cancelled(cancel_event)
        log_progress(value, label)
        previous_offset = offset


def _phase_schedules(total_frames: int) -> dict[int, list[tuple[float, float, str]]]:
    capture = [(0.0, 0.0, "Preparing capture...")]
    for step in range(1, 10):
        progress = step / 10
        frame = max(1, round(total_frames * progress))
        capture.append((float(step), progress, f"Copying frame {frame}/{total_frames}"))
    capture.append((DUMMY_PHASE_DURATION_SECONDS, 1.0, "Phase 1: Capture complete"))

    spatial = [
        (0.0, 0.0, "Phase 3: Preparing images..."),
        (3.5, 0.05, f"Preparing image {max(1, round(total_frames / 3))} of {total_frames}"),
        (5.25, 0.10, f"Preparing image {max(1, round(total_frames * 2 / 3))} of {total_frames}"),
        (7.0, 0.15, "Phase 3: Running Bundle Adjustment..."),
        (7.5, 0.30, "Phase 3: Matching image features..."),
        (8.0, 0.45, "Phase 3: Registering cameras..."),
        (8.5, 0.60, "Phase 3: Optimizing camera poses..."),
        (9.0, 0.75, "Phase 3: Triangulating scene points..."),
        (9.5, 0.90, "Phase 3: Refining reconstruction..."),
        (10.0, 1.0, "Phase 3: Spatial initialization complete"),
    ]
    geometry = [
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
    export = [
        (0.0, 0.0, "Phase 5: Loading mesh..."),
        (1.0, 0.05, "Phase 5: Cleaning topology..."),
        (2.5, 0.15, "Phase 5: Decimating mesh..."),
        (4.0, 0.45, "Phase 5: Computing normals..."),
        (5.0, 0.50, "Phase 5: Unwrapping UVs..."),
        (7.0, 0.80, "Phase 5: Baking 4K texture..."),
        (9.0, 0.95, "Phase 5: Exporting OBJ..."),
        (10.0, 1.0, "Phase 5: Export complete"),
    ]
    return {1: capture, 3: spatial, 4: geometry, 5: export}


def _run_dummy_masking(manifest: dict, total_frames: int, cancel_event) -> None:
    start_schedule = [
        (0.0, 0.0, "Starting Masking Phase..."),
        (1.0, 0.05, "Loading detection models..."),
        (2.0, 0.10, "Analyzing frame 1"),
    ]
    _emit_schedule(start_schedule, cancel_event)

    preview_path = Path(manifest["paths"]["masked_frames"]) / "mask-preview.png"
    write_preview(preview_path)
    choice, _ = await_ipc_selection({
        "frame_name": "frame-0001",
        "preview_path": str(preview_path.resolve()),
        "total_candidates": 3,
        "image_width": 480,
        "image_height": 270,
    })
    check_cancelled(cancel_event)
    log_info(f"Selection received: {choice}")

    finish_schedule = [(0.0, 0.10, "Selection received")]
    for offset, progress in enumerate((0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.85), start=1):
        frame = max(1, round(total_frames * progress))
        finish_schedule.append((float(offset), progress, f"Processed frame {frame}/{total_frames}"))
    finish_schedule.append((8.0, 1.0, "Phase 2: Masking complete"))
    _emit_schedule(finish_schedule, cancel_event)


def run_dummy_phase(
    phase_num: int,
    manifest_path: Path,
    args: dict,
    ipc_mode: bool = False,
    cancel_event=None,
) -> None:
    """Simulate one pipeline phase without importing or invoking a processing module."""
    del ipc_mode
    check_cancelled(cancel_event)
    set_phase(phase_num)
    path, manifest = load_manifest(manifest_path)
    total_frames = max(1, int(args.get("minimum_frames", 45)))

    log_info(f"Starting dummy Phase {phase_num}")
    if phase_num == 2:
        _run_dummy_masking(manifest, total_frames, cancel_event)
    else:
        schedule = _phase_schedules(total_frames).get(phase_num)
        if schedule is None:
            raise ValueError(f"Unknown pipeline phase: {phase_num}")
        _emit_schedule(schedule, cancel_event)

    check_cancelled(cancel_event)
    if phase_num == 5:
        output_dir = Path(manifest["paths"]["export"])
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{manifest['run_name']}_{args.get('quality', 'fast')}.obj"
        output_path.write_text(CUBE_OBJ, encoding="utf-8")

    update_manifest(path, manifest, phase_num)


def run_dummy_pipeline(args: dict, ipc_mode: bool = False, cancel_event=None):
    return run_pipeline_with_args(
        args,
        ipc_mode=ipc_mode,
        cancel_event=cancel_event,
        phase_executor=run_dummy_phase,
        validate_input=False,
    )


if __name__ == "__main__":
    listen_for_ipc_commands(run_dummy_pipeline)
