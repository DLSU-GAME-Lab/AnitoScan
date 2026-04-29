import argparse
import json
import shutil
import sys
import time
from pathlib import Path
import numpy as np
import cv2

# =====================================================================
# DIRECTORY RESOLUTION
# =====================================================================
MODULE_PATH = Path(__file__).resolve()  # /src/pipeline/modules/geometry.py
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent

def run_transform_generation(manifest_path, force=False):
    # 1. Load Manifest
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    # Inputs come from the previous steps
    image_dir = Path(manifest["paths"]["masked_frames"])
    spacial_dir = Path(manifest.get("paths", {}).get("spacial", str(PROJECT_ROOT / "data" / "spacial")))
    
    # We need a new path for the NeuS2 formatted data
    output_dir = Path(manifest.get("paths", {}).get("geometry", str(PROJECT_ROOT / "data" / "geometry")))
    output_dir = output_dir / "transform"
    neus_images_dir = output_dir / "images"

    # 2. Preparation & Validation
    if not spacial_dir.exists() or not spacial_dir.is_dir():
        print(f"[!] Spacial data directory not found: {spacial_dir}")
        print("    Please run spacial.py first.")
        sys.exit(1)

    if force and output_dir.exists():
        print(f"[!] Force flag detected. Wiping: {output_dir}")
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    neus_images_dir.mkdir(parents=True, exist_ok=True)

    # Gather input files
    npz_files = sorted(list(spacial_dir.glob("*.npz")))
    source_images = sorted(list(image_dir.glob("*.png")))
    total_pairs = len(npz_files)

    if total_pairs == 0:
        print(f"[!] Error: No .npz files found in {spacial_dir}")
        sys.exit(1)

    transforms_out_path = output_dir / "transforms.json"
    
    # 3. Check if we already have the outputs
    if transforms_out_path.exists() and not force:
        print(f"[*] Found existing transforms.json in {output_dir}. Skipping geometry generation.")
        print("PROGRESS: 100")
        return

    # 4. NeuS2 Camera Setup
    start_perf = time.perf_counter()
    print(f"[*] Generating NeuS2 geometry for {total_pairs} pairs to: {output_dir}")

    # NeuS2 / NeRF standardizes around a ~60 degree FOV if uncalibrated
    FOV_DEG = 60.0
    camera_angle_x = FOV_DEG * (np.pi / 180.0)

    # 5. Initialize Trajectory
    global_c2w = np.eye(4, dtype=np.float32)
    
    transforms_dict = {
        "camera_angle_x": camera_angle_x,
        # We will leave these blank globally and set them per-frame if needed,
        # but NeuS2 usually reads the first frame's data as global
        "frames": []
    }

    def add_frame(img_name, c2w_matrix, W, H, focal_length):
        src_img = image_dir / img_name
        dst_img = neus_images_dir / img_name
        if not dst_img.exists():
            shutil.copy2(src_img, dst_img)
            
        transforms_dict["frames"].append({
            "file_path": f"images/{img_name}",
            "transform_matrix": c2w_matrix.tolist(),
            "fl_x": focal_length,
            "fl_y": focal_length,
            "cx": W / 2.0,
            "cy": H / 2.0,
            "w": W,
            "h": H
        })

    # Add the very first frame (Identity pose)
    # Add the very first frame (Identity pose)
    first_data = np.load(npz_files[0])
    # ADD [0] to extract the first batch!
    H1, W1 = first_data['pts3d_1'][0].shape[:2] 
    f1 = (W1 / 2.0) / np.tan(camera_angle_x / 2.0)
    add_frame(source_images[0].name, global_c2w, W1, H1, f1)

    # 6. Geometry Generation Logic (Iterating through pairs)
    for i, npz_path in enumerate(npz_files):
        data = np.load(npz_path)
        
        # 1. Get raw 3D points and confidence. 
        # ADD [0] to extract the forward pass and ignore the reverse pass!
        pts3d_2_raw = data['pts3d_2'][0] 
        conf_2_raw = data['conf_2'][0]
        
        # Now the shape is strictly (H, W, 3), so we take the first two items
        H, W = pts3d_2_raw.shape[:2] 
        
        # 2. Flatten arrays
        pts3d_2 = pts3d_2_raw.reshape(-1, 3) 
        conf_2 = conf_2_raw.reshape(-1)
        img2_name = str(data['img2_name'])

        # 3. Dynamically calculate Intrinsics (K)
        focal_length = (W / 2.0) / np.tan(camera_angle_x / 2.0)
        K = np.array([
            [focal_length, 0, W / 2.0],
            [0, focal_length, H / 2.0],
            [0, 0, 1]
        ], dtype=np.float32)

        # 4. Dynamically generate the 2D pixel grid for this specific image
        X_grid, Y_grid = np.meshgrid(np.arange(W), np.arange(H), indexing='xy')
        pixel_coords_2d = np.stack([X_grid, Y_grid], axis=-1).reshape(-1, 2).astype(np.float32)

        # 5. Filter out noisy points
        confidence_threshold = np.percentile(conf_2, 90)
        valid_mask = conf_2 > confidence_threshold

        # NOW they will align perfectly! (114688 mask applied to 114688 rows)
        valid_3d_points = pts3d_2[valid_mask]
        valid_2d_pixels = pixel_coords_2d[valid_mask]

        # 6. Use Perspective-n-Point.
        # Since points are in Cam 1 space, and pixels are in Cam 2,
        # solvePnP gives us the World-to-Camera (w2c) matrix
        success, rvec, tvec, inliers = cv2.solvePnPRansac(
            valid_3d_points, 
            valid_2d_pixels, 
            K, 
            distCoeffs=None, 
            flags=cv2.SOLVEPNP_EPNP
        )

        if not success:
            print(f"[!] Warning: solvePnP failed for {img2_name}. Using previous pose.")
            relative_c2w = np.eye(4)
        else:
            R, _ = cv2.Rodrigues(rvec)
            
            # NeuS2 needs Camera-to-World (c2w), so we invert the w2c matrix
            relative_c2w = np.eye(4)
            relative_c2w[:3, :3] = R.T
            relative_c2w[:3, 3] = -R.T @ tvec.flatten()

        # Chain the relative pose to our global trajectory
        global_c2w = global_c2w @ relative_c2w
        
        # Standardize matrix for NeuS2 (Coordinate flip)
        flip_mat = np.array([
            [1, 0, 0, 0],
            [0, -1, 0, 0],
            [0, 0, -1, 0],
            [0, 0, 0, 1]
        ])
        neus_c2w = global_c2w @ flip_mat

        # Add to JSON
        add_frame(img2_name, neus_c2w, W, H, focal_length)

        # Progress tracking
        percent = int(((i + 1) / total_pairs) * 100)
        print(f"PROGRESS: {percent}")
        sys.stdout.flush()

    # 7. Write transforms.json
    with open(transforms_out_path, "w") as f:
        json.dump(transforms_dict, f, indent=4)

    print("PROGRESS: 100")

    end_perf = time.perf_counter()
    total_time = end_perf - start_perf
    processing_speed = total_pairs / total_time if total_time > 0 else 0

    print("[*] Geometry Generation Phase Complete.")
    print(f"[*] Total Transforms Generated: {len(transforms_dict['frames'])}")
    print(f"[*] Saved to: {transforms_out_path}")
    print(f"[*] Total Time: {total_time:.2f}s")
    print(f"[*] Processing Speed: {processing_speed:.2f} pairs/sec")