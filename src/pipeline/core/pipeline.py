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

    if args.get("force"):
        cmd.append("--force")

    if args.image:
        cmd.append("--image")
    if args.video:
        cmd.append("--video")

    _run_phase(1, "Capture", cmd, ipc_mode)

    # if args.force:
    #     cmd.append("--force")
    # try:
    #     subprocess.run(cmd, check=True)
    # except subprocess.CalledProcessError as e:
    #     print(f"[!] Pipeline failed at Phase 1 (Capture). Exit code: {e.returncode}")
    #     sys.exit(e.returncode)

    # if args.get("force"):
    #     cmd.append("--force")
    # result = subprocess.run(cmd)
    # if result.returncode != 0:
    #     raise RuntimeError(f"[!] Pipeline failed at Phase 1 (Capture). Exit code: {result.returncode}")


def run_phase2(parent_module_path, manifest_path, args, ipc_mode=False):
    module_path = parent_module_path / "remove_background.py"
    cmd = [
        sys.executable,
        str(module_path),
        "--manifest",
        str(manifest_path),
        "--yoloe_model_size",
        str(args.yoloe_model_size),
        "--iou_threshold",
        str(args.get("iou_threshold", 0.15)),
        "--drift_limit",
        str(args.get("drift_limit", 500)),
        "--max_yoloe_failures",
        str(args.get("max_yoloe_failures", 2)),
        "--yoloe_model_size",
        str(args.get("yoloe_model_size","s")),
    ]

    if args.get("force"):
        cmd.append("--force")

    _run_phase(2, "Masking", cmd, ipc_mode)

    # if args.force:
    #     cmd.append("--force")
    # try:
    #     subprocess.run(cmd, check=True)
    # except subprocess.CalledProcessError as e:
    #     print(f"[!] Pipeline failed at Phase 2 (Masking). Exit code: {e.returncode}")
    #     sys.exit(e.returncode)
    # if args.get("force"):
    #     cmd.append("--force")
    # result = subprocess.run(cmd)
    # if result.returncode != 0:
    #     raise RuntimeError(f"[!] Pipeline failed at Phase 2 (Masking). Exit code: {result.returncode}")


def run_phase3(parent_module_path, manifest_path, args, ipc_mode=False):
    # 1. Launch Phase 3: Spatial Initialization
    module_path = parent_module_path / "spatial.py"
    cmd = [sys.executable, str(module_path), "--manifest", str(manifest_path)]
    if args.get("force"):
        cmd.append("--force")
    
    _run_phase(3, "Spatial Initialization", cmd, ipc_mode)
    
    
    # if args.force:
    #     cmd.append("--force")
    # try:
    #     subprocess.run(cmd, check=True)
    # except subprocess.CalledProcessError as e:
    #     print(
    #         f"[!] Pipeline failed at Phase 3 (Spatial Initialization). Exit code: {e.returncode}"
    #     )
    #     sys.exit(e.returncode)
    # if args.get("force"):
    #     cmd.append("--force")
    # result = subprocess.run(cmd)
    # if result.returncode != 0:
    #     raise RuntimeError(f"[!] Pipeline failed at Phase 3 (Spatial Initialization). Exit code: {result.returncode}")






def run_phase4(parent_module_path, manifest_path, args, ipc_mode=False):
    module_path = parent_module_path / "geometry.py"
    cmd = [sys.executable, str(module_path), "--manifest", str(manifest_path)]
    if args.get("force"):
        cmd.append("--force")
    
    _run_phase(4, "Geometry Generation", cmd, ipc_mode)

    # if args.force:
    #     cmd.append("--force")
    # try:
    #     subprocess.run(cmd, check=True)
    # except subprocess.CalledProcessError as e:
    #     print(
    #         f"[!] Pipeline failed at Phase 4 (Geometry Generation). Exit code: {e.returncode}"
    #     )
    #     sys.exit(e.returncode)
    # if args.get("force"):
    #     cmd.append("--force")
    # result = subprocess.run(cmd)
    # if result.returncode != 0:
    #     raise RuntimeError(f"[!] Pipeline failed at Phase 4 (Geometry Generation). Exit code: {result.returncode}")




def run_pipeline_with_args(args: dict, ipc_mode: bool=False):
    base_dir = (WORKSPACE_DIR / args["name"]).resolve()
    capture_dir = base_dir / "01_capture"
    mask_dir = base_dir / "02_masking"
    spatial_dir = base_dir / "03_spatial"
    geometry_dir = base_dir / "04_geometry"

    manifest_path = base_dir / "manifest.json"

    capture_dir.mkdir(parents=True, exist_ok=True)
    mask_dir.mkdir(parents=True, exist_ok=True)
    spatial_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(PROJECT_ROOT / "data" / "input" / args["input"]).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input source not found: {args['input']}")
    
    manifest = {
        "run_name": args["name"],
        "input_source": str(input_path),
        "mode": args.get("mode", "disk"),
        "settings": {
            "requested_fps": args["fps"],
            "blur_threshold": args.get("blur_threshold", 200.0),
            "proxy_width": args.get("proxy_width", 640),
            "jpg_quality": args.get("jpg_quality", 85),
            "max_search": args.get("max_search", 3),
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

    parent_module_path = Path(__file__).parent.parent / "modules"

    send_log(f"Worspace initialized: {base_dir}")
    send_progress(0.0, "[*] Starting Phase 1: Capture")
    run_phase1(parent_module_path, manifest_path, args, ipc_mode)
   # run_phase1(parent_module_path, manifest_path, args)

    send_progress(0.25, "[*] Starting Phase 2: Masking")
    run_phase2(parent_module_path, manifest_path, args, ipc_mode)
 #   run_phase2(parent_module_path, manifest_path, args)

    send_progress(0.50, "[*] Starting Phase 3: Spatial")
    run_phase3(parent_module_path, manifest_path, args, ipc_mode)
   # run_phase3(parent_module_path, manifest_path, args)

    send_progress(0.75, "[*] Starting Phase 4: Geometry")
    run_phase4(parent_module_path, manifest_path, args, ipc_mode)
   # run_phase4(parent_module_path, manifest_path, args)

    send_progress(1.0, "[*] Complete")
    send_done({"run_name": args["name"], "output": str(base_dir)})


def run_ipc_mode():
    send_log("Backend ready")

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
    parser.add_argument("--iou_threshold", type=float, default=0.35)
    parser.add_argument("--drift_limit", type=int, default=200)
    parser.add_argument("--max_yoloe_failures", type=int, default=2)
    parser.add_argument(
        "--yoloe_model_size", type=str, choices=["n", "s", "m", "l", "x"], default="s"
    )

    args = parser.parse_args()

    run_pipeline_with_args(vars(args), ipc_mode=False)

    # # 0.2. Establish Workspace (WORKSPACE_ROOT/[name]/)
    # base_dir = (WORKSPACE_DIR / args.name).resolve()
    # capture_dir = base_dir / "01_capture"
    # mask_dir = base_dir / "02_masking"
    # spatial_dir = base_dir / "03_spatial"
    # geometry_dir = base_dir / "04_geometry"

    # manifest_path = base_dir / "manifest.json"

    # capture_dir.mkdir(parents=True, exist_ok=True)
    # mask_dir.mkdir(parents=True, exist_ok=True)
    # spatial_dir.mkdir(parents=True, exist_ok=True)
    # geometry_dir.mkdir(parents=True, exist_ok=True)

    # input_path = Path(PROJECT_ROOT / "data" / "input" / Path(args.input)).resolve()

    # # If the path provided doesn't exist locally, check data/input/
    # if not input_path.exists():
    #     print(f"[!] Input source not found: {args.input}")
    #     sys.exit(1)

    # # 0.3. Create the Manifest
    # manifest = {
    #     "run_name": args.name,
    #     "input_source": str(input_path),
    #     "mode": args.mode,
    #     "settings": {
    #         "requested_fps": args.fps,
    #         "blur_threshold": args.blur_threshold,
    #         "proxy_width": args.proxy_width,
    #         "jpg_quality": args.jpg_quality,
    #         "max_search": args.max_search,
    #     },
    #     "status": {
    #         "phase": 1,
    #         "completed": [],
    #     },
    #     "paths": {
    #         "run_root": str(base_dir),
    #         "raw_frames": str(capture_dir),
    #         "masked_frames": str(mask_dir),
    #         "spatial": str(spatial_dir),
    #         "geometry": str(geometry_dir),
    #     },
    # }

    # with open(manifest_path, "w") as f:
    #     json.dump(manifest, f, indent=4)

    #print(f"[*] Workspace initialized: {base_dir}")
    #print(f"[*] Mode: {args.mode} | Target FPS: {args.fps}")

    # parent_module_path = Path(__file__).parent.parent / "modules"

    # run_phase1(parent_module_path, manifest_path, args)
    # run_phase2(parent_module_path, manifest_path, args)
    # run_phase3(parent_module_path, manifest_path, args)
    # run_phase4(parent_module_path, manifest_path, args)


if __name__ == "__main__":
    #run_pipeline()
    if len(sys.argv) > 1 and sys.argv[1] == "--ipc":
        run_ipc_mode()
    else:
        run_cli_mode()

