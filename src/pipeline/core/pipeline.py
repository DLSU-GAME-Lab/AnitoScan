import argparse
import json
import subprocess
import sys
from pathlib import Path

# DIRECTORY RESOLUTION
SCRIPT_PATH = Path(__file__).resolve()  # /src/pipeline/core/pipeline.py
PROJECT_ROOT = SCRIPT_PATH.parent.parent.parent.parent
WORKSPACE_DIR = PROJECT_ROOT / "data" / "runs"  # /data/runs/
MODULES_DIR = SCRIPT_PATH.parent.parent / "modules"  # /src/pipeline/modules/


def run_phase1(parent_module_path, manifest_path, args):
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
    if args.image:
        cmd.append("--image")
    if args.video:
        cmd.append("--video")

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] Pipeline failed at Phase 1 (Capture). Exit code: {e.returncode}")
        sys.exit(e.returncode)


def run_phase2(parent_module_path, manifest_path, args):
    module_path = parent_module_path / "remove_background.py"
    cmd = [
        sys.executable,
        str(module_path),
        "--manifest",
        str(manifest_path),
        "--yoloe_model_size",
        str(args.yoloe_model_size),
        "--iou_threshold",
        str(args.iou_threshold),
        "--drift_limit",
        str(args.drift_limit),
    ]

    if args.force:
        cmd.append("--force")

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] Pipeline failed at Phase 2 (Masking). Exit code: {e.returncode}")
        sys.exit(e.returncode)


def run_phase3(parent_module_path, manifest_path, args):
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
    module_path = parent_module_path / "geometry.py"

    # Translate quality preset to geometry parameters
    if args.quality == "fast":
        train_iters, densify, opacity = 7000, 5000, 1000
    elif args.quality == "medium":
        train_iters, densify, opacity = 15000, 7500, 3000
    elif args.quality == "detailed":
        train_iters, densify, opacity = 30000, 15000, 3000

    cmd = [
        sys.executable,
        str(module_path),
        "--manifest",
        str(manifest_path),
        "--train_iterations",
        str(train_iters),
        "--densify_until_iter",
        str(densify),
        "--opacity_reset_interval",
        str(opacity),
    ]

    if args.force:
        cmd.append("--force")

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(
            f"[!] Pipeline failed at Phase 4 (Geometry Generation). Exit code: {e.returncode}"
        )
        sys.exit(e.returncode)


def run_phase5(parent_module_path, manifest_path, args):
    module_path = parent_module_path / "export.py"
    cmd = [sys.executable, str(module_path), "--manifest", str(manifest_path)]
    if args.force:
        cmd.append("--force")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(
            f"[!] Pipeline failed at Phase 5 (Export & Baking). Exit code: {e.returncode}"
        )
        sys.exit(e.returncode)


def run_pipeline():
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

    # Geometry defaults
    parser.add_argument(
        "--quality",
        type=str,
        choices=["fast", "medium", "detailed"],
        default="fast",
        help="Quality preset for 2DGS generation (controls iterations, densification, and opacity resets)",
    )

    args = parser.parse_args()

    base_dir = (WORKSPACE_DIR / args.name).resolve()
    capture_dir = base_dir / "01_capture"
    mask_dir = base_dir / "02_masking"
    spatial_dir = base_dir / "03_spatial"
    geometry_dir = base_dir / "04_geometry"

    export_dir = Path(PROJECT_ROOT / "data" / "output" / args.name).resolve()

    manifest_path = base_dir / "manifest.json"

    capture_dir.mkdir(parents=True, exist_ok=True)
    mask_dir.mkdir(parents=True, exist_ok=True)
    spatial_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(PROJECT_ROOT / "data" / "input" / Path(args.input)).resolve()

    if not input_path.exists():
        print(f"[!] Input source not found: {args.input}")
        sys.exit(1)

    manifest = {
        "run_name": args.name,
        "input_source": str(input_path),
        "mode": args.mode,
        "settings": {
            "minimum_frames": args.minimum_frames,
            "blur_threshold": args.blur_threshold,
            "proxy_width": args.proxy_width,
            "jpg_quality": args.jpg_quality,
            "max_search": args.max_search,
            "quality": args.quality,
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
            "export": str(export_dir),
        },
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    print(f"[*] Workspace initialized: {base_dir}")
    print(f"[*] Minimum Targeted Frame Dataset Size: {args.minimum_frames}")

    parent_module_path = Path(__file__).parent.parent / "modules"

    run_phase1(parent_module_path, manifest_path, args)
    run_phase2(parent_module_path, manifest_path, args)
    run_phase3(parent_module_path, manifest_path, args)
    run_phase4(parent_module_path, manifest_path, args)
    run_phase5(parent_module_path, manifest_path, args)


if __name__ == "__main__":
    run_pipeline()
