import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
import re
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d
import pycolmap
from scipy.spatial.transform import Rotation as R


core_path = str(Path(__file__).resolve().parent.parent / "core")
sys.path.insert(0, core_path)

from ipc import send_log, send_progress, status_update, status_error

# =====================================================================
# DIRECTORY RESOLUTION
# =====================================================================
MODULE_PATH = Path(__file__).resolve()  # /src/pipeline/modules/geometry.py
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent

# Vendor Paths for 2DGS
GS_PATH = PROJECT_ROOT / "vendor" / "2d-gaussian-splatting"


def run_bundle_adjustment(image_dir: Path, output_dir: Path):
    """
    Runs a mathematically rigorous Bundle Adjustment pass using pycolmap
    to generate sub-pixel perfect camera poses and a sparse feature cloud.
    """
    status_update("Starting Geometric Bundle Adjustment...")
    database_path = output_dir / "database.db"
    if database_path.exists():
        database_path.unlink()  # Start fresh

    # 1. Feature Extraction (API FIX APPLIED HERE)
    status_update("Extracting SIFT features...")

    # Initialize the specific reader options object required by the new API
    reader_options = pycolmap.ImageReaderOptions()  # type: ignore
    reader_options.camera_model = "PINHOLE"

    pycolmap.extract_features(  # type: ignore
        database_path,
        image_dir,
        camera_mode=pycolmap.CameraMode.SINGLE,  # type: ignore
        reader_options=reader_options,
    )

    # 2. Feature Matching (Building the observation tracks)
    status_update("Matching features...")
    pycolmap.match_exhaustive(database_path)  # type: ignore

    # 3. Incremental Mapping & Bundle Adjustment (Ceres Solver)
    status_update("Running Ceres Solver (Bundle Adjustment)...")
    maps = pycolmap.incremental_mapping(database_path, image_dir, output_dir)  # type: ignore

    # Because pycolmap can technically return multiple disjoint maps,
    # we check if any maps were created, and extract the largest one (index 0)
    if not maps or len(maps) == 0:
        status_error("Bundle Adjustment failed to converge. The solver couldn't find enough matches.")
        sys.exit(1)

    # PyCOLMAP returns a dictionary in newer versions, where the largest map is usually key 0
    # or it returns a list. We will safely grab the first/largest one.
    
    # status_update(f"Bundle Adjustment complete. Registered {len(best_map.images)} cameras.")
    map_values = list(maps.values()) if isinstance(maps, dict) else list(maps)
    best_map = max(map_values, key=lambda m: len(m.images))

    status_update(f"Bundle Adjustment complete. Registered {len(best_map.images)} cameras.")

    total_input_images = len(list(image_dir.glob("*")))
    if len(best_map.images) < max(3, 0.5 * total_input_images):
        status_error(
            f"Bundle Adjustment only registered {len(best_map.images)}/{total_input_images} images "
            "in the largest reconstructed map. Scene may lack sufficient overlap/texture."
        )   
        sys.exit(1)

    # Export to the raw text format 2DGS expects
    best_map.write_text(str(output_dir))
    return output_dir


def export_to_2dgs_format(manifest):
    """
    Bridges MASt3R output from spatial.py to the COLMAP format required by
    train.py and render.py.
    """
    spatial_dir = Path(manifest["paths"]["spatial"])
    transforms_path = spatial_dir / "transforms.json"
    point_cloud_path = spatial_dir / "init_points.ply"

    # The 'source_path' (-s) for train.py/render.py
    output_dir = Path(manifest["paths"]["geometry"])
    input_dir_2dgs = output_dir / "input_for_2dgs"
    sparse_dir = input_dir_2dgs / "sparse" / "0"
    image_dir = input_dir_2dgs / "images"

    sparse_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    if not transforms_path.exists():
        status_error(f"{transforms_path} not found. Run spatial.py first.")
        sys.exit(1)

    if not point_cloud_path.exists():
        status_error(f"{point_cloud_path} not found.")
        sys.exit(1)

    # 1. PRE-CALCULATE CENTER AND SCALE
    # We must do this first so the cameras and points match
    pcd = o3d.io.read_point_cloud(str(point_cloud_path))
    if pcd.is_empty():
        status_error("Point cloud is empty.")
        sys.exit(1)

    center = pcd.get_center()
    max_bound = pcd.get_max_bound()
    min_bound = pcd.get_min_bound()
    scale = np.max(max_bound - min_bound)

    # Apply to Point Cloud immediately
    pcd.translate(-center)
    pcd.scale(1.0 / scale, center=(0, 0, 0))

    with open(transforms_path, "r") as f:
        transforms = json.load(f)

    # 2. Write cameras.txt
    with open(sparse_dir / "cameras.txt", "w") as f:
        f.write("# Camera list with one line per camera: \n")
        f.write("# CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n")
        for i, frame in enumerate(transforms["frames"]):
            W = frame["w"]
            H = frame["h"]

            # Calculate the scale factor from MASt3R's 512 internal inference size up to full-res
            # Use whichever side MASt3R maps to its maximum size setting
            base_inference_dim = 512
            scale_factor = max(W, H) / base_inference_dim

            true_focal = frame["focal_length"] * scale_factor

            # Scale up the custom principal points up to full resolution
            true_cx = frame["cx"] * scale_factor
            true_cy = frame["cy"] * scale_factor

            fov_x = 2 * math.atan(W / (2 * true_focal)) * (180 / math.pi)
            status_update(f"Camera {i}: Res {W}x{H} | Focal {true_focal:.2f} | FoV {fov_x:.2f}°")

            # CAMERA_ID PINHOLE WIDTH HEIGHT fx fy cx cy
            f.write(
                f"{i + 1} PINHOLE {W} {H} {true_focal} {true_focal} {true_cx} {true_cy}\n"
            )

    # 3. Write images.txt and INJECT PNGs
    status_update("Processing images and copying full-res Alpha Channels...")
    with open(sparse_dir / "images.txt", "w") as f:
        f.write("# Image list with two lines per image\n")
        f.write("# IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n")

        for i, frame in enumerate(transforms["frames"]):
            c2w = np.array(frame["transform_matrix"])

            # 1. Apply the center/scale shift to the position
            c2w[:3, 3] = (c2w[:3, 3] - center) / scale

            # 2. Convert Camera-to-World down to World-to-Camera
            w2c = np.linalg.inv(c2w)

            rot_mat = w2c[:3, :3]
            tvec = w2c[:3, 3]

            # 3. Convert to Quaternion
            quat = R.from_matrix(rot_mat).as_quat()
            colmap_quat = [quat[3], quat[0], quat[1], quat[2]]

            jpg_name = Path(frame["file_path"]).name
            png_name = Path(jpg_name).stem + ".png"

            f.write(
                f"{i + 1} {' '.join(map(str, colmap_quat))} {' '.join(map(str, tvec))} {i + 1} {png_name}\n"
            )
            f.write("\n")

            original_png_path = Path(manifest["paths"]["masked_frames"]) / png_name
            target_image_path = image_dir / png_name

            if original_png_path.exists():
                # Read the image with its Alpha channel
                img_rgba = cv2.imread(str(original_png_path), cv2.IMREAD_UNCHANGED)

                if img_rgba is not None and img_rgba.shape[2] == 4:
                    # Extract Color and Alpha
                    bgr = img_rgba[:, :, :3].astype(np.float32)
                    alpha = img_rgba[:, :, 3].astype(np.float32) / 255.0

                    # Soften the edges slightly to prevent aliasing spikes
                    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
                    alpha_3c = np.expand_dims(alpha, axis=2)

                    # Create a pure white background canvas
                    white_bg = np.ones_like(bgr) * 255.0

                    # Smoothly composite the object over the white background
                    bgr_float = bgr.astype(np.float32)
                    composited_bgr = (bgr_float * alpha_3c) + (
                        white_bg * (1.0 - alpha_3c)
                    )
                    composited_bgr = composited_bgr.astype(np.uint8)

                    # Save as a flat 3-channel image
                    cv2.imwrite(str(target_image_path), composited_bgr)
                else:
                    # Fallback just in case the image was already flat
                    shutil.copy2(str(original_png_path), str(target_image_path))

    # 3. Write points3D.txt
    # TARGETED DOWNSAMPLING
    MAX_POINTS = 1_000_000

    initial_pts = len(pcd.points)
    status_update(f"Initial cloud density: {initial_pts:,} points.")

    if initial_pts > MAX_POINTS:
        status_update(f"Cloud too large. Randomly downsampling to {MAX_POINTS:,} points...")
        indices = np.random.choice(initial_pts, MAX_POINTS, replace=False)
        pcd = pcd.select_by_index(indices)
    else:
        status_update("Cloud is within safe limits. Skipping downsampling.")

    status_update(f"Final cloud density for 2DGS: {len(pcd.points):,} points.")

    # Extract data for COLMAP format
    final_verts = np.asarray(pcd.points)
    final_colors = np.asarray(pcd.colors) * 255  # O3D colors are 0-1

    with open(sparse_dir / "points3D.txt", "w") as f:
        f.write("# 3D point list: POINT3D_ID, X, Y, Z, R, G, B, ERROR\n")
        for i in range(len(final_verts)):
            v, c = final_verts[i], final_colors[i]
            f.write(
                f"{i + 1} {v[0]} {v[1]} {v[2]} {int(c[0])} {int(c[1])} {int(c[2])} 0\n"
            )

    status_update(f"2DGS export complete. Source path for train.py: {input_dir_2dgs}")
    return input_dir_2dgs


