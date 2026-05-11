import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import torch
import trimesh
import cv2
from sklearn.neighbors import NearestNeighbors

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


# Convert BGRA masked PNGs to cropped RGB JPGs for MASt3R
# Crops tightly around the masked object to maximize feature density
def convert_masked_frames(source_images, converted_dir):

    converted_images = []

    for png_path in source_images:
        out_path = converted_dir / (Path(png_path).stem + ".jpg")

        if not out_path.exists():
            img = cv2.imread(png_path, cv2.IMREAD_UNCHANGED)
            if img is None:
                print(f"[!] Warning: Could not read {png_path}, skiping.")
                continue

            if img.ndim == 3 and img.shape[2] == 4:
                alpha_channel = img[:, :, 3]
                bgr = img[:, :, :3]

                # Find bounding box of the masked object
                coords = cv2.findNonZero(alpha_channel)
                if coords is None:
                    print(f"[!] Warning: Empty mask in {Path(png_path).name}, skipping")
                    continue

                x, y, w, h = cv2.boundingRect(coords)

                # Add 5% padding
                pad_x = int(w * 0.05)
                pad_y = int(h * 0.05)
                H, W = img.shape[:2]
                x1 = max(0, x - pad_x)
                y1 = max(0, y - pad_y)
                x2 = min(W, x + w + pad_x)
                y2 = min(H, y + h + pad_y)

                # Crop and apply binary mask - object on black background
                bgr_crop = bgr[y1:y2, x1:x2]
                alpha_crop = alpha_channel[y1:y2, x1:x2]
                mask = (alpha_crop > 0).astype(np.uint8)
                composited = bgr_crop.copy()
                composited[mask == 0] = 0
            
            else:
                composited = img

            cv2.imwrite(str(out_path), composited, [cv2.IMWRITE_JPEG_QUALITY, 95])
        
        converted_images.append(str(out_path))

    return converted_images

# Remove points whose mean neighbor distance exceeds the threshold
def filter_outliers(pts, colors, n_neighbors=20, std_multiplier=2.0):

    nbrs = NearestNeighbors(n_neighbors=n_neighbors).fit(pts)
    distances, _ = nbrs.kneighbors(pts)
    mean_distances = distances[:, 1:].mean(axis=1)  # exclude self (index 0)
    
    threshold = mean_distances.mean() + std_multiplier * mean_distances.std()
    mask = mean_distances < threshold
    
    print(f"[*] Outlier filter: kept {mask.sum():,} / {len(pts):,} points")
    return pts[mask], colors[mask]


def run_spatial_reconstruction(manifest_path, force=False):
    # 1. Load Manifest
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    # Input comes from the first step (capture.py)
    input_dir = Path(manifest["paths"]["masked_frames"])
    output_dir = Path(manifest["paths"]["spatial"])


    # 2. Preparation & Validation
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"[!] Input directory not found: {input_dir}")
        sys.exit(1)

    if force and output_dir.exists():
        print(f"[!] Force flag detected. Wiping: {output_dir}")
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)


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
        

    # 4. Gather and subsample source images
    all_images = sorted([str(p) for p in input_dir.glob("*.png")])
    total_available = len(all_images)

    if total_available < 2:
        print(f"[!] Error: Found only {total_available} masked frames in {input_dir}")
        sys.exit(1)

    # # Subsample to reduce redundancy
    N = 3       # higher N = fewer frames = less accuracy
    source_images = all_images[::N]
    print(f"[*] Subsampled {total_available} to {len(source_images)} frames")


    # 5. Convert masked PNGs to cropped RGB JPGs for MASt3R
    converted_dir = output_dir / "converted_for_mast3r"
    converted_dir.mkdir(exist_ok=True)

    print(f"[*] Converting masked frames...")
    source_images = convert_masked_frames(source_images, converted_dir)
    total_images = len(source_images)
    print(f"[*] Converted {total_images} frames")

    if total_images < 2:
        print(f"[!] Error: MASt3R requires at least 2 images. Got {total_images}.")
        sys.exit(1)


    # 6. Initialize MASt3R
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
    # controls how many neighboring frames each frame gets paired with.

    #pairs_swin = make_pairs(imgs_meta, scene_graph="swin-3", symmetrize=True)
    pairs_swin = make_pairs(imgs_meta, scene_graph="swin-10", symmetrize=True)
    
    # Manually add loop closure pairs connecting end frames back to start
    n = len(imgs_meta)
    loop_window = 15

    boundary_indices = list(range(loop_window)) + list(range(n - loop_window, n))
    boundary_imgs = [imgs_meta[i] for i in boundary_indices]
    pairs_boundary = make_pairs(boundary_imgs, scene_graph="complete", symmetrize=True)

    pairs = pairs_swin + pairs_boundary
    print(f"[*] Total pairs: {len(pairs)} (swin-10): {len(pairs_swin)} + boundary: {len(pairs_boundary)}")


    # 7. MASt3R Sparse Global Alignment
    # sparse_global_alignment performs inference and optimization internally
    cache_path = output_dir / "matching_cache"
    cache_path.mkdir(exist_ok=True)

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


    # 8. Extraction for next phase
    # The returned 'scene' object has methods to get optimized poses
    poses = scene.get_im_poses().detach().cpu().numpy()  # 4x4 matrices [R|t]
    focals = scene.get_focals().detach().cpu().numpy()

    pts3d_raw = scene.pts3d             # list of 252 tensors (M, 3) - XYZ
    colors_raw = scene.pts3d_colors     # list of 252 tensors (M, 1) - RGB

    pts3d_world_list = []
    colors_list = []

    for pts_cam, col in zip(pts3d_raw, colors_raw):
        pts = pts_cam.detach().cpu().numpy() if not isinstance(pts_cam, np.ndarray) else pts_cam
        col = col.detach().cpu().numpy() if not isinstance(col, np.ndarray) else col

        # Filter out black background points (all channels near zero)
        # These are artifact points from the black-background masked regions
        is_not_black = np.any(col > 0.05, axis=1)
        pts = pts[is_not_black]
        col = col[is_not_black]

        if len(pts) == 0:
            continue

        pts3d_world_list.append(pts)
        colors_list.append(col)

    pts3d_all = np.concatenate(pts3d_world_list, axis=0)
    colors_float = np.concatenate(colors_list, axis=0)

    # Filter outliers on float colors
    pts3d_all, colors_float = filter_outliers(pts3d_all, colors_float)

    # Convert to uint8 ONCE at the end
    colors_all = (colors_float * 255).astype(np.uint8)


    # 9. Save transforms
    transforms = {"camera_model": "PINHOLE", "frames": []}

    for i, path in enumerate(source_images):
        transforms["frames"].append(
        {
            "file_path": f"./{Path(path).name}",
            "transform_matrix": poses[i].tolist(),
            "focal_length": float(focals[i]),
        }
    )

    with open(output_dir / "transforms.json", "w") as f:
        json.dump(transforms, f, indent=4)
        

    # 10. Save outputs
    pc = trimesh.PointCloud(vertices=pts3d_all, colors=colors_all)
    pc.export(str(output_dir / "init_points.ply"))

    total_time = time.perf_counter() - start_perf
    print("PROGRESS: 100")

    result = scene.get_pts3d_colors()
    print(f"Total entries: {len(result)}")
    print(f"Source images: {len(source_images)}")
    print(f"Poses: {len(poses)}")


    # 11. Finalize Manifest
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
