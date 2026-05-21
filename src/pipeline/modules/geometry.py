import argparse
import json
import math
import os
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
    print("[*] Starting Geometric Bundle Adjustment...")
    database_path = output_dir / "database.db"
    if database_path.exists():
        database_path.unlink()  # Start fresh

    # 1. Feature Extraction (API FIX APPLIED HERE)
    print("[*] Extracting SIFT features...")

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
    print("[*] Matching features...")
    pycolmap.match_exhaustive(database_path)  # type: ignore

    # 3. Incremental Mapping & Bundle Adjustment (Ceres Solver)
    print("[*] Running Ceres Solver (Bundle Adjustment)...")
    maps = pycolmap.incremental_mapping(database_path, image_dir, output_dir)  # type: ignore

    # Because pycolmap can technically return multiple disjoint maps,
    # we check if any maps were created, and extract the largest one (index 0)
    if not maps or len(maps) == 0:
        print(
            "[!] Bundle Adjustment failed to converge. The solver couldn't find enough matches."
        )
        sys.exit(1)

    # PyCOLMAP returns a dictionary in newer versions, where the largest map is usually key 0
    # or it returns a list. We will safely grab the first/largest one.
    best_map_key = list(maps.keys())[0] if isinstance(maps, dict) else 0
    best_map = maps[best_map_key]

    print(f"[*] Bundle Adjustment complete. Registered {len(best_map.images)} cameras.")

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
        print(f"[!] Error: {transforms_path} not found. Run spatial.py first.")
        sys.exit(1)

    if not point_cloud_path.exists():
        print(f"[!] Warning: {point_cloud_path} not found.")
        sys.exit(1)

    # 1. PRE-CALCULATE CENTER AND SCALE
    # We must do this first so the cameras and points match
    pcd = o3d.io.read_point_cloud(str(point_cloud_path))
    if pcd.is_empty():
        print("[!] Error: Point cloud is empty.")
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
            print(
                f"Camera {i}: Res {W}x{H} | Focal {true_focal:.2f} | FoV {fov_x:.2f}°"
            )

            # CAMERA_ID PINHOLE WIDTH HEIGHT fx fy cx cy
            f.write(
                f"{i + 1} PINHOLE {W} {H} {true_focal} {true_focal} {true_cx} {true_cy}\n"
            )

    # 3. Write images.txt and INJECT PNGs
    print("[*] Processing images and copying full-res Alpha Channels...")
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

            # # COPY THE ORIGINAL MASKED PNG (No resizing, keeps math perfectly aligned)
            # original_png_path = Path(manifest["paths"]["masked_frames"]) / png_name
            # if original_png_path.exists():
            #     shutil.copy2(str(original_png_path), str(image_dir / png_name))

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

                    # Create a pure black background canvas (zeros)
                    # black_bg = np.zeros_like(bgr)

                    # # Smoothly composite the object over the black background
                    # bgr_float = bgr.astype(np.float32)
                    # composited_bgr = (bgr_float * alpha_3c) + (
                    #     black_bg * (1.0 - alpha_3c)
                    # )
                    # composited_bgr = composited_bgr.astype(np.uint8)

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
    # 2DGS can easily handle up to 500k starting points.
    # We only downsample if the dataset is massive, to save RAM.
    MAX_POINTS = 1_000_000

    initial_pts = len(pcd.points)
    print(f"[*] Initial cloud density: {initial_pts:,} points.")

    if initial_pts > MAX_POINTS:
        print(f"[*] Cloud too large. Randomly downsampling to {MAX_POINTS:,} points...")
        # Random downsampling preserves the overall shape much better than large voxels
        # for thin edges and sparse mono scans.
        indices = np.random.choice(initial_pts, MAX_POINTS, replace=False)
        pcd = pcd.select_by_index(indices)
    else:
        print("[*] Cloud is within safe limits. Skipping downsampling.")

    print(f"[*] Final cloud density for 2DGS: {len(pcd.points):,} points.")

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

    print(f"[*] 2DGS export complete. Source path for train.py: {input_dir_2dgs}")
    return input_dir_2dgs


# =====================================================================
# MAIN SURFACE RECONSTRUCTION (2DGS)
# =====================================================================


def run_surface_reconstruction(manifest_path, force=False):
    # 1. Load Manifest
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    output_dir = Path(manifest["paths"]["geometry"])
    output_dir.mkdir(parents=True, exist_ok=True)

    # 2. Setup Directories
    input_data_path = output_dir / "input_for_2dgs"
    sparse_dir = input_data_path / "sparse" / "0"
    image_dir = input_data_path / "images"

    sparse_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    # 3. Prepare Images (White Background Composite)
    print("[*] Prepping images for Geometric Solver...")
    start_time_pycolmap = time.perf_counter()
    for original_png_path in Path(manifest["paths"]["masked_frames"]).glob("*.png"):
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

    # 4. RUN BUNDLE ADJUSTMENT
    run_bundle_adjustment(image_dir, sparse_dir)

    total_time_pycolmap = time.perf_counter() - start_time_pycolmap
    print(
        f"[*] Spatial Initialization via pycolmap Complete. Saved to: {input_data_path}"
    )
    print(f"[*] Total Time: {total_time_pycolmap:.2f}s")

    # 5. Training (7k iterations)
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
        "7000",
        "--densify_from_iter",
        "500",  # default is 500
        "--densify_until_iter",
        # "7500",  # default is 15000
        "5000",
        "--opacity_reset_interval",
        # "3000",  # default is 3000
        "1000",
        "--white_background",
        "--lambda_dist",
        "0.0",  # default is 0.0
        "--lambda_normal",
        "0.05",  # default is 0.05
        "--quiet",
    ]

    # 6. Rendering/Meshing
    # Uses render.py to perform TSDF fusion and export the mesh
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
        "7000",  # change depending on number of iterations of train
    ]

    print("[*] Starting 2DGS Training (7k iterations)...")
    start_time = time.perf_counter()

    train_checkpoint_exists = (
        gs_model_dir / "point_cloud" / "iteration_7000"
    ).exists()  # change depending on number of iterations
    if train_checkpoint_exists and not force:
        print("[*] Found existing training output. Skipping training...")
    else:
        try:
            subprocess.run(
                train_cmd, cwd=str(GS_PATH), env=os.environ.copy(), check=True
            )
        except subprocess.CalledProcessError:
            print("[!] Training failed.")
            sys.exit(1)

    print("[*] Starting Mesh Extraction (TSDF Fusion)...")
    mesh_checkpoint_exists = (
        gs_model_dir / "train" / "ours_7000"
    ).exists()  # change depending on number of iterations
    if mesh_checkpoint_exists and not force:
        print("[*] Found existing mesh output. Skipping meshing...")
    else:
        try:
            subprocess.run(
                render_cmd, cwd=str(GS_PATH), env=os.environ.copy(), check=True
            )
        except subprocess.CalledProcessError:
            print("[!] Meshing failed.")
            sys.exit(1)

    # 7. Final Logging and Progress
    total_time = time.perf_counter() - start_time

    print("PROGRESS: 100")
    print(f"[*] 2DGS Reconstruction Complete. Saved to: {output_dir}")
    print(f"[*] Total Time: {total_time:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=str, required=True, help="Path to project manifest.json"
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing geometry data"
    )

    args = parser.parse_args()
    run_surface_reconstruction(args.manifest, force=args.force)