# =====================================================================
# MAIN SURFACE RECONSTRUCTION (2DGS)
# =====================================================================


def run_surface_reconstruction(
    manifest_path,
    train_iterations,
    densify_until_iter,
    opacity_reset_interval,
    force=False,
    ipc_mode=False
):
    # 1. Load Manifest
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    output_dir = Path(manifest["paths"]["geometry"])
    output_dir.mkdir(parents=True, exist_ok=True)

    # 2. Setup Directories
    input_data_path = output_dir / "input_for_2dgs"
    sparse_dir = input_data_path / "sparse" / "0"
    image_dir = input_data_path / "images"

    # --- SPATIAL INITIALIZATION CHECK ---
    spatial_init_complete = (sparse_dir / "points3D.txt").exists() and (
        sparse_dir / "cameras.txt"
    ).exists()

    if spatial_init_complete and not force:
        status_update(f"Found existing spatial initialization in {input_data_path}. Skipping prep and bundle adjustment...")
    else:
        # We need to run spatial init, ensure directories exist fresh
        if force and input_data_path.exists():
            shutil.rmtree(input_data_path)

        sparse_dir.mkdir(parents=True, exist_ok=True)
        image_dir.mkdir(parents=True, exist_ok=True)

        # 3. Prepare Images (White Background Composite)
        status_update("Prepping images for Geometric Solver...",
                        progress=0.0,
                        progress_msg="Phase 4: Preparing images...",
                        phase=4)
        
        start_time_pycolmap = time.perf_counter()
        masked_frames = list(Path(manifest["paths"]["masked_frames"]).glob("*.png"))
        total_frames = len(masked_frames)

        for i, original_png_path in enumerate(masked_frames):
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

            if ipc_mode and total_frames > 0 and i % 10 == 0:
                send_progress(
                    (i / total_frames) * 0.15,
                    f"Preparing image {i + 1} of {total_frames}",
                    phase=4
                )
        
        # 4. RUN BUNDLE ADJUSTMENT
        status_update("Started running bundle adjustment...",
                      progress=0.15,
                      progress_msg="Phase 4: Running Bundle Adjustment...",
                      phase=4)
        run_bundle_adjustment(image_dir, sparse_dir)

        total_time_pycolmap = time.perf_counter() - start_time_pycolmap
        status_update(f"Spatial Initialization via pycolmap Complete. Saved to: {input_data_path}")
        status_update(f"Total Time: {total_time_pycolmap:.2f}s")

    # 5. Training
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

    # 6. Rendering/Meshing
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

    status_update(f"Starting 2DGS Training ({train_iterations} iterations)...",
                  progress=0.30,
                  progress_msg="Phase 4: Training 2DG...",
                  phase=4)
    total_time = 0
    start_time = time.perf_counter()

    train_checkpoint_exists = ( 
        gs_model_dir / "point_cloud" / f"iteration_{train_iterations}"
    ).exists()  # change depending on number of iterations

    if train_checkpoint_exists and not force:
        status_update("Found existing training output. Skipping training...")
    else:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        process = subprocess.Popen(
            train_cmd, cwd=str(GS_PATH), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        assert process.stdout is not None

        TRAIN_START = 0.30
        TRAIN_END = 0.85    
        TRAIN_RANGE = TRAIN_END - TRAIN_START

        for line in process.stdout:
            line = line.rstrip()
            print(f"\r{line}", end="", flush=True)
            if ipc_mode:
                match = re.search(r'(\d+)\s*/\s*(\d+)', line)
                if match:
                    current = int(match.group(1))
                    total = int(match.group(2))

                    progress = TRAIN_START + (current / total) * TRAIN_RANGE
                    send_log("")
                    send_progress(
                        progress,
                        f"Training {current}/{total} iterations",
                        phase=4
                    )
                else:   
                    stripped = line.strip()
                    if stripped and not stripped.startswith("("):
                        send_log(f"[train] {stripped}")

        process.wait()
        if process.returncode != 0:
            status_error("Phase 4: Training failed")
            sys.exit(1)

    status_update("Starting Mesh Extraction (TSDF Fusion)...",
                progress=0.85,
                progress_msg="Phase 4: Extracting mesh...",
                phase=4)
    mesh_output_dir = gs_model_dir / "train" / f"ours_{train_iterations}"

    if mesh_output_dir.exists() and not force:
        status_update("Found existing mesh output. Skipping meshing...")
    else:
        process = subprocess.Popen(
            render_cmd, cwd=str(GS_PATH), env=os.environ.copy(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip()
            print(f"\r{line}", end="", flush=True)
            if ipc_mode and line.strip():
                send_log(f"[render] {line}")
        process.wait()
        if process.returncode != 0:
            status_error("Phase 4: Meshing failed")
            sys.exit()

    # 7. Final Stage: Expose PLY to the workspace root for Phase 5
    target_fused_ply = output_dir / "fused_mesh.ply"
    
    if mesh_output_dir.exists():
        # Strictly search for the post-processed mesh
        possible_meshes = list(mesh_output_dir.rglob("*_post.ply"))

        if possible_meshes:
            # Grab the post-processed mesh (it will be fuse_post.ply or fuse_unbounded_post.ply)
            best_mesh = possible_meshes[0]

            shutil.copy2(str(best_mesh), str(target_fused_ply))
            status_update(f"Base geometry staged for Phase 5 at: {target_fused_ply}")
        else:
            status_error(f"No *_post.ply files found in {mesh_output_dir}.")
    else:
        status_error(f"Mesh directory {mesh_output_dir} not found.")

    manifest["status"]["phase"] = 4
    if "geometry" not in manifest["status"]["completed"]:
        manifest["status"]["completed"].append("geometry")

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    total_time = time.perf_counter() - start_time
    print("PROGRESS: 100")
    status_update(f"2DGS Reconstruction Complete. Saved to: {output_dir}")
    status_update(f"Total Time: {total_time:.2f}s")
    status_update(f"2DGS Reconstruction complete. Output: {output_dir}",
                  progress=1.0,
                  progress_msg="Phase 4: Geometry complete",
                  phase=4)



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=str, required=True, help="Path to project manifest.json"
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing geometry data"
    )

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
        ipc_mode=args.ipc
    )