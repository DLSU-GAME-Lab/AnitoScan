import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d
import pycolmap
from scipy.spatial.transform import Rotation as R

MODULE_PATH = Path(__file__).resolve()
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent
GS_PATH = PROJECT_ROOT / "vendor" / "2d-gaussian-splatting"


def run_bundle_adjustment(image_dir: Path, output_dir: Path, log_cb=None):
    def log(msg: str):
        if log_cb:
            log_cb(msg)
        else:
            print(f"[*] {msg}")

    log("Starting Geometric Bundle Adjustment...")
    database_path = output_dir / "database.db"
    if database_path.exists():
        database_path.unlink()

    log("Extracting SIFT features...")
    reader_options = pycolmap.ImageReaderOptions()
    reader_options.camera_model = "PINHOLE"

    pycolmap.extract_features(
        database_path,
        image_dir,
        camera_mode=pycolmap.CameraMode.SINGLE,
        reader_options=reader_options,
    )

    log("Matching features...")
    pycolmap.match_exhaustive(database_path)

    log("Running Ceres Solver (Bundle Adjustment)...")
    maps = pycolmap.incremental_mapping(database_path, image_dir, output_dir)

    if not maps or len(maps) == 0:
        raise RuntimeError("Bundle Adjustment failed to converge. The solver couldn't find enough matches.")

    map_values = list(maps.values()) if isinstance(maps, dict) else list(maps)
    best_map = max(map_values, key=lambda m: len(m.images))

    log(f"Bundle Adjustment complete. Registered {len(best_map.images)} cameras.")

    total_input_images = len(list(image_dir.glob("*")))
    if len(best_map.images) < max(3, 0.5 * total_input_images):
        raise RuntimeError(
            f"Bundle Adjustment registered only {len(best_map.images)}/{total_input_images} images."
        )

    best_map.write_text(str(output_dir))
    return output_dir


def run_surface_reconstruction(
    manifest_path: str | Path,
    train_iterations: int,
    densify_until_iter: int,
    opacity_reset_interval: int,
    force: bool = False,
    progress_cb=None,
    log_cb=None,
    is_cancelled=None,
):
    def log(msg: str):
        if log_cb:
            log_cb(msg)
        else:
            print(f"[*] {msg}")

    def progress(val: float, label: str):
        if progress_cb:
            progress_cb(4, val, label)

    def check_cancel():
        if is_cancelled and is_cancelled():
            raise RuntimeError("Pipeline cancelled by user during Phase 4 (Geometry)")

    manifest_path = Path(manifest_path).resolve()
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    output_dir = Path(manifest["paths"]["geometry"])
    output_dir.mkdir(parents=True, exist_ok=True)

    input_data_path = output_dir / "input_for_2dgs"
    sparse_dir = input_data_path / "sparse" / "0"
    image_dir = input_data_path / "images"

    spatial_init_complete = (sparse_dir / "points3D.txt").exists() and (
        sparse_dir / "cameras.txt"
    ).exists()

    if spatial_init_complete and not force:
        log(f"Found existing spatial initialization in {input_data_path}. Skipping prep...")
    else:
        if force and input_data_path.exists():
            shutil.rmtree(input_data_path)

        sparse_dir.mkdir(parents=True, exist_ok=True)
        image_dir.mkdir(parents=True, exist_ok=True)

        log("Prepping images for Geometric Solver...")
        progress(0.0, "Phase 4: Preparing images...")

        start_time_pycolmap = time.perf_counter()
        masked_frames = list(Path(manifest["paths"]["masked_frames"]).glob("*.png"))
        total_frames = len(masked_frames)

        for i, original_png_path in enumerate(masked_frames):
            check_cancel()
            target_image_path = image_dir / original_png_path.name
            img_rgba = cv2.imread(str(original_png_path), cv2.IMREAD_UNCHANGED)

            if img_rgba is not None and img_rgba.shape[2] == 4:
                bgr = img_rgba[:, :, :3].astype(np.float32)
                alpha = img_rgba[:, :, 3].astype(np.float32) / 255.0
                alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
                alpha_3c = np.expand_dims(alpha, axis=2)

                white_bg = np.ones_like(bgr) * 255.0
                composited_bgr = (bgr * alpha_3c) + (white_bg * (1.0 - alpha_3c))
                cv2.imwrite(str(target_image_path), composited_bgr.astype(np.uint8))

            if total_frames > 0 and i % 10 == 0:
                progress(
                    (i / total_frames) * 0.15,
                    f"Preparing image {i + 1} of {total_frames}",
                )

        log("Started running bundle adjustment...")
        progress(0.15, "Phase 4: Running Bundle Adjustment...")
        run_bundle_adjustment(image_dir, sparse_dir, log_cb=log)

        total_time_pycolmap = time.perf_counter() - start_time_pycolmap
        log(f"Spatial Initialization via pycolmap Complete. Time: {total_time_pycolmap:.2f}s")

    gs_model_dir = output_dir / "vanilla_2dgs"
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
        "500",
        "--densify_until_iter",
        str(densify_until_iter),
        "--opacity_reset_interval",
        str(opacity_reset_interval),
        "--white_background",
        "--lambda_dist",
        "0.0",
        "--lambda_normal",
        "0.05",
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
        "--skip_train",
        "--iteration",
        str(train_iterations),
    ]

    log(f"Starting 2DGS Training ({train_iterations} iterations)...")
    progress(0.30, "Phase 4: Training 2DGS...")
    start_time = time.perf_counter()

    train_checkpoint_exists = (
        gs_model_dir / "point_cloud" / f"iteration_{train_iterations}"
    ).exists()

    if train_checkpoint_exists and not force:
        log("Found existing training output. Skipping training...")
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

        TRAIN_START = 0.30
        TRAIN_END = 0.85
        TRAIN_RANGE = TRAIN_END - TRAIN_START

        for line in process.stdout:
            check_cancel()
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

    if mesh_output_dir.exists() and not force:
        log("Found existing mesh output. Skipping meshing...")
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
            check_cancel()
            stripped = line.strip()
            if stripped:
                log(f"[render] {stripped}")
        process.wait()
        if process.returncode != 0:
            raise RuntimeError("Phase 4: Meshing process failed")

    target_fused_ply = output_dir / "fused_mesh.ply"

    if mesh_output_dir.exists():
        possible_meshes = list(mesh_output_dir.rglob("*_post.ply"))
        if possible_meshes:
            shutil.copy2(str(possible_meshes[0]), str(target_fused_ply))
            log(f"Base geometry staged for Phase 5 at: {target_fused_ply}")
        else:
            raise FileNotFoundError(f"No *_post.ply files found in {mesh_output_dir}")
    else:
        raise FileNotFoundError(f"Mesh directory {mesh_output_dir} not found")

    manifest["status"]["phase"] = 4
    if "geometry" not in manifest["status"]["completed"]:
        manifest["status"]["completed"].append("geometry")

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    total_time = time.perf_counter() - start_time
    log(f"2DGS Reconstruction Complete. Total Time: {total_time:.2f}s")
    progress(1.0, "Phase 4: Geometry complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--train_iterations", type=int, default=15000)
    parser.add_argument("--densify_until_iter", type=int, default=7500)
    parser.add_argument("--opacity_reset_interval", type=int, default=3000)
    parser.add_argument("--ipc", action="store_true")

    args = parser.parse_args()

    run_surface_reconstruction(
        args.manifest,
        train_iterations=args.train_iterations,
        densify_until_iter=args.densify_until_iter,
        opacity_reset_interval=args.opacity_reset_interval,
        force=args.force,
    )
