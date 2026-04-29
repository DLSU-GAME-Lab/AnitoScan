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

# Point to where NeuS2 will be installed
# Updated paths for 19reborn/NeuS2
NEUS2_PATH = PROJECT_ROOT / "vendor" / "NeuS2"
# The official repo uses a 'scripts' folder for Python execution
train_script = NEUS2_PATH / "scripts" / "run.py" 
# NeuS2 supports standard Instant-NGP style JSON (which your transforms.py creates)
config_name = "base.json" # Or "dtu.json" depending on your scene type

def run_surface_reconstruction(manifest_path, force=False):
    # 1. Load Manifest
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    # NeuS2 reads from the geometry folder (where transforms.json is)
    geometry_dir = Path(manifest.get("paths", {}).get("geometry", str(PROJECT_ROOT / "data" / "geometry" / "transform")))
    geometry_dir = geometry_dir / "transform"

    # We will save the final 3D mesh here
    output_dir = Path(manifest.get("paths", {}).get("surface", str(PROJECT_ROOT / "data" / "surface")))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Validation
    if not geometry_dir.exists() or not (geometry_dir / "transforms.json").exists():
        print(f"[!] Geometry data not found in {geometry_dir}")
        print("    Please run transforms.py first.")
        sys.exit(1)

    if not NEUS2_PATH.exists():
        print(f"[!] NeuS2 not found at {NEUS2_PATH}")
        print("    Please clone https://github.com/1900zyh/NeuS2.git into your vendor folder and build it.")
        sys.exit(1)

    # 2. Configure the NeuS2 Environment
    # NeuS2 runner is usually 'exp_runner.py'
    train_script = NEUS2_PATH / "exp_runner.py"
    
    # NeuS2 uses conf files. 'womask.conf' means training without background masks.
    # If your pipeline generated black-and-white masks earlier, you can use 'default.conf'
    config_file = NEUS2_PATH / "confs" / "womask.conf"

    # 3. Phase 1: Train the Neural Surface
    print(f"[*] Phase 1: Starting NeuS2 Training...")
    print(f"[*] Reading data from: {geometry_dir}")

    train_cmd = [
        sys.executable,  # Use current python environment
        str(train_script),
        "--mode", "train",
        "--conf", str(config_file),
        "--case", str(geometry_dir)
    ]

    try:
        # Run training. We use subprocess.run so we can see the output in real-time
        subprocess.run(train_cmd, cwd=str(NEUS2_PATH), check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] NeuS2 Training failed with exit code {e.returncode}")
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