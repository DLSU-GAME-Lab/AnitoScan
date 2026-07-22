"""3D Reconstruction Pipeline Execution Orchestrator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Path Resolution
SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent.parent.parent
WORKSPACE_DIR = PROJECT_ROOT / "data" / "runs"
MODULES_DIR = SCRIPT_PATH.parent.parent / "modules"

sys.path.insert(0, str(MODULES_DIR))

from capture import run_capture
from export import run_export_and_baking
from geometry import run_surface_reconstruction
from remove_background import run_remove_background
from spatial import run_spatial_reconstruction


def run_pipeline_with_args(
    args: dict,
    progress_cb=None,
    log_cb=None,
    action_cb=None,
    is_cancelled=None,
) -> dict[str, str]:
    """
    Executes all 5 pipeline phases cleanly in process, passing down
    logging, progress, action, and cancellation hooks.
    """
    def log(text: str):
        if log_cb:
            log_cb(text)

    run_name = args.get("run_name") or args.get("name") or ""
    input_str = args.get("input") or ""

    base_dir = (WORKSPACE_DIR / run_name).resolve()
    capture_dir = base_dir / "01_capture"
    mask_dir = base_dir / "02_masking"
    spatial_dir = base_dir / "03_spatial"
    geometry_dir = base_dir / "04_geometry"
    export_dir = (PROJECT_ROOT / "data" / "output" / run_name).resolve()
    manifest_path = base_dir / "manifest.json"

    capture_dir.mkdir(parents=True, exist_ok=True)
    mask_dir.mkdir(parents=True, exist_ok=True)
    spatial_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(PROJECT_ROOT / "data" / "input" / input_str).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input source not found: {input_path}")

    manifest = {
        "run_name": run_name,
        "input_source": str(input_path),
        "mode": args.get("mode", "disk"),
        "settings": {
            "minimum_frames": args.get("minimum_frames", 45),
            "blur_threshold": args.get("blur_threshold", 200.0),
            "proxy_width": args.get("proxy_width", 640.0),
            "jpg_quality": args.get("jpg_quality", 85),
            "max_search": args.get("max_search", 3),
            "quality": args.get("quality", "fast"),
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

    log(f"Workspace initialized: {base_dir}")

    force = bool(args.get("force", False))

    # --- Phase 1: Capture ---
    log("Starting Phase 1: Capture")
    run_capture(
        manifest_path=manifest_path,
        is_image_mode=bool(args.get("image", False)),
        is_video_mode=bool(args.get("video", False)),
        force=force,
        progress_cb=progress_cb,
        log_cb=log_cb,
        is_cancelled=is_cancelled,
    )

    # --- Phase 2: Masking ---
    log("Starting Phase 2: Masking")
    run_remove_background(
        manifest_path=manifest_path,
        yoloe_model_size=args.get("yoloe_model_size", "s"),
        iou_threshold=float(args.get("iou_threshold", 0.50)),
        drift_limit=int(args.get("drift_limit", 200)),
        force=force,
        action_cb=action_cb,
        progress_cb=progress_cb,
        log_cb=log_cb,
        is_cancelled=is_cancelled,
    )

    # --- Phase 3: Spatial ---
    log("Starting Phase 3: Spatial")
    run_spatial_reconstruction(
        manifest_path=manifest_path,
        force=force,
        progress_cb=progress_cb,
        log_cb=log_cb,
        is_cancelled=is_cancelled,
    )

    # --- Phase 4: Geometry ---
    log("Starting Phase 4: Geometry")
    quality = args.get("quality", "fast")
    if quality == "fast":
        train_iters, densify, opacity = 7000, 5000, 1000
    elif quality == "medium":
        train_iters, densify, opacity = 15000, 7500, 3000
    else:
        train_iters, densify, opacity = 30000, 15000, 3000

    run_surface_reconstruction(
        manifest_path=manifest_path,
        train_iterations=train_iters,
        densify_until_iter=densify,
        opacity_reset_interval=opacity,
        force=force,
        progress_cb=progress_cb,
        log_cb=log_cb,
        is_cancelled=is_cancelled,
    )

    # --- Phase 5: Export ---
    log("Starting Phase 5: Export")
    output_obj_path = run_export_and_baking(
        manifest_path=manifest_path,
        force=force,
        progress_cb=progress_cb,
        log_cb=log_cb,
        is_cancelled=is_cancelled,
    )

    log("Scan Complete")

    return {
        "run_name": run_name,
        "workspace": str(base_dir),
        "output": output_obj_path,
    }
