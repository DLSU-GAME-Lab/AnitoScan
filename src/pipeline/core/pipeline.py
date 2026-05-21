import argparse
import json
import subprocess
import sys
from pathlib import Path

# DIRECTORY RESOLUTION
SCRIPT_PATH = Path(__file__).resolve()  # /src/pipeline/core/pipeline.py
PROJECT_ROOT = SCRIPT_PATH.parent.parent.parent.parent
WORKSPACE_DIR = PROJECT_ROOT / "data" / "runs"  # /data/runs/
MODULES_DIR = SCRIPT_PATH.parent.parent / "modules"  # /src/


# IPC helpers
def send(obj: dict):
    print(json.dumps(obj), flush=True)

def send_progress(value: float, label: str = ""):
    send({"type": "progress", "value": round(value, 2), "label": label})

def send_log(text: str):
    send({"type": "log", "text" : text})

def send_done(data: dict = {}):
    send({"type": "done", "data": data})

def send_error(text: str):
    send({"type": "error", "text": text})

def run_phase1(parent_module_path, manifest_path, args):
    # 1. Launch Phase 1: Capture
    module_path = parent_module_path / "capture.py"
    cmd = [
        sys.executable,
        str(module_path),
        "--manifest",
        str(manifest_path),
        "--blur-threshold",
        str(args.blur_threshold),
        "--proxy-width",
        str(args.proxy_width),
        "--jpg-quality",
        str(args.jpg_quality),
        "--max_search",
        str(args.max_search),
    ]
    if args.force:
        cmd.append("--force")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] Pipeline failed at Phase 1 (Capture). Exit code: {e.returncode}")
        sys.exit(e.returncode)


def run_phase2(parent_module_path, manifest_path, args):
    # 2. Launch Phase 2: Masking
    module_path = parent_module_path / "remove_background.py"
    cmd = [
        sys.executable,
        str(module_path),
        "--manifest",
        str(manifest_path),
        "--iou_threshold",
        str(args.iou_threshold),
        "--drift_limit",
        str(args.drift_limit),
        "--max_yoloe_failures",
        str(args.max_yoloe_failures),
        "--yoloe_model_size",
        str(args.yoloe_model_size),
    ]
    if args.force:
        cmd.append("--force")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] Pipeline failed at Phase 2 (Masking). Exit code: {e.returncode}")
        sys.exit(e.returncode)


def run_phase3(parent_module_path, manifest_path, args):
    # 1. Launch Phase 3: Spatial Initialization
    module_path = parent_module_path / "spatial.py"
    cmd = [sys.executable, str(module_path), "--manifest", str(manifest_path)]
    if args.force:
        cmd.append("--force")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(
            f"[!] Pipeline failed at Phase 3 (Spatial Initialization). Exit code: {e.returncode}"
        )
        sys.exit(e.returncode)


def run_phase4(parent_module_path, manifest_path, args):
    # 1. Launch Phase 4: Geometry generation
    module_path = parent_module_path / "geometry.py"
    cmd = [sys.executable, str(module_path), "--manifest", str(manifest_path)]
    if args.force:
        cmd.append("--force")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(
            f"[!] Pipeline failed at Phase 4 (Geometry Generation). Exit code: {e.returncode}"
        )
        sys.exit(e.returncode)


def run_pipeline():
    # 0.1. Define the Interface
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
        help="Path to folder (photos/videos) or a specific media file",
    )
    parser.add_argument(
        "--fps",
        type=int,
        required=True,
        help="Explicit frames-per-second for initial extraction",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["disk", "pipe"],
        default="disk",
        help="Data handling mode: 'disk' (visibility) or 'pipe' (performance)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Bypass caching and force a fresh execution of all active pipeline phases",
    )
    parser.add_argument(
        "--blur-threshold",
        type=float,
        default=200.0,
        help="Laplacian variance threshold",
    )
    parser.add_argument(
        "--proxy-width", type=int, default=640, help="Width for blur check proxy"
    )
    parser.add_argument(
        "--jpg-quality", type=int, default=85, help="JPEG quality 1-100"
    )
    parser.add_argument(
        "--max_search",
        type=int,
        default=3,
        help="Max adjacent frames to search if blurry frame is found",
    )
    parser.add_argument(
        "--iou_threshold",
        type=float,
        default=0.15,
        help="Minimum overlap between boundary boxes",
    )
    parser.add_argument(
        "--drift_limit",
        type=int,
        default=500,
        help="Maximum drift limit between boundary boxes",
    )
    parser.add_argument(
        "--max_yoloe_failures",
        type=int,
        default=2,
        help="Maximum failures before doing automatic reset for YOLOE",
    )
    parser.add_argument(
        "--yoloe_model_size",
        type=str,
        choices=["n", "s", "m", "l", "x"],
        default="s",
        help="YOLOE model size",
    )
    args = parser.parse_args()

    # 0.2. Establish Workspace (WORKSPACE_ROOT/[name]/)
    base_dir = (WORKSPACE_DIR / args.name).resolve()
    capture_dir = base_dir / "01_capture"
    mask_dir = base_dir / "02_masking"
    spatial_dir = base_dir / "03_spatial"
    geometry_dir = base_dir / "04_geometry"

    manifest_path = base_dir / "manifest.json"

    capture_dir.mkdir(parents=True, exist_ok=True)
    mask_dir.mkdir(parents=True, exist_ok=True)
    spatial_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(PROJECT_ROOT / "data" / "input" / Path(args.input)).resolve()

    # If the path provided doesn't exist locally, check data/input/
    if not input_path.exists():
        print(f"[!] Input source not found: {args.input}")
        sys.exit(1)

    # 0.3. Create the Manifest
    manifest = {
        "run_name": args.name,
        "input_source": str(input_path),
        "mode": args.mode,
        "settings": {
            "requested_fps": args.fps,
            "blur_threshold": args.blur_threshold,
            "proxy_width": args.proxy_width,
            "jpg_quality": args.jpg_quality,
            "max_search": args.max_search,
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
    print(f"[*] Mode: {args.mode} | Target FPS: {args.fps}")

    parent_module_path = Path(__file__).parent.parent / "modules"

    run_phase1(parent_module_path, manifest_path, args)
    run_phase2(parent_module_path, manifest_path, args)
    run_phase3(parent_module_path, manifest_path, args)
    run_phase4(parent_module_path, manifest_path, args)


if __name__ == "__main__":
    run_pipeline()
