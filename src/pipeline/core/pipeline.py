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

def run_phase1(parent_module_path, manifest_path, args):
    # 1. Launch Phase 1: Capture
    # This locates capture.py relative to this script's directory
    module_path = parent_module_path / "capture.py"
    cmd = [sys.executable, str(module_path), "--manifest", str(manifest_path)]
    if args.force:
        cmd.append("--force")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] Pipeline failed at Phase 1 (Capture). Exit code: {e.returncode}")
        sys.exit(e.returncode)

def run_phase2(parent_module_path, manifest_path, args):
    # 1. Launch Phase 1: Capture
    # This locates capture.py relative to this script's directory
    module_path = parent_module_path / "remove_background.py"
    cmd = [sys.executable, str(module_path), "--manifest", str(manifest_path)]
    if args.force:
        cmd.append("--force")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] Pipeline failed at Phase 2 (Remove Background). Exit code: {e.returncode}")
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
    args = parser.parse_args()

    # 0.2. Establish Workspace (WORKSPACE_ROOT/[name]/)
    base_dir = (WORKSPACE_DIR / args.name).resolve()
    capture_dir = base_dir / "01_capture" / "raw_frames"
    mask_dir = base_dir / "01_capture" / "masked_frames"

    manifest_path = base_dir / "manifest.json"

    capture_dir.mkdir(parents=True, exist_ok=True)
    mask_dir.mkdir(parents=True, exist_ok=True)
    
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
        "settings": {"requested_fps": args.fps},
        "status": {
            "phase": 1,
            "completed": [],
        },
        "paths": {
            "run_root": str(base_dir),
            "raw_frames": str(capture_dir),
            "masked_frames": str(mask_dir),
        },
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    print(f"[*] Workspace initialized: {base_dir}")
    print(f"[*] Mode: {args.mode} | Target FPS: {args.fps}")

    parent_module_path = Path(__file__).parent.parent / "modules"

    run_phase1(parent_module_path, manifest_path, args)
    run_phase2(parent_module_path, manifest_path, args)


if __name__ == "__main__":
    run_pipeline()
