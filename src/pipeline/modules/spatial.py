import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import torch
import trimesh

# DIRECTORY RESOLUTION
MODULE_PATH = Path(__file__).resolve()  # /src/pipeline/modules/spatial.py
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models" / "03_spatial"

MAST3R_PATH = PROJECT_ROOT / "vendor" / "mast3r"
DUST3R_PATH = MAST3R_PATH / "dust3r"

print(f"[*] Searching for MASt3R in: {MAST3R_PATH}")
if not MAST3R_PATH.exists():
    print(f"[!] ERROR: Folder not found at {MAST3R_PATH}")

for p in [MAST3R_PATH, DUST3R_PATH]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Attempt MASt3R / DUSt3R imports
try:
    from dust3r.image_pairs import make_pairs
    from dust3r.utils.image import load_images
    from mast3r.cloud_opt.sparse_ga import sparse_global_alignment
    from mast3r.model import AsymmetricMASt3R
except ImportError:
    print("[!] Error: MASt3R modules not found.")
    print("    Ensure your PYTHONPATH includes the MASt3R and DUSt3R vendor folders.")
    sys.exit(1)


def run_spatial_reconstruction(manifest_path, force=False):
    # 1. Load Manifest
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    # Input comes from the first step (capture.py)
    input_dir = Path(manifest["paths"]["raw_frames"])
    output_dir = Path(manifest["paths"]["spatial"])

    # 2. Preparation & Validation
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"[!] Input directory not found: {input_dir}")
        sys.exit(1)

    if force and output_dir.exists():
        print(f"[!] Force flag detected. Wiping: {output_dir}")
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Gather source images
    source_images = sorted([str(p) for p in input_dir.glob("*.jpg")])
    total_images = len(source_images)

    if total_images < 2:
        print(
            f"[!] Error: MASt3R requires at least 2 images. Found {total_images} in {input_dir}"
        )
        sys.exit(1)

    # 3. Check for existing artifacts in the output directory
    required_artifacts = ["transforms.json", "init_points.ply"]

    # Check if the folder exists and contains both required files
    if output_dir.exists() and not force:
        artifacts_present = all((output_dir / f).exists() for f in required_artifacts)
        if artifacts_present:
            print(
                f"[*] Found completed artifacts in {output_dir}. Skipping spatial reconstruction."
            )
            print("PROGRESS: 100")
            return

    # 4. Initialize MASt3R
    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"

    print(f"[*] Initializing MASt3R on device: {device}")

    # Load the MASt3R model
    # Note: Depending on your specific MASt3R version, the init might vary slightly.
    # Force the model to load with a tuple to override the broken config
    model_path = str(MODELS_DIR / "MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric")

    model = AsymmetricMASt3R.from_pretrained(model_path).to(device)
    model.eval()

    # Load images for the pair-matching metadata
    imgs_meta = load_images(
        source_images, size=256
    )  # TODO: change to 512 for release ver

    # Create the scene graph
    # 'swin-3' means a sliding window of size 3
    pairs = make_pairs(imgs_meta, scene_graph="swin-3", symmetrize=True)

    # sparse_global_alignment performs inference and optimization internally
    cache_path = output_dir / "matching_cache"
    cache_path.mkdir(exist_ok=True)

    # 4. MASt3R-SfM: Sparse Global Alignment
    # This function replaces the manual inference + GlobalAligner loop.
    # It handles its own caching and memory optimization.
    print(f"[*] Running Sparse Global Alignment on {total_images} frames...")
    start_perf = time.perf_counter()

    scene = sparse_global_alignment(
        imgs=source_images,
        pairs_in=pairs,
        model=model,
        device=device,
        cache_path=str(cache_path),
        niter1=300,  # Coarse alignment iterations
        niter2=100,  # Fine alignment iterations
    )

    # 5. Extraction for next phase
    # The returned 'scene' object has methods to get optimized poses
    poses = scene.get_im_poses().detach().cpu().numpy()  # 4x4 matrices [R|t]
    focals = scene.get_focals().detach().cpu().numpy()

    pts3d_list = [p.detach().cpu().numpy() for p in scene.pts3d]
    pts3d_flattened = np.concatenate(pts3d_list, axis=0)

    transforms = {"camera_model": "PINHOLE", "frames": []}

    for i, path in enumerate(source_images):
        # We store camera-to-world (c2w) matrices for NeuS2
        transforms["frames"].append(
            {
                "file_path": f"./{Path(path).name}",
                "transform_matrix": poses[i].tolist(),
                "focal_length": float(focals[i]),
            }
        )

    # Save outputs
    with open(output_dir / "transforms.json", "w") as f:
        json.dump(transforms, f, indent=4)

    pc = trimesh.PointCloud(vertices=pts3d_flattened)
    pc.export(str(output_dir / "init_points.ply"))

    total_time = time.perf_counter() - start_perf
    print("PROGRESS: 100")

    # 6. Finalize Manifest
    manifest["status"]["phase"] = 3
    if "spatial" not in manifest["status"]["completed"]:
        manifest["status"]["completed"].append("spatial")

    total_frames = len(source_images)

    if total_time > 0:
        processing_speed = total_frames / total_time
    else:
        processing_speed = 0

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)
    has_transforms = (output_dir / "transforms.json").exists()
    has_points = (output_dir / "init_points.ply").exists()

    print("[*] Spatial Reconstruction Phase Complete.")
    print("[*] Artifacts Generated:")
    print(f"    - Camera Poses: {'[OK]' if has_transforms else '[MISSING]'}")
    print(f"    - Sparse Cloud: {'[OK]' if has_points else '[MISSING]'}")
    print(f"[*] Total Frames Aligned: {total_frames}")
    print(f"[*] Processing Speed: {processing_speed:.2f} frames/sec")
    print(f"[*] Total Time: {total_time:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=str, required=True, help="Path to project manifest.json"
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing spatial data"
    )

    args = parser.parse_args()
    run_spatial_reconstruction(args.manifest, force=args.force)
