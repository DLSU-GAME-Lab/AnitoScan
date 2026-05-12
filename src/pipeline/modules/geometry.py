import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation as R

# =====================================================================
# DIRECTORY RESOLUTION
# =====================================================================
MODULE_PATH = Path(__file__).resolve()  # /src/pipeline/modules/geometry.py
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent

# Vendor Paths for 2DGS/SuGaR
SUGAR_PATH = PROJECT_ROOT / "vendor" / "SuGaR"
# Note: SuGaR's internal 2DGS trainer
GS_TRAIN_SCRIPT = SUGAR_PATH / "gaussian_splatting" / "train.py"


def calculate_aabb_from_ply(ply_path):
    """
    Calculates the required AABB scale based on the point cloud extents.
    """
    if not ply_path.exists():
        print(f"[!] Warning: {ply_path.name} not found. Using default aabb_scale=1.0")
        return 1.0

    # Load the object
    pc = trimesh.load(str(ply_path))

    # Handle both Scene and Geometry objects to avoid attribute errors
    if isinstance(pc, trimesh.Scene):
        bounds = pc.bounds
    else:
        bounds = pc.bounds

    extents = bounds[1] - bounds[0]
    scale = float(np.max(extents))

    return round(scale * 1.1, 2)


# =====================================================================
# UTILITIES: MASt3R TO 2DGS/SUGAR BRIDGE
# =====================================================================


def export_to_sugar_format(manifest):
    """
    Bridges MASt3R output to the COLMAP format required by 2DGS/SuGaR.
    Handles C2W -> W2C conversion and coordinate flipping.
    """
    spatial_dir = Path(manifest["paths"]["spatial"])
    transforms_path = spatial_dir / "transforms.json"
    point_cloud_path = spatial_dir / "init_points.ply"

    # SuGaR expects data inside a specific 'sparse/0' folder
    sugar_input_dir = spatial_dir / "sugar_input"
    sparse_dir = sugar_input_dir / "sparse" / "0"
    image_dir = sugar_input_dir / "images"

    sparse_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    with open(transforms_path, "r") as f:
        transforms = json.load(f)

    # 1. Write cameras.txt (PINHOLE model)
    with open(sparse_dir / "cameras.txt", "w") as f:
        W, H = 512, 512  # Set to your MASt3R processing resolution
        for i, frame in enumerate(transforms["frames"]):
            focal = frame["focal_length"]
            # Format: CAMERA_ID PINHOLE WIDTH HEIGHT fx fy cx cy
            f.write(f"{i + 1} PINHOLE {W} {H} {focal} {focal} {W / 2} {H / 2}\n")

    # 2. Write images.txt (W2C conversion for SuGaR)
    with open(sparse_dir / "images.txt", "w") as f:
        for i, frame in enumerate(transforms["frames"]):
            # NeRF/MASt3R is C2W. SuGaR reader expects W2C.
            c2w = np.array(frame["transform_matrix"])

            # Change from OpenGL/Blender camera axes (Y up, Z back) to COLMAP (Y down, Z forward)
            # This matches the flip in dataset_readers.py
            c2w_colmap = c2w.copy()
            c2w_colmap[:3, 1:3] *= -1

            w2c = np.linalg.inv(c2w_colmap)

            rot_mat = w2c[:3, :3]
            tvec = w2c[:3, 3]

            # Convert to COLMAP-style quaternion [qw, qx, qy, qz]
            quat = R.from_matrix(rot_mat).as_quat()
            colmap_quat = [quat[3], quat[0], quat[1], quat[2]]

            file_name = Path(frame["file_path"]).name
            f.write(
                f"{i + 1} {' '.join(map(str, colmap_quat))} {' '.join(map(str, tvec))} {i + 1} {file_name}\n\n"
            )

            # Copy images to the 'images' folder for the SuGaR reader
            src_img = spatial_dir / frame["file_path"]
            if src_img.exists():
                shutil.copy2(src_img, image_dir / file_name)

    # 3. Write points3D.txt
    pc = trimesh.load(str(point_cloud_path))

    # Resolve the "Attribute vertices is unknown" error
    if isinstance(pc, trimesh.Scene):
        # Extract points from the first geometry in the scene
        geo_key = list(pc.geometry.keys())[0]
        vertices = pc.geometry[geo_key].vertices
        colors = pc.geometry[geo_key].visual.vertex_colors[:, :3]
    else:
        print("Error exporting to COLMAP format for 2DGS/SuGaR")
        sys.exit(1)

    with open(sparse_dir / "points3D.txt", "w") as f:
        for i in range(len(vertices)):
            v, c = vertices[i], colors[i]
            f.write(f"{i + 1} {v[0]} {v[1]} {v[2]} {c[0]} {c[1]} {c[2]} 0\n")

    print(f"[*] Bridge complete. SuGaR source path: {sugar_input_dir}")
    return sugar_input_dir


# =====================================================================
# MAIN SURFACE RECONSTRUCTION (2DGS + SUGAR)
# =====================================================================


def run_surface_reconstruction(manifest_path, force=False):
    # 1. Load Manifest
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    spatial_dir = Path(manifest["paths"]["spatial"])
    output_dir = Path(manifest["paths"]["geometry"])
    output_dir.mkdir(parents=True, exist_ok=True)

    # 2. Bridge MASt3R output to 2DGS/SuGaR format
    print("[*] Phase 1: Bridging MASt3R data to 2DGS/SuGaR format...")
    sugar_data_path = export_to_sugar_format(manifest)

    # 3. Initialization for Vanilla 2DGS (First 7k iterations)
    gs_output_dir = output_dir / "vanilla_2dgs"
    if force and gs_output_dir.exists():
        print(f"[!] Force flag detected. Wiping 2DGS cache: {gs_output_dir}")
        shutil.rmtree(gs_output_dir)
    gs_output_dir.mkdir(parents=True, exist_ok=True)

    # 4. Start 2DGS Initialization (First 7k iterations)
    train_cmd = [
        sys.executable,
        str(GS_TRAIN_SCRIPT),
        "-s",
        str(sugar_data_path),
        "-m",
        str(gs_output_dir),
        "--iterations",
        "7000",
        "--quiet",
    ]

    print(f"[*] Executing 2DGS Training for {manifest['run_name']}...")
    start_time = time.perf_counter()

    try:
        # Run from SuGaR path to ensure local module resolution
        subprocess.run(train_cmd, cwd=str(SUGAR_PATH), check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] 2DGS failed with exit code {e.returncode}")
        sys.exit(1)

    # 4. Final Logging and Progress
    total_time = time.perf_counter() - start_time
    total_expected_frames = len(list((sugar_data_path / "images").glob("*")))

    print("PROGRESS: 100")
    print(f"[*] 2DGS Initialization Complete. Saved to: {gs_output_dir}")
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
