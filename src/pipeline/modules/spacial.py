import argparse
import json
import shutil
import sys
import time
from pathlib import Path
import numpy as np
import torch
import cv2
from PIL import Image

# DIRECTORY RESOLUTION
MODULE_PATH = Path(__file__).resolve()  # /src/pipeline/modules/spacial.py
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent

MAST3R_PATH = PROJECT_ROOT / "vendor" / "mast3r"
DUST3R_PATH = MAST3R_PATH / "dust3r"

for p in [MAST3R_PATH, DUST3R_PATH]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Attempt MASt3R / DUSt3R imports
try:
    from mast3r.model import AsymmetricMASt3R
    from dust3r.inference import inference
    from dust3r.utils.image import load_images
    from dust3r.image_pairs import make_pairs
except ImportError:
    print("[!] Error: MASt3R modules not found.")
    print("    Ensure your PYTHONPATH includes the MASt3R and DUSt3R vendor folders.")
    sys.exit(1)



def run_spacial_reconstruction(manifest_path, force=False):
    # 1. Load Manifest
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    # Input comes from the previous step (remove_background.py)
    input_dir = Path(manifest["paths"]["masked_frames"])
    
    # We need a new path in the manifest for the 3D output data
    # Assuming manifest["paths"]["spacial_data"] exists
    output_dir = Path(manifest.get("paths", {}).get("spacial", str(PROJECT_ROOT / "data" / "spacial")))

    # 2. Preparation & Validation
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"[!] Input directory not found: {input_dir}")
        sys.exit(1)

    if force and output_dir.exists():
        print(f"[!] Force flag detected. Wiping: {output_dir}")
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Gather source masked images (must be PNGs to preserve the alpha channel)
    source_images = sorted(list(input_dir.glob("*.png")))
    total_images = len(source_images)
    
    if total_images < 2:
        print(f"[!] Error: MASt3R requires at least 2 images. Found {total_images} in {input_dir}")
        sys.exit(1)

    # In a pairwise sequence, N images yield N-1 pairs
    total_expected_pairs = total_images - 1

    # 3. Check if we already have the outputs we need
    existing_outputs = list(output_dir.glob("*.npz"))
    existing_count = len(existing_outputs)

    print(f"[*] Found {existing_count} existing spacial data files in {output_dir}.")
    if existing_count >= total_expected_pairs and not force:
        print(f"[*] Expected ~{total_expected_pairs}. Skipping spacial reconstruction phase.")
        print("PROGRESS: 100")
        return

    # 4. Initialize MASt3R
    if torch.cuda.is_available():
        device = 'cuda'
    elif torch.backends.mps.is_available():
        device = 'mps'
    else:
        device = 'cpu'
        
    print(f"[*] Initializing MASt3R on device: {device}")
    
    # Load the MASt3R model
    # Note: Depending on your specific MASt3R version, the init might vary slightly.
    # Force the model to load with a tuple to override the broken config
    local_model_path = r"models\spacial\MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric"

    model = AsymmetricMASt3R.from_pretrained(
        local_model_path
    ).to(device)
    model.eval()

    # 5. Spacial Reconstruction Logic
    start_perf = time.perf_counter()
    print(f"[*] Processing {total_expected_pairs} pairs to: {output_dir}")

    # Process pairs consecutively (Frame 1 -> Frame 2, Frame 2 -> Frame 3, etc.)
    for i in range(total_images - 1):
        img_path_1 = source_images[i]
        img_path_2 = source_images[i + 1]
        
        target_name = f"pair_{i+1:04d}.npz"
        target_path = output_dir / target_name

        if target_path.exists() and not force:
            continue

        # Load images using DUSt3R's native loader to handle sizing and normalization
        # We pass the paths as strings inside a list
        imgs = load_images([str(img_path_1), str(img_path_2)], size=512)
        # The tensor is typically stored inside each image dict under the 'img' key
        imgs_tensor = torch.stack([img['img'] for img in imgs])
        
        # Create a single pair configuration
        pairs = make_pairs(imgs, scene_graph="complete", prefilter=None, symmetrize=True)

        with torch.no_grad():
            # Run inference
            output = inference(pairs, model, device, batch_size=1, verbose=False)
            
            # Extract predictions
            pred1 = output['pred1']
            pred2 = output['pred2']

            # Image 1 is standard
            pts3d_1 = pred1['pts3d'].detach().cpu().numpy()

            # Image 2 uses a different key in the Asymmetric model
            if 'pts3d' in pred2:
                pts3d_2 = pred2['pts3d'].detach().cpu().numpy()
            else:
                # This is the key MASt3R uses for the second view in a pair
                pts3d_2 = pred2['pts3d_in_other_view'].detach().cpu().numpy()

            # Confidence and Descriptors are usually in both
            conf_1 = pred1['conf'].detach().cpu().numpy()
            conf_2 = pred2['conf'].detach().cpu().numpy()
            desc_1 = pred1['desc'].detach().cpu().numpy()
            desc_2 = pred2['desc'].detach().cpu().numpy()
            
            # Save the raw 3D data as an NPZ file for the next step in your pipeline
            np.savez_compressed(
                target_path,
                pts3d_1=pts3d_1,
                pts3d_2=pts3d_2,
                conf_1=conf_1,
                conf_2=conf_2,
                img1_name=img_path_1.name,
                img2_name=img_path_2.name
            )

        # Progress tracking
        percent = int(((i + 1) / total_expected_pairs) * 100)
        print(f"PROGRESS: {percent}")
        sys.stdout.flush()

    print("PROGRESS: 100")

    end_perf = time.perf_counter()
    total_time = end_perf - start_perf
    final_file_count = len(list(output_dir.glob("*.npz")))

    if total_time > 0:
        processing_speed = final_file_count / total_time
    else:
        processing_speed = 0

    print("[*] Spacial Reconstruction Phase Complete.")
    print(f"[*] Total Pairs Processed: {final_file_count}")
    print(f"[*] Total Time: {total_time:.2f}s")
    print(f"[*] Processing Speed: {processing_speed:.2f} pairs/sec")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True, help="Path to project manifest.json")
    parser.add_argument("--force", action="store_true", help="Overwrite existing spacial data")
    
    args = parser.parse_args()
    run_spacial_reconstruction(args.manifest, force=args.force)