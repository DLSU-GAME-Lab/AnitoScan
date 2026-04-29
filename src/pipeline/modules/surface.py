import argparse
import json
import subprocess
import sys
import os
import shutil
from pathlib import Path

# =====================================================================
# DIRECTORY RESOLUTION
# =====================================================================
MODULE_PATH = Path(__file__).resolve()  
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent

# 1. Update the path resolution
NEUS2_PATH = PROJECT_ROOT / "vendor" / "NeuS2"
train_script = NEUS2_PATH / "scripts" / "run.py"
# The confirmed path:
config_file = NEUS2_PATH / "configs" / "nerf" / "base.json"

# 2. Update the train_cmd logic
def run_surface_reconstruction(manifest_path, force=False):
    # 1. Load Manifest
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    # NeuS2 reads from the geometry folder (where transforms.json is)
    geometry_dir = Path(manifest.get("paths", {}).get("geometry", str(PROJECT_ROOT / "data" / "geometry" / "transform")))
    geometry_dir = geometry_dir / "transform"

    # We will save the final 3D mesh here
    output_dir = Path(manifest.get("paths", {}).get("geometry", str(PROJECT_ROOT / "data" / "surface")))
    output_dir = output_dir / "final_reconstruction.obj"

    # Construct the command for the 19reborn version
    train_cmd = [
        sys.executable,
        str(train_script),
        "--name", "AnitoScan_Project",
        "--mode", "sdf",               # SDF is required for high-quality surfaces
        "--scene", str(geometry_dir / "transforms.json"),
        "--marching_cubes_res", "256",
        "--network", str(config_file), # Points to configs/nerf/base.json
        "--train",                     # Enable training mode
        "--n_steps", "500",             # ~5-10 mins on a modern GPU
        "--save_mesh",                  # Generate .ply when finished
        "--save_mesh_path", str(output_dir)
    ]

    print(f"[*] Executing NeuS2 command...")
    # It's vital to run this with the NeuS2 root as the CWD (Current Working Directory)
    # because the internal C++ testbed relies on relative paths to shaders/kernels.
    try:
        subprocess.run(train_cmd, cwd=str(NEUS2_PATH), check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] NeuS2 failed with exit code {e.returncode}")
        print(f"[!] NeuS2 failed. Check if you installed 'commentjson' and 'pytorch3d'.")
        sys.exit(1)

    # 4. Phase 2: Extract the 3D Mesh
    print(f"[*] Phase 2: Extracting Mesh (.ply)...")
    
    # NeuS2 extracts meshes by running the same script with --mode validate_mesh
    mesh_cmd = [
        sys.executable,
        str(train_script),
        "--mode", "validate_mesh",
        "--conf", str(config_file),
        "--case", str(geometry_dir),
        "--is_continue" # Tells it to use the weights it just finished training
    ]

    try:
        subprocess.run(mesh_cmd, cwd=str(NEUS2_PATH), check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] NeuS2 Mesh Extraction failed with exit code {e.returncode}")
        sys.exit(1)

    # 5. Move the final Mesh to our output folder
    # NeuS2 saves output in a folder called 'exp' by default
    neus_exp_dir = NEUS2_PATH / "exp" / geometry_dir.name
    mesh_files = list(neus_exp_dir.rglob("*.ply"))

    if not mesh_files:
        print(f"[!] Warning: No .ply mesh files found in {neus_exp_dir}.")
    else:
        # Sort to get the latest mesh if multiple were generated
        mesh_files.sort(key=os.path.getmtime)
        final_mesh = mesh_files[-1]
        target_mesh_path = output_dir / "final_mesh.ply"
        
        shutil.copy2(final_mesh, target_mesh_path)
        print(f"[*] Surface Reconstruction Complete!")
        print(f"[*] Saved final mesh to: {target_mesh_path}")

    print("PROGRESS: 100")