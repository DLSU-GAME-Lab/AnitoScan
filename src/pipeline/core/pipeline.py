import argparse
import json
import subprocess
import sys
from pathlib import Path

from ipc import send, send_progress, send_log, send_done, send_error, is_ipc_mode

# DIRECTORY RESOLUTION
SCRIPT_PATH = Path(__file__).resolve()  # /src/pipeline/core/pipeline.py
PROJECT_ROOT = SCRIPT_PATH.parent.parent.parent.parent
WORKSPACE_DIR = PROJECT_ROOT / "data" / "runs"  # /data/runs/
MODULES_DIR = SCRIPT_PATH.parent.parent / "modules"  # /src/pipeline/modules/


def _get(args, key, default=None):
    if isinstance(args, dict):
        return args.get(key, default)   # IPC mode
    return getattr(args, key, default)  # CLI mode  

def _run_phase(phase_num: int, phase_name: str, cmd: list, ipc_mode: bool):
    result = subprocess.run(cmd)
    if result.returncode != 0:
        msg = f"[!] Pipeline failed at Phase {phase_num} ({phase_name}). Exit code: {result.returncode}"
        if ipc_mode:
            raise RuntimeError(msg)
        else:
            print(f"[!] {msg}")
            sys.exit(result.returncode)



def run_phase1(parent_module_path, manifest_path, args, ipc_mode=False):
    # if not ipc_mode:
    #     ipc_mode = bool(_get(args, "ipc", False))

    # 1. Launch Phase 1: Capture
    module_path = parent_module_path / "capture.py"
    cmd = [
        sys.executable,
        str(module_path),
        "--manifest",
        str(manifest_path),
        "--blur-threshold",
        str(args.get("blur_threshold", 200.0)),
        "--proxy-width",
        str(args.get("proxy_width", 640)),
        "--jpg-quality",
        str(args.get("jpg_quality", 85)),
        "--max_search",
        str(args.get("max_search", 3)),
    ]
    if _get(args, "force"): cmd.append("--force")
    if _get(args, "image"): cmd.append("--image")
    if _get(args, "video"): cmd.append("--video")

    if ipc_mode: cmd.append("--ipc")

    _run_phase(1, "Capture", cmd, ipc_mode)


def run_phase2(parent_module_path, manifest_path, args, ipc_mode=False):
    module_path = parent_module_path / "remove_background.py"
    cmd = [
        sys.executable,
        str(module_path),
        "--manifest",
        str(manifest_path),
        "--iou_threshold",
        str(_get(args, "iou_threshold", 0.15)), 
        "--drift_limit",
        str(_get(args, "drift_limit", 500)),
       # "--max_yoloe_failures",
       # str(_get(args, "max_yoloe_failures", 2)),
        "--yoloe_model_size",
        str(_get(args, "yoloe_model_size", "s")),
    ]

    if _get(args, "force"): cmd.append("--force")

    if ipc_mode: cmd.append("--ipc")

    _run_phase(2, "Masking", cmd, ipc_mode)



def run_phase3(parent_module_path, manifest_path, args, ipc_mode=False):
    module_path = parent_module_path / "spatial.py"
    cmd = [sys.executable, str(module_path), "--manifest", str(manifest_path)]
    if _get(args, "force"):
        cmd.append("--force")
    _run_phase(3, "Spatial Initialization", cmd, ipc_mode)


def run_phase4(parent_module_path, manifest_path, args, ipc_mode=False):
    module_path = parent_module_path / "geometry.py"
    cmd = [sys.executable, str(module_path), "--manifest", str(manifest_path)]
    if _get(args, "force"):
        cmd.append("--force")
    _run_phase(4, "Geometry Generation", cmd, ipc_mode)


def run_pipeline_with_args(args: dict, ipc_mode: bool=False):
    name = _get(args, "name")   or ""
    input = _get(args, "input") or ""

    base_dir = (WORKSPACE_DIR / name).resolve()
    capture_dir = base_dir / "01_capture"
    mask_dir = base_dir / "02_masking"
    spatial_dir = base_dir / "03_spatial"
    geometry_dir = base_dir / "04_geometry"

    manifest_path = base_dir / "manifest.json"

    capture_dir.mkdir(parents=True, exist_ok=True)
    mask_dir.mkdir(parents=True, exist_ok=True)
    spatial_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(PROJECT_ROOT / "data" / "input" / input).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input source not found: {input}")
    
    manifest = {
        "run_name": args["name"],
        "input_source": str(input_path),
       # "mode": args.get("mode", "disk"),
        "mode":  _get(args, "mode", "disk"),
        "settings": {
            "minimum_frames": _get(args, "minimum_frames", 45),
            "blur_threshold": _get(args, "blur_threshold", 200.0),
            "proxy_width":    _get(args, "proxy_width", 640.0),
            "jpg_quality":    _get(args, "jpg_quality", 85),
            "max_search":     _get(args, "max_search", 3),
        },

        "status": {
            "phase": 1,
            "completed": [],
        },
        "paths": {
            "run_root": str(base_dir),
            "raw_frames": str(capture_dir),
            "masked_frames": str(mask_dir),
            "spatial": str(spatial_dir),
            "geometry": str(geometry_dir),
        },
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    print(f"[*] Workspace initialized: {base_dir}")

    if is_ipc_mode():
        send_log(f"Workspace initialized: {base_dir}")
        send({"type": "workspace_ready", "path": str(base_dir), "run_name": args["name"]})

    parent_module_path = Path(__file__).parent.parent / "modules"

    if is_ipc_mode(): send_progress(0.0, "[*] Starting Phase 1: Capture", phase=1)
    run_phase1(parent_module_path, manifest_path, args, ipc_mode)

    if is_ipc_mode(): send_progress(0.25, "[*] Starting Phase 2: Masking", phase=2)
    run_phase2(parent_module_path, manifest_path, args, ipc_mode)

    if is_ipc_mode(): send_progress(0.50, "[*] Starting Phase 3: Spatial", phase=3)
    run_phase3(parent_module_path, manifest_path, args, ipc_mode)

    if is_ipc_mode(): send_progress(0.75, "[*] Starting Phase 4: Geometry", phase=4)
    run_phase4(parent_module_path, manifest_path, args, ipc_mode)

    if is_ipc_mode(): send_progress(1.0, "[*] Complete")
    send_done({"run_name": name, "output": str(base_dir)})


def run_ipc_mode():
    send_log("Backend ready")
    send_log(is_ipc_mode().__str__())
    

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            cmd = json.loads(raw_line)
        except json.JSONDecodeError:
            send_error("Bad JSON received")
            continue

        action = cmd.get("action")

        if action == "run_pipeline":
            try:
                run_pipeline_with_args(cmd, ipc_mode=True)
            except FileNotFoundError as e:
                send_error(str(e))
            except RuntimeError as e:
                send_error(str(e))
        else:
            send_error(f"Unknown action: {action}")

    send_log("Backend exiting")




def run_cli_mode():
    parser = argparse.ArgumentParser(
        description="3D Reconstruction Pipeline Entry Point"
    )
    parser.add_argument(
        "--name",
        type=str,
        required=True,
        help="Unique name for this reconstruction run",
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Path to folder or a specific media file",
    )

    # Swapped --fps for --minimum_frames
    parser.add_argument(
        "--minimum_frames",
        type=int,
        default=45,
        help="Minimum target frame count required across the video duration for stable COLMAP parsing",
    )

    parser.add_argument("--mode", type=str, choices=["disk", "pipe"], default="disk")
    parser.add_argument("-f", "--force", action="store_true")

    parser.add_argument(
        "--image", action="store_true", help="Force image directory mode"
    )
    parser.add_argument("--video", action="store_true", help="Force video file mode")

    # Capture defaults
    parser.add_argument("--blur-threshold", type=float, default=200.0)
    parser.add_argument("--proxy-width", type=int, default=640)
    parser.add_argument("--jpg-quality", type=int, default=85)
    parser.add_argument("--max_search", type=int, default=3)

    # Tracking defaults
    parser.add_argument("--iou_threshold", type=float, default=0.50)
    parser.add_argument("--drift_limit", type=int, default=200)
    parser.add_argument(
        "--yoloe_model_size", type=str, choices=["n", "s", "m", "l", "x"], default="s"
    )

    args = parser.parse_args()

    run_pipeline_with_args(vars(args), ipc_mode=False)

    
if __name__ == "__main__":
    #run_pipeline()
    if len(sys.argv) > 1 and sys.argv[1] == "--ipc":
        run_ipc_mode()
    else:
        run_cli_mode()

