"""3D Reconstruction Pipeline Execution Orchestrator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from src.pipeline.core.config import ConfigValidationError, PipelineConfig, RunCancelled

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parents[3]

PHASES = (
    (1, "Capture", "capture"),
    (2, "Masking", "masking"),
    (3, "Spatial", "spatial"),
    (4, "Geometry", "geometry"),
    (5, "Export", "export"),
)


def _load_phase_functions() -> dict[str, Callable[..., Any]]:
    """Load production phase functions only when an actual run needs them."""
    from src.pipeline.modules.capture import run_capture
    from src.pipeline.modules.export import run_export_and_baking
    from src.pipeline.modules.geometry import run_surface_reconstruction
    from src.pipeline.modules.remove_background import run_remove_background
    from src.pipeline.modules.spatial import run_spatial_reconstruction

    return {
        "capture": run_capture,
        "masking": run_remove_background,
        "spatial": run_spatial_reconstruction,
        "geometry": run_surface_reconstruction,
        "export": run_export_and_baking,
    }


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".json.tmp")
    with open(temporary_path, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    temporary_path.replace(path)


def _string_paths(paths: list[Path]) -> list[str]:
    return [str(path) for path in paths]


def run_pipeline_with_args(
    args: dict[str, Any],
    progress_cb=None,
    log_cb=None,
    action_cb=None,
    is_cancelled=None,
    phase_started_cb=None,
    phase_completed_cb=None,
    workspace_ready_cb=None,
    phase_functions: dict[str, Callable[..., Any]] | None = None,
    project_root: str | Path | None = None,
) -> dict[str, str]:
    """Execute all phases while owning workspace, manifest, and phase lifecycle."""
    root = Path(project_root).resolve() if project_root is not None else PROJECT_ROOT

    def log(text: str) -> None:
        if log_cb:
            log_cb(text)

    def check_cancelled() -> None:
        if is_cancelled and is_cancelled():
            raise RunCancelled("Pipeline cancelled by user request")

    config = PipelineConfig.from_dict(args)
    if not config.input_path.is_absolute():
        config.input_path = (root / "data" / "input" / config.input_path).resolve()

    # Validation intentionally precedes all workspace and output mutations.
    config.validate(check_path_exists=True)

    base_dir = (root / "data" / "runs" / config.run_name).resolve()
    capture_dir = base_dir / "01_capture"
    mask_dir = base_dir / "02_masking"
    spatial_dir = base_dir / "03_spatial"
    geometry_dir = base_dir / "04_geometry"
    export_dir = (root / "data" / "output" / config.run_name).resolve()
    manifest_path = base_dir / "manifest.json"

    paths = {
        "run_root": str(base_dir),
        "capture": str(capture_dir),
        "masking": str(mask_dir),
        "spatial": str(spatial_dir),
        "geometry": str(geometry_dir),
        "output": str(export_dir),
        "manifest": str(manifest_path),
    }
    manifest: dict[str, Any] = {
        "run_name": config.run_name,
        "configuration": config.to_dict(),
        "status": {
            "state": "running",
            "phase": 0,
            "completed": [],
            "current_phase": None,
            "completed_phases": [],
        },
        "paths": paths,
        "artifacts": {},
        "output": None,
    }

    for directory in (capture_dir, mask_dir, spatial_dir, geometry_dir, export_dir):
        directory.mkdir(parents=True, exist_ok=True)
    _write_manifest(manifest_path, manifest)
    if workspace_ready_cb:
        workspace_ready_cb(config.run_name, str(base_dir))
    log(f"Workspace initialized: {base_dir}")

    functions = phase_functions
    force = config.spatial.force or config.export.force

    def run_phase(
        phase: int,
        label: str,
        function: Callable[..., Any],
        artifact_builder: Callable[[Any], dict[str, Any]],
        **kwargs: Any,
    ) -> Any:
        check_cancelled()
        manifest["status"]["phase"] = phase
        manifest["status"]["current_phase"] = phase
        _write_manifest(manifest_path, manifest)
        log(f"Starting Phase {phase}: {label}")
        if phase_started_cb:
            phase_started_cb(phase, label)

        def phase_progress(value: float, progress_label: str | None = None) -> None:
            check_cancelled()
            if progress_cb:
                progress_cb(phase, value, progress_label)

        result = function(
            **kwargs,
            progress_cb=phase_progress,
            log_cb=log_cb,
            check_cancelled=check_cancelled,
        )
        check_cancelled()
        manifest["artifacts"][PHASES[phase - 1][2]] = artifact_builder(result)
        manifest["status"]["completed"].append(phase)
        manifest["status"]["completed_phases"].append(phase)
        manifest["status"]["current_phase"] = None
        _write_manifest(manifest_path, manifest)
        if phase_completed_cb:
            phase_completed_cb(phase)
        return result

    try:
        check_cancelled()
        functions = functions if functions is not None else _load_phase_functions()
        capture_result = run_phase(
            1,
            "Capture",
            functions["capture"],
            lambda result: {
                "output_dir": str(result.output_dir),
                "frames": _string_paths(result.extracted_frames),
                "frame_count": result.frame_count,
                "source_type": result.source_type,
            },
            input_source=config.input_path,
            output_dir=capture_dir,
            minimum_frames=config.capture.minimum_frames,
            is_image_mode=bool(args.get("image", False)),
            is_video_mode=bool(args.get("video", False)),
            force=force,
        )
        masking_result = run_phase(
            2,
            "Masking",
            functions["masking"],
            lambda result: {
                "output_dir": str(result.output_dir),
                "masks": _string_paths(result.mask_paths),
                "mask_count": result.mask_count,
            },
            raw_frames_dir=capture_result.output_dir,
            output_dir=mask_dir,
            minimum_frames=config.capture.minimum_frames,
            yoloe_model_size=config.masking.yoloe_model_size,
            iou_threshold=config.masking.iou_threshold,
            drift_limit=config.masking.drift_limit,
            force=force,
            action_cb=action_cb,
        )
        spatial_result = run_phase(
            3,
            "Spatial",
            functions["spatial"],
            lambda result: {
                "spatial_dir": str(result.spatial_dir),
                "input_2dgs_dir": str(result.input_2dgs_dir),
                "transforms_json": str(result.transforms_json_path),
                "init_points_ply": str(result.init_points_ply_path),
                "registered_cameras_count": result.registered_cameras_count,
            },
            masked_frames_dir=masking_result.output_dir,
            output_dir=spatial_dir,
            force=force,
        )
        geometry_result = run_phase(
            4,
            "Geometry",
            functions["geometry"],
            lambda result: {
                "geometry_dir": str(result.geometry_dir),
                "fused_mesh": str(result.fused_mesh_path),
            },
            input_2dgs_dir=spatial_result.input_2dgs_dir,
            output_dir=geometry_dir,
            train_iterations=config.geometry.train_iterations,
            densify_until_iter=config.geometry.densify_until_iter,
            opacity_reset_interval=config.geometry.opacity_reset_interval,
            force=force,
        )
        export_result = run_phase(
            5,
            "Export",
            functions["export"],
            lambda result: {
                "export_dir": str(result.export_dir),
                "primary_obj": str(result.primary_obj_path),
                "texture": str(result.texture_path) if result.texture_path else None,
            },
            fused_mesh_path=geometry_result.fused_mesh_path,
            output_dir=export_dir,
            run_name=config.run_name,
            quality_preset=config.quality,
            force=force,
        )

        output_path = str(export_result.primary_obj_path)
        manifest["status"].update(
            state="completed", current_phase=None, error=None
        )
        manifest["output"] = output_path
        manifest["artifacts"]["primary_output"] = output_path
        _write_manifest(manifest_path, manifest)
        log("Scan Complete")
        return {
            "run_name": config.run_name,
            "workspace": str(base_dir),
            "output": output_path,
        }
    except RunCancelled as exception:
        manifest["status"].update(state="cancelled", error=str(exception))
        _write_manifest(manifest_path, manifest)
        raise
    except Exception as exception:
        manifest["status"].update(state="failed", error=str(exception))
        _write_manifest(manifest_path, manifest)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run 3D reconstruction pipeline via CLI using PipelineConfig."
    )
    parser.add_argument("--run-name", "-n", required=True, type=str)
    parser.add_argument("--input", "-i", required=True, type=str, dest="input_path")
    parser.add_argument(
        "--quality", choices=["fast", "medium", "detailed"], default="fast"
    )
    parser.add_argument("--image", action="store_true")
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--minimum-frames", type=int, default=None)
    parser.add_argument("--blur-threshold", type=float, default=None)
    parser.add_argument("--proxy-width", type=int, default=None)
    parser.add_argument("--jpg-quality", type=int, default=None)
    parser.add_argument("--max-search", type=int, default=None)
    parser.add_argument("--iou-threshold", type=float, default=None)
    parser.add_argument("--drift-limit", type=int, default=None)
    parser.add_argument("--yoloe-model-size", choices=["n", "s", "m", "l", "x"], default=None)
    parser.add_argument("--train-iterations", type=int, default=None)
    parser.add_argument("--densify-until-iter", type=int, default=None)
    parser.add_argument("--opacity-reset-interval", type=int, default=None)

    parsed = parser.parse_args()
    args_dict = {key: value for key, value in vars(parsed).items() if value is not None}
    try:
        results = run_pipeline_with_args(args=args_dict, log_cb=print)
        print(f"Pipeline finished successfully: {json.dumps(results, indent=2)}")
    except ConfigValidationError as exception:
        print(f"Configuration Error: {exception}", file=sys.stderr)
        sys.exit(1)
    except Exception as exception:
        print(f"Pipeline Error: {exception}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
