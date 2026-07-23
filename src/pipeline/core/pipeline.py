"""3D Reconstruction Pipeline Execution Orchestrator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Path Resolution
SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent.parent.parent
WORKSPACE_DIR = PROJECT_ROOT / "data" / "runs"
MODULES_DIR = SCRIPT_PATH.parent.parent / "modules"

sys.path.insert(0, str(MODULES_DIR))

from src.pipeline.core.config import ConfigValidationError, PipelineConfig
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
        input_source=config.input_path,
        output_dir=capture_dir,
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
        raw_frames_dir=capture_dir,
        output_dir=mask_dir,
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
    spatial_result = run_spatial_reconstruction(
        masked_frames_dir=mask_dir,
        output_dir=spatial_dir,
        force=force,
        progress_cb=progress_cb,
        log_cb=log_cb,
        is_cancelled=is_cancelled,
    )

    # --- Phase 4: Geometry ---
    log("Starting Phase 4: Geometry")
    geometry_result = run_surface_reconstruction(
        input_2dgs_dir=spatial_result.input_2dgs_dir,
        output_dir=geometry_dir,
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
    quality_preset = getattr(config.export, "quality_preset", "fast")
    export_result = run_export_and_baking(
        fused_mesh_path=geometry_result.fused_mesh_path,
        output_dir=export_dir,
        run_name=config.run_name,
        quality_preset=quality_preset,
        force=force,
        progress_cb=progress_cb,
        log_cb=log_cb,
        is_cancelled=is_cancelled,
    )

    log("Scan Complete")

    return {
        "run_name": config.run_name,
        "workspace": str(base_dir),
        "output": str(export_result.primary_obj_path),
    }


def main() -> None:
    """CLI entrypoint that builds PipelineConfig from args and executes the pipeline."""
    parser = argparse.ArgumentParser(
        description="Run 3D reconstruction pipeline via CLI using PipelineConfig."
    )
    parser.add_argument("--run-name", "-n", required=True, type=str, help="Unique run identifier.")
    parser.add_argument("--input", "-i", required=True, type=str, dest="input_path", help="Input video or image directory.")
    parser.add_argument("--quality", choices=["fast", "medium", "detailed"], default="fast", help="Quality preset.")

    # Processing mode flags
    parser.add_argument("--image", action="store_true", help="Force image processing mode.")
    parser.add_argument("--video", action="store_true", help="Force video processing mode.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing intermediate files/outputs.")

    # Sub-configuration overrides
    parser.add_argument("--minimum-frames", type=int, default=None, help="Minimum required capture frames.")
    parser.add_argument("--blur-threshold", type=float, default=None, help="Blur threshold.")
    parser.add_argument("--proxy-width", type=int, default=None, help="Proxy width.")
    parser.add_argument("--jpg-quality", type=int, default=None, help="JPG quality (1-100).")
    parser.add_argument("--max-search", type=int, default=None, help="Max search distance.")

    parser.add_argument("--iou-threshold", type=float, default=None, help="Masking IoU threshold.")
    parser.add_argument("--drift-limit", type=int, default=None, help="Masking drift limit.")
    parser.add_argument("--yoloe-model-size", choices=["n", "s", "m", "l", "x"], default=None, help="YOLO model size.")

    parser.add_argument("--train-iterations", type=int, default=None, help="Total training iterations.")
    parser.add_argument("--densify-until-iter", type=int, default=None, help="Densify until iteration.")
    parser.add_argument("--opacity-reset-interval", type=int, default=None, help="Opacity reset interval.")

    parsed = parser.parse_args()

    # Omit None entries so PipelineConfig / preset defaults take effect
    args_dict = {k: v for k, v in vars(parsed).items() if v is not None}

    try:
        results = run_pipeline_with_args(args=args_dict, log_cb=print)
        print(f"Pipeline finished successfully: {json.dumps(results, indent=2)}")
    except ConfigValidationError as err:
        print(f"Configuration Error: {err}", file=sys.stderr)
        sys.exit(1)
    except Exception as err:
        print(f"Pipeline Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
