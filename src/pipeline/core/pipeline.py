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

from src.pipeline.core.config import PipelineConfig
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
    """Executes all 5 pipeline phases cleanly in process using PipelineConfig."""
    def log(text: str):
        if log_cb:
            log_cb(text)

    # Instantiate and validate pipeline configuration
    config = PipelineConfig.from_dict(args)
    if not config.input_path.is_absolute():
        config.input_path = (PROJECT_ROOT / "data" / "input" / config.input_path).resolve()

    config.validate(check_path_exists=True)

    base_dir = (WORKSPACE_DIR / config.run_name).resolve()
    capture_dir = base_dir / "01_capture"
    mask_dir = base_dir / "02_masking"
    spatial_dir = base_dir / "03_spatial"
    geometry_dir = base_dir / "04_geometry"
    export_dir = (PROJECT_ROOT / "data" / "output" / config.run_name).resolve()
    manifest_path = base_dir / "manifest.json"

    capture_dir.mkdir(parents=True, exist_ok=True)
    mask_dir.mkdir(parents=True, exist_ok=True)
    spatial_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    # Save initial manifest directly from PipelineConfig
    config.save_manifest(manifest_path)
    log(f"Workspace initialized: {base_dir}")

    force = config.spatial.force or config.export.force

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
        yoloe_model_size=config.masking.yoloe_model_size,
        iou_threshold=config.masking.iou_threshold,
        drift_limit=config.masking.drift_limit,
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
    run_surface_reconstruction(
        manifest_path=manifest_path,
        train_iterations=config.geometry.train_iterations,
        densify_until_iter=config.geometry.densify_until_iter,
        opacity_reset_interval=config.geometry.opacity_reset_interval,
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
        "run_name": config.run_name,
        "workspace": str(base_dir),
        "output": output_obj_path,
    }
