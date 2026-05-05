import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

# =====================================================================
# DIRECTORY RESOLUTION
# =====================================================================
MODULE_PATH = Path(__file__).resolve()  # /src/pipeline/modules/geometry.py
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent

# 1. Update the path resolution
NEUS2_PATH = PROJECT_ROOT / "vendor" / "NeuS2"
train_script = NEUS2_PATH / "scripts" / "run.py"
# The confirmed path:
config_file = NEUS2_PATH / "configs" / "nerf" / "base.json"


def calculate_aabb_from_ply(ply_path):
    """
    Calculates the required AABB scale based on the point cloud extents.
    """
    if not ply_path.exists():
        print(f"[!] Warning: {ply_path.name} not found. Using default aabb_scale=1.0")
        return 1.0

    # Load the object
    pc = trimesh.load(str(ply_path))

    # Use .extents (width, height, depth) directly.
    scale = float(np.max(pc.extents))

    return round(scale * 1.1, 2)


# 2. Update the train_cmd logic
def run_surface_reconstruction(manifest_path, force=False):
    # 1. Load Manifest
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    spatial_dir = Path(manifest["paths"]["spatial"])
    transforms_path = spatial_dir / "transforms.json"
    point_cloud_path = spatial_dir / "init_points.ply"

    # NeuS2 saves training checkpoints and results here
    neus_exp_dir = NEUS2_PATH / "exp" / manifest["run_name"]

    # We will save the final 3D mesh here
    output_dir = Path(manifest["paths"]["geometry"])
    output_dir.mkdir(parents=True, exist_ok=True)

    if force and neus_exp_dir.exists():
        print(f"[!] Force flag detected. Wiping NeuS2 experiment cache: {neus_exp_dir}")
        shutil.rmtree(neus_exp_dir)

    aabb_scale = calculate_aabb_from_ply(point_cloud_path)
    print(f"[*] Calculated AABB scale: {aabb_scale}")

    with open(transforms_path, "r") as f:
        transforms_data = json.load(f)
    total_expected_frames = len(transforms_data.get("frames", []))

    # Construct the command for the 19reborn version
    train_cmd = [
        sys.executable,
        str(train_script),
        "--name",
        manifest["run_name"],
        "--mode",
        "sdf",  # SDF is required for high-quality surfaces
        "--scene",
        str(transforms_path),
        "--aabb_scale",
        str(aabb_scale),
        "--marching_cubes_res",
        "256",  # TODO: change to 512 for release ver
        "--network",
        str(config_file),  # Points to configs/nerf/base.json
        "--train",  # Enable training mode
        "--n_steps",
        "500",  # ~5-10 mins on a modern GPU
        "--save_mesh",  # Generate .ply when finished
        "--save_mesh_path",
        str(output_dir / "final_mesh.ply"),
    ]

    print(f"[*] Executing NeuS2 Training for {manifest['run_name']}...")
    start_time = time.perf_counter()
    try:
        # NeuS2 must run in its own directory for shader/kernel resolution
        subprocess.run(train_cmd, cwd=str(NEUS2_PATH), check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] NeuS2 failed with exit code {e.returncode}")
        sys.exit(1)

    # 4. Phase 2: Extract the 3D Mesh
    print("[*] Phase 2: Extracting Mesh (.ply)...")

    # NeuS2 extracts meshes by running the same script with --mode validate_mesh
    mesh_cmd = [
        sys.executable,
        str(train_script),
        "--mode",
        "validate_mesh",
        "--conf",
        str(config_file),
        "--case",
        str(manifest["run_name"]),
        "--is_continue",  # Tells it to use the weights it just finished training
    ]

    try:
        subprocess.run(mesh_cmd, cwd=str(NEUS2_PATH), check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] NeuS2 Mesh Extraction failed with exit code {e.returncode}")
        sys.exit(1)

    # 5. Move the final Mesh to our output folder
    # NeuS2 saves output in a folder called 'exp' by default
    mesh_files = list(neus_exp_dir.rglob("*.ply"))

    if mesh_files:
        mesh_files.sort(key=os.path.getmtime)
        shutil.copy2(mesh_files[-1], output_dir / "final_mesh.ply")

    # 6. Final Logging and Progress
    total_time = time.perf_counter() - start_time

    print("PROGRESS: 100")
    print(f"[*] Complete. Filtered visualization saved to: {output_dir}")
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
