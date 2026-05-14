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
from scipy.spatial.transform import Rotation as R

# =====================================================================
# DIRECTORY RESOLUTION
# =====================================================================
MODULE_PATH = Path(__file__).resolve()  # /src/pipeline/modules/geometry.py
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent

# Vendor Paths for 2DGS/SuGaR
GS_PATH = PROJECT_ROOT / "vendor" / "2d-gaussian-splatting"


# def calculate_aabb_from_ply(ply_path):
#     if not ply_path.exists():
#         return 1.0

#     # Load the object
#     geo = trimesh.load(str(ply_path))

#     # All trimesh Geometry objects (Scene, Trimesh, PointCloud)
#     # are required to implement the .bounds property.
#     # .bounds returns [min_xyz, max_xyz]
#     b = geo.bounds
#     extents = b[1] - b[0]
#     scale = float(np.max(extents))

#     return round(scale * 1.1, 2)


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

    # 1. Write cameras.txt
    with open(sparse_dir / "cameras.txt", "w") as f:
        f.write("# Camera list with one line per camera: \n")
        f.write("# CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n")
        for i, frame in enumerate(transforms["frames"]):
            raw_focal = frame["focal_length"]
            W = frame["w"]
            H = frame["h"]

            # THE CRITICAL FIX: Scale the focal length to match the full-resolution image
            scale_factor = max(W, H) / 512.0
            true_focal = raw_focal * scale_factor

            fov_x = 2 * math.atan(W / (2 * true_focal)) * (180 / math.pi)
            print(
                f"Camera {i}: Res {W}x{H} | Focal {true_focal:.2f} | FoV {fov_x:.2f}°"
            )

            # CAMERA_ID PINHOLE WIDTH HEIGHT fx fy cx cy
            f.write(
                f"{i + 1} PINHOLE {W} {H} {true_focal} {true_focal} {W / 2} {H / 2}\n"
            )

    # 2. Write images.txt and INJECT PNGs
    print("[*] Processing images and copying full-res Alpha Channels...")
    with open(sparse_dir / "images.txt", "w") as f:
        f.write("# Image list with two lines per image\n")
        f.write("# IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n")
        for i, frame in enumerate(transforms["frames"]):
            c2w = np.array(frame["transform_matrix"])

            # 1. Apply the center/scale shift to the position
            c2w[:3, 3] = (c2w[:3, 3] - center) / scale

            # Flip Y and Z axes: OpenGL (Y-up, Z-back) -> OpenCV (Y-down, Z-forward)
            # This ensures the camera is facing the origin (0,0,0)
            c2w_opencv = c2w.copy()
            c2w_opencv[:3, 1:3] *= -1
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

            # COPY THE ORIGINAL MASKED PNG (No resizing, keeps math perfectly aligned)
            original_png_path = Path(manifest["paths"]["masked_frames"]) / png_name
            if original_png_path.exists():
                shutil.copy2(str(original_png_path), str(image_dir / png_name))

    # 3. Write points3D.txt
    if not point_cloud_path.exists():
        print(f"[!] Warning: {point_cloud_path} not found.")
    else:
        # TARGETED DOWNSAMPLING
        # 2DGS can easily handle up to 500k starting points.
        # We only downsample if the dataset is massive, to save RAM.
        MAX_POINTS = 300_000

        initial_pts = len(pcd.points)
        print(f"[*] Initial cloud density: {initial_pts:,} points.")

        if initial_pts > MAX_POINTS:
            print(
                f"[*] Cloud too large. Randomly downsampling to {MAX_POINTS:,} points..."
            )
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

    # 2. Bridge MASt3R output to 2DGS format
    print("[*] Bridging MASt3R data to 2DGS format (COLMAP format)...")
    input_data_path = export_to_2dgs_format(manifest)

    # 3. Phase 2: Training (7k iterations)
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
        # "--sh_degree",
        # "2",  # Workaround: Limit to Degree 2 (9 coeffs)
        # "--convert_SHs_python",
        # "--densify_from_iter",
        # "1500",
        # "--densify_until_iter",
        # "2500",
        # "--opacity_reset_interval",
        # "10000",  # Prevent early pruning crashes
        "--white_background",
        # "--lambda_dist",
        # "1.0",
        # "--lambda_normal",
        # "0.05",
        "--quiet",
    ]

    print("[*] Starting 2DGS Training (7k iterations)...")
    start_time = time.perf_counter()
    try:
        subprocess.run(train_cmd, cwd=str(GS_PATH), env=os.environ.copy(), check=True)
    except subprocess.CalledProcessError:
        print("[!] Training failed.")
        sys.exit(1)

    # 4. Phase 3: Rendering/Meshing
    # Uses render.py to perform TSDF fusion and export the mesh
    print("[*] Starting Mesh Extraction (TSDF Fusion)...")
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
        "7000",
    ]

    try:
        subprocess.run(render_cmd, cwd=str(GS_PATH), env=os.environ.copy(), check=True)
    except subprocess.CalledProcessError:
        print("[!] Meshing failed.")
        sys.exit(1)

    # 4. Final Logging and Progress
    total_time = time.perf_counter() - start_time
    total_expected_frames = len(list((input_data_path / "images").glob("*")))

    print("PROGRESS: 100")
    print(f"[*] 2DGS Reconstruction Complete. Saved to: {output_dir}")
    print(f"[*] Speed: {total_expected_frames / total_time:.2f} fps")
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
