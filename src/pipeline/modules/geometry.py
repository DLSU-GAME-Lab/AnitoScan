from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import time

MODULE_PATH = Path(__file__).resolve()
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent
GS_PATH = PROJECT_ROOT / "vendor" / "2d-gaussian-splatting"

from src.pipeline.core.config import RunCancelled


@dataclass
class GeometryResult:
    geometry_dir: Path
    fused_mesh_path: Path


def run_surface_reconstruction(
    input_2dgs_dir: str | Path,
    output_dir: str | Path,
    train_iterations: int = 15000,
    densify_until_iter: int = 7500,
    opacity_reset_interval: int = 3000,
    force: bool = False,
    progress_cb=None,
    log_cb=None,
    check_cancelled=None,
    is_cancelled=None,
) -> GeometryResult:
    def log(msg: str):
        if log_cb:
            log_cb(msg)
        else:
            print(f"[*] {msg}")

    def progress(val: float, label: str):
        if progress_cb:
            progress_cb(val, label)

    def do_check_cancel():
        if check_cancelled:
            check_cancelled()
        elif is_cancelled and is_cancelled():
            raise RunCancelled("Pipeline cancelled by user during Phase 4 (Geometry)")

    input_data_path = Path(input_2dgs_dir).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    sparse_dir = input_data_path / "sparse" / "0"
    spatial_init_complete = (
        (sparse_dir / "points3D.txt").exists() or (sparse_dir / "points3D.bin").exists()
    ) and (
        (sparse_dir / "cameras.txt").exists() or (sparse_dir / "cameras.bin").exists()
    )

    if not spatial_init_complete:
        raise FileNotFoundError(
            f"Required 2DGS sparse inputs missing in {sparse_dir}. Did Phase 3 (Spatial) complete?"
        )

    target_fused_ply = output_dir / "fused_mesh.ply"

    # --- SKIP LOGIC (CACHED) ---
    if target_fused_ply.exists() and not force:
        log(f"Found existing fused mesh at {target_fused_ply}. Skipping 2DGS training...")
        progress(1.0, "Phase 4: Geometry complete (cached)")
        return GeometryResult(
            geometry_dir=output_dir,
            fused_mesh_path=target_fused_ply,
        )

    gs_model_dir = output_dir / "vanilla_2dgs"
    if force and gs_model_dir.exists():
        shutil.rmtree(gs_model_dir)
    gs_model_dir.mkdir(parents=True, exist_ok=True)

    train_cmd = [
        sys.executable,
        str(GS_PATH / "train.py"),
        "-s", str(input_data_path),
        "-m", str(gs_model_dir),
        "--iterations", str(train_iterations),
        "--densify_from_iter", "500",
        "--densify_until_iter", str(densify_until_iter),
        "--opacity_reset_interval", str(opacity_reset_interval),
        "--white_background",
        "--lambda_dist", "0.0",
        "--lambda_normal", "0.05",
        "--quiet",
    ]

    render_cmd = [
        sys.executable,
        str(GS_PATH / "render.py"),
        "-s", str(input_data_path),
        "-m", str(gs_model_dir),
        "--skip_test",
        "--skip_train",
        "--iteration", str(train_iterations),
    ]

    log(f"Starting 2DGS Training ({train_iterations} iterations)...")
    progress(0.10, "Phase 4: Training 2DGS...")
    start_time = time.perf_counter()

    train_checkpoint_exists = (
        gs_model_dir / "point_cloud" / f"iteration_{train_iterations}"
    ).exists()

    if train_checkpoint_exists and not force:
        log("Found existing training output. Skipping training step...")
    else:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        process = subprocess.Popen(
            train_cmd,
            cwd=str(GS_PATH),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None

        TRAIN_START = 0.10
        TRAIN_END = 0.85
        TRAIN_RANGE = TRAIN_END - TRAIN_START

        for line in process.stdout:
            do_check_cancel()
            match = re.search(r"(\d+)\s*/\s*(\d+)", line)
            if match:
                current = int(match.group(1))
                total = int(match.group(2))
                prog_val = TRAIN_START + (current / total) * TRAIN_RANGE
                progress(prog_val, f"Training {current}/{total} iterations")
            else:
                stripped = line.strip()
                if stripped and not stripped.startswith("("):
                    log(f"[train] {stripped}")

        process.wait()
        if process.returncode != 0:
            raise RuntimeError("Phase 4: 2DGS Training process failed")

    log("Starting Mesh Extraction (TSDF Fusion)...")
    progress(0.85, "Phase 4: Extracting mesh...")
    mesh_output_dir = gs_model_dir / "train" / f"ours_{train_iterations}"

    if mesh_output_dir.exists() and not force and list(mesh_output_dir.rglob("*_post.ply")):
        log("Found existing mesh output. Skipping render meshing...")
    else:
        process = subprocess.Popen(
            render_cmd,
            cwd=str(GS_PATH),
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            do_check_cancel()
            stripped = line.strip()
            if stripped:
                log(f"[render] {stripped}")
        process.wait()
        if process.returncode != 0:
            raise RuntimeError("Phase 4: Meshing process failed")

    if mesh_output_dir.exists():
        possible_meshes = list(mesh_output_dir.rglob("*_post.ply"))
        if possible_meshes:
            shutil.copy2(str(possible_meshes[0]), str(target_fused_ply))
            log(f"Base geometry staged for Phase 5 at: {target_fused_ply}")
        else:
            raise FileNotFoundError(f"No *_post.ply files found in {mesh_output_dir}")
    else:
        raise FileNotFoundError(f"Mesh directory {mesh_output_dir} not found")

    total_time = time.perf_counter() - start_time
    log(f"2DGS Reconstruction Complete. Total Time: {total_time:.2f}s")
    progress(1.0, "Phase 4: Geometry complete")

    return GeometryResult(
        geometry_dir=output_dir,
        fused_mesh_path=target_fused_ply,
    )
