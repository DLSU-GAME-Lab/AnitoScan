import argparse
import json
import shutil
import sys
import time
from pathlib import Path
import cv2
import numpy as np
import torch
from ultralytics import SAM

# DIRECTORY RESOLUTION
MODULE_PATH = Path(__file__).resolve()  # /src/pipeline/modules/remove_background.py
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')

def run_remove_background(manifest_path, force=False, model_size="s"):
    # 1. Load Manifest
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    input_dir = Path(manifest["paths"]["raw_frames"])
    output_dir = Path(manifest["paths"]["masked_frames"])

    # 2. Preparation & Validation
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"[!] Input directory not found: {input_dir}")
        sys.exit(1)

    if force and output_dir.exists():
        print(f"[!] Force flag detected. Wiping: {output_dir}")
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Gather source images
    source_images = sorted([
        f for f in input_dir.iterdir() 
        if f.suffix.lower() in IMAGE_EXTENSIONS
    ])
    
    total_expected_frames = len(source_images)
    if total_expected_frames == 0:
        print(f"[!] Error: No valid images found in {input_dir}")
        sys.exit(1)

    # 3. Check if we already have the frames we need
    existing_frames = list(output_dir.glob("*.png"))
    existing_frame_count = len(existing_frames)

    print(f"[*] Found {existing_frame_count} existing masked frames in {output_dir}.")
    if existing_frame_count >= total_expected_frames and not force:
        print(f"[*] Expected ~{total_expected_frames}. Skipping background removal phase.")
        print("PROGRESS: 100")
        return

    # 4. Initialize SAM 2
    if torch.cuda.is_available():
        device = 'cuda'
    elif torch.backends.mps.is_available():
        device = 'mps'
    else:
        device = 'cpu'
        
    print(f"[*] Initializing SAM 2 ({model_size}) on device: {device}")
    model = SAM(f"sam2_{model_size}.pt")

    # 5. Background Removal Logic
    start_perf = time.perf_counter()
    print(f"[*] Processing {total_expected_frames} frames to: {output_dir}")

    for i, img_path in enumerate(source_images):
        # We save as PNG to preserve the alpha (transparency) channel
        target_name = f"{img_path.stem}.png"
        target_path = output_dir / target_name

        # Predict using SAM 2
        results = model.predict(source=str(img_path), conf=0.25, device=device, verbose=False)

        img = cv2.imread(str(img_path))
        bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)

        if not results[0].masks:
            # If nothing is detected, keep the image but make it fully opaque
            # so the pipeline doesn't crash on a missing file
            bgra[:, :, 3] = 255 
        else:
            # Extract mask, resize to match image, and apply to alpha channel
            mask = results[0].masks.data[0].cpu().numpy().astype(np.float32) 
            h, w = img.shape[:2]
            mask_resized = cv2.resize(mask, (w, h))
            
            mask_255 = (mask_resized * 255).astype(np.uint8)
            bgra[:, :, 3] = cv2.bitwise_not(mask_255)

        # Export
        cv2.imwrite(str(target_path), bgra)

        # Progress tracking
        percent = int(((i + 1) / total_expected_frames) * 100)
        print(f"PROGRESS: {percent}")
        sys.stdout.flush()

    print("PROGRESS: 100")

    end_perf = time.perf_counter()
    total_time = end_perf - start_perf
    final_frame_count = len(list(output_dir.glob("*.png")))

    if total_time > 0:
        processing_speed = final_frame_count / total_time
    else:
        processing_speed = 0

    print("[*] Background Removal Phase Complete.")
    print(f"[*] Total Frames: {final_frame_count} frames")
    print(f"[*] Total Time: {total_time:.2f}s")
    print(f"[*] Processing Speed: {processing_speed:.2f} frames/sec")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--force", action="store_true")
    # Added model_size as an optional argument so you can override it from the CLI if needed
    parser.add_argument("--model_size", type=str, default="s", choices=['t', 's', 'b', 'l'])
    
    args = parser.parse_args()
    run_remove_background(args.manifest, force=args.force, model_size=args.model_size)