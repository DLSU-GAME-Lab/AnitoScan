import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

core_path = str(Path(__file__).resolve().parent.parent / "core")
sys.path.insert(0, core_path)

from benchmark import append_failed_phase_benchmark, append_phase_benchmark
from log import log_error, log_info, log_progress, set_ipc_mode, set_phase
from manifest import load_manifest, update_manifest

# =====================================================================
# DIRECTORY RESOLUTION
# =====================================================================
MODULE_PATH = Path(__file__).resolve()  # /src/pipeline/modules/geometry.py
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent
GS_PATH = PROJECT_ROOT / "vendor" / "2d-gaussian-splatting"  # Vendor Path for 2DGS
TRAIN_END = 0.85  # training ends at 85% and meshing begins for progress logging


def run_surface_reconstruction(
    manifest_path_string,
    train_iterations,
    densify_until_iter,
    opacity_reset_interval,
    force=False,
    ipc_mode=False
):
    set_ipc_mode(ipc_mode)
    set_phase(4)

    manifest_path, manifest = load_manifest(manifest_path_string)
    phase_start = time.perf_counter()

    output_dir = Path(manifest["paths"]["geometry"])
    output_dir.mkdir(parents=True, exist_ok=True)

    input_data_path = Path(manifest["paths"]["spatial"])
    sparse_dir = input_data_path / "sparse" / "0"
    gs_model_dir = output_dir / "vanilla_2dgs"
    benchmark_settings = {
        "force": force,
        "train_iterations": train_iterations,
        "densify_until_iter": densify_until_iter,
        "opacity_reset_interval": opacity_reset_interval,
    }
    benchmark_metrics = {
        "training_skipped": False,
        "meshing_skipped": False,
        "train_checkpoint_exists": False,
        "training_iteration": 0,
        "candidate_meshes": 0,
        "fused_mesh_bytes": 0,
    }
    benchmark_paths = {
        "input_data_path": input_data_path,
        "sparse_dir": sparse_dir,
        "gs_model_dir": gs_model_dir,
    }

    if not (sparse_dir / "points3D.txt").exists():
        error = FileNotFoundError(f"Spatial initialization missing in {input_data_path}. Run Phase 3 first.")
        append_failed_phase_benchmark(
            manifest,
            4,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        raise error

    if force and gs_model_dir.exists():
        shutil.rmtree(gs_model_dir)
    gs_model_dir.mkdir(parents=True, exist_ok=True)

    train_cmd = [
        sys.executable,
        str(GS_PATH / "train.py"),
        "-s",
        str(input_data_path),
        "-m",
        str(gs_model_dir),
        "--iterations",
        str(train_iterations),
        "--densify_from_iter",
        "500",  # default is 500
        "--densify_until_iter",
        str(densify_until_iter),
        "--opacity_reset_interval",
        str(opacity_reset_interval),
        "--white_background",
        "--lambda_dist",
        "0.0",  # default is 0.0
        "--lambda_normal",
        "0.05",  # default is 0.05
        "--quiet",
    ]

    render_cmd = [
        sys.executable,
        str(GS_PATH / "render.py"),
        "-s",
        str(input_data_path),
        "-m",
        str(gs_model_dir),
        "--skip_test",
        "--skip_train",  # Only interested in the mesh
        "--iteration",
        str(train_iterations),
    ]

    log_info(f"Starting 2DGS Training ({train_iterations} iterations)...")
    log_progress(0, "Phase 4: Training 2DGS...")
    start_time = time.perf_counter()

    train_checkpoint_exists = (
        gs_model_dir / "point_cloud" / f"iteration_{train_iterations}"
    ).exists()
    benchmark_metrics["train_checkpoint_exists"] = train_checkpoint_exists

    training_skipped = False
    if train_checkpoint_exists and not force:
        training_skipped = True
        benchmark_metrics["training_skipped"] = training_skipped
        log_info("Found existing training output. Skipping training...")
    else:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        try:
            process = subprocess.Popen(
                train_cmd, cwd=str(GS_PATH), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
        except (OSError, ValueError) as error:
            append_failed_phase_benchmark(
                manifest,
                4,
                start_time=phase_start,
                settings=benchmark_settings,
                metrics=benchmark_metrics,
                paths=benchmark_paths,
                error=error,
            )
            raise
        assert process.stdout is not None

        for line in process.stdout:
            line = line.rstrip()
            match = re.search(r'(\d+)\s*/\s*(\d+)', line)
            if match:
                current = int(match.group(1))
                total = int(match.group(2))
                benchmark_metrics["training_iteration"] = current
                progress = (current / total) * TRAIN_END
                log_progress(progress, f"Training {current}/{total} iterations")
            else:
                stripped = line.strip()
                if stripped and not stripped.startswith("("):
                    log_info(f"\r[train] {stripped}")

        process.wait()
        if process.returncode != 0:
            error = RuntimeError("Phase 4: Training failed")
            benchmark_metrics["training_return_code"] = process.returncode
            append_failed_phase_benchmark(
                manifest,
                4,
                start_time=phase_start,
                settings=benchmark_settings,
                metrics=benchmark_metrics,
                paths=benchmark_paths,
                error=error,
            )
            raise error

    # 6. Rendering / TSDF Fusion
    log_info("Starting Mesh Extraction (TSDF Fusion)...")
    log_progress(TRAIN_END, "Phase 4: Extracting mesh...")
    mesh_output_dir = gs_model_dir / "train" / f"ours_{train_iterations}"
    benchmark_paths["mesh_output_dir"] = mesh_output_dir

    meshing_skipped = False
    if mesh_output_dir.exists() and not force:
        meshing_skipped = True
        benchmark_metrics["meshing_skipped"] = meshing_skipped
        log_info("Found existing mesh output. Skipping meshing...")
    else:
        try:
            process = subprocess.Popen(
                render_cmd, cwd=str(GS_PATH), env=os.environ.copy(),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
        except (OSError, ValueError) as error:
            append_failed_phase_benchmark(
                manifest,
                4,
                start_time=phase_start,
                settings=benchmark_settings,
                metrics=benchmark_metrics,
                paths=benchmark_paths,
                error=error,
            )
            raise
        assert process.stdout is not None
        for line in process.stdout:
            stripped = line.rstrip()
            if stripped:
                log_info(f"[render] {stripped}")
        process.wait()
        if process.returncode != 0:
            error = RuntimeError("Phase 4: Meshing failed")
            benchmark_metrics["meshing_return_code"] = process.returncode
            append_failed_phase_benchmark(
                manifest,
                4,
                start_time=phase_start,
                settings=benchmark_settings,
                metrics=benchmark_metrics,
                paths=benchmark_paths,
                error=error,
            )
            raise error

    # 7. Final Stage: Expose PLY to the workspace root for Phase 5
    target_fused_ply = output_dir / "fused_mesh.ply"

    if not mesh_output_dir.exists():
        error = FileNotFoundError(f"Mesh directory {mesh_output_dir} not found.")
        append_failed_phase_benchmark(
            manifest,
            4,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        raise error

    possible_meshes = list(mesh_output_dir.rglob("*_post.ply"))
    benchmark_metrics["candidate_meshes"] = len(possible_meshes)
    if not possible_meshes:
        error = FileNotFoundError(f"No *_post.ply files found in {mesh_output_dir}.")
        append_failed_phase_benchmark(
            manifest,
            4,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        raise error

    best_mesh = possible_meshes[0]
    benchmark_paths["source_mesh"] = best_mesh
    try:
        shutil.copy2(str(best_mesh), str(target_fused_ply))
    except OSError as error:
        append_failed_phase_benchmark(
            manifest,
            4,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        raise
    benchmark_paths["fused_mesh"] = target_fused_ply
    benchmark_metrics["fused_mesh_bytes"] = target_fused_ply.stat().st_size if target_fused_ply.exists() else 0
    log_info(f"Base geometry staged for Phase 5 at: {target_fused_ply}")

    update_manifest(manifest_path, manifest, phase=4)

    total_time = time.perf_counter() - start_time
    append_phase_benchmark(
        manifest,
        4,
        status="completed",
        skipped=training_skipped and meshing_skipped,
        duration_seconds=total_time,
        settings={
            "force": force,
            "train_iterations": train_iterations,
            "densify_until_iter": densify_until_iter,
            "opacity_reset_interval": opacity_reset_interval,
        },
        metrics={
            **benchmark_metrics,
            "training_skipped": training_skipped,
            "meshing_skipped": meshing_skipped,
            "train_checkpoint_exists": train_checkpoint_exists,
            "candidate_meshes": len(possible_meshes),
            "fused_mesh_bytes": target_fused_ply.stat().st_size if target_fused_ply.exists() else 0,
        },
        paths=benchmark_paths,
    )

    log_info(f"2DGS Reconstruction Complete. Saved to: {output_dir}")
    log_info(f"Total Time: {total_time:.2f}s")
    log_progress(1.0, "Phase 4: Geometry complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True, help="Path to project manifest.json")
    parser.add_argument("--force", action="store_true", help="Overwrite existing geometry data")
    parser.add_argument("--train_iterations", type=int, default=15000)
    parser.add_argument("--densify_until_iter", type=int, default=7500)
    parser.add_argument("--opacity_reset_interval", type=int, default=3000)
    parser.add_argument("--ipc", action="store_true")

    args = parser.parse_args()

    try:
        run_surface_reconstruction(
            args.manifest,
            train_iterations=args.train_iterations,
            densify_until_iter=args.densify_until_iter,
            opacity_reset_interval=args.opacity_reset_interval,
            force=args.force,
            ipc_mode=args.ipc
        )
    except (RuntimeError, ValueError, OSError) as error:
        log_error(str(error))
        sys.exit(1)
