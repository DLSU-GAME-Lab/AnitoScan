import argparse
import json
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics.models.sam import SAM
from ultralytics.models.yolo import YOLOE

# DIRECTORY RESOLUTION
MODULE_PATH = Path(__file__).resolve()  # /src/pipeline/modules/remove_background.py
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models" / "02_masking"

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def calculate_iou(boxA, boxB):
    # box = [x1, y1, x2, y2]
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA + 1) * max(0, yB - yA + 1)
    boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
    boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)

    iou = interArea / float(boxAArea + boxBArea - interArea)
    return iou


def calculate_centroid_drift(boxA, boxB):
    # Get centers: (x1 + x2) / 2, (y1 + y2) / 2
    centerA = np.array([(boxA[0] + boxA[2]) / 2, (boxA[1] + boxA[3]) / 2])
    centerB = np.array([(boxB[0] + boxB[2]) / 2, (boxB[1] + boxB[3]) / 2])
    # Euclidean distance
    return np.linalg.norm(centerA - centerB)


def run_remove_background(
    manifest_path,
    iou_threshold,
    drift_limit,
    max_yoloe_failures,
    yoloe_model_size,
    force=False,
):
    # 1. Load Manifest
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    input_dir = Path(manifest["paths"]["raw_frames"]).resolve()
    output_dir = Path(manifest["paths"]["masked_frames"]).resolve()

    # 2. Preparation & Validation
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"[!] Input directory not found: {input_dir}")
        sys.exit(1)

    if force and output_dir.exists():
        print(f"[!] Force flag detected. Wiping: {output_dir}")
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Gather source images
    source_images = sorted(
        [f for f in input_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS]
    )

    total_expected_frames = len(source_images)
    if total_expected_frames == 0:
        print(f"[!] Error: No valid images found in {input_dir}")
        sys.exit(1)

    # 3. Check if we already have the frames we need
    existing_frames = list(output_dir.glob("*.png"))
    existing_frame_count = len(existing_frames)

    print(f"[*] Found {existing_frame_count} existing masked frames in {output_dir}.")
    if existing_frame_count >= total_expected_frames and not force:
        print(
            f"[*] Expected ~{total_expected_frames}. Skipping background removal phase."
        )
        print("PROGRESS: 100")
        return

    # 4. Initialize Models
    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"

    yoloe_path = MODELS_DIR / f"yoloe-26{yoloe_model_size}-seg-pf.pt"
    sam_path = MODELS_DIR / "sam2.1_s.pt"

    # Uncomment to disable auto-download of model weights
    # if not yoloe_path.exists():
    #     print(f"[!] YOLOE weights not found: {yoloe_path}")
    #     sys.exit(1)

    # if not sam_path.exists():
    #     print(f"[!] SAM weights not found: {sam_path}")
    #     sys.exit(1)

    detector = YOLOE(str(yoloe_path))
    segmenter = SAM(str(sam_path))

    # Adjust these if the mask is still too tight or too loose
    BOX_PADDING_PERCENT = 0.08  # Expands the YOLO box by 8% before SAM
    MASK_DILATION_ITERATIONS = 2  # Number of times to thicken the final pixel mask
    dilation_kernel = np.ones((5, 5), np.uint8)

    # 4. Processing Loop
    start_perf = time.perf_counter()
    last_percent = -1
    prev_box = None
    consecutive_failures = 0

    # Step A: Zero-Shot Object Detection to get boundary box
    det_generator = detector.predict(
        source=str(input_dir), conf=0.35, device=device, stream=True, verbose=False
    )

    # Use a ThreadPool for writing to disk so the CPU can keep detecting
    with ThreadPoolExecutor(max_workers=4) as executor:
        for i, det_results in enumerate(det_generator):
            # Extract the current image path from the detection metadata
            img_path = Path(det_results.path)
            img = det_results.orig_img
            if img is None:
                print(f"[!] Critical: OpenCV could not read {img_path}")
                continue

            # class_names = det_results.names
            h_img, w_img = img.shape[:2]
            img_area = h_img * w_img

            # Default: Fully Transparent BGRA Frame
            final_output = np.zeros((h_img, w_img, 4), dtype=np.uint8)

            if det_results.boxes is not None and len(det_results.boxes) > 0:
                valid_boxes = []
                for box in det_results.boxes:
                    coords = box.xyxy[0].cpu().numpy()
                    box_area = (coords[2] - coords[0]) * (coords[3] - coords[1])

                    if (box_area / img_area) < 0.70:
                        valid_boxes.append(box)

                if valid_boxes:
                    best_candidate_match = None
                    highest_iou = -1.0
                    winner_coords = None

                    found_any_match = False
                    # Keep track of the best "failed" candidate for debugging
                    best_failed_stats = {"iou": -1.0, "drift": -1.0}

                    # Search through all valid boxes for the best temporal match
                    for idx, candidate_box in enumerate(valid_boxes):
                        candidate_coords = candidate_box.xyxy[0].cpu().numpy()

                        # First frame initialization: just take the most confident one
                        if prev_box is None:
                            best_candidate_match = candidate_box
                            winner_coords = candidate_coords
                            found_any_match = True
                            break

                        iou = calculate_iou(prev_box, candidate_coords)
                        drift = calculate_centroid_drift(prev_box, candidate_coords)

                        # Check thresholds (using 250px drift for safer 1 FPS tracking)
                        if iou > iou_threshold and drift < drift_limit:
                            # We want the candidate that overlaps most with our last known position
                            if iou > highest_iou:
                                highest_iou = iou
                                best_candidate_match = candidate_box
                                winner_coords = candidate_coords
                                found_any_match = True
                        else:
                            if iou > best_failed_stats["iou"]:
                                best_failed_stats = {
                                    "iou": iou,
                                    "drift": drift,
                                    "idx": idx,
                                }

                    # Only proceed if we found a candidate that passed the temporal check
                    if (
                        found_any_match
                        and winner_coords is not None
                        and best_candidate_match is not None
                    ):
                        # Calculate padding pixels based on the box size
                        box_w = winner_coords[2] - winner_coords[0]
                        box_h = winner_coords[3] - winner_coords[1]
                        pad_x = box_w * BOX_PADDING_PERCENT
                        pad_y = box_h * BOX_PADDING_PERCENT

                        # Apply padding while ensuring we don't go outside image boundaries
                        padded_coords = [
                            max(0, winner_coords[0] - pad_x),
                            max(0, winner_coords[1] - pad_y),
                            min(w_img, winner_coords[2] + pad_x),
                            min(h_img, winner_coords[3] + pad_y),
                        ]

                        prompt_bboxes = np.array([padded_coords], dtype=np.float32)
                        sam_results = segmenter.predict(
                            source=img,
                            bboxes=prompt_bboxes,
                            device=device,
                            verbose=False,
                        )
                        if sam_results[0].masks is not None:
                            mask_np = sam_results[0].masks.data[0].cpu().numpy()
                            mask_resized = cv2.resize(
                                (mask_np > 0).astype(np.uint8) * 255,
                                (w_img, h_img),
                                interpolation=cv2.INTER_NEAREST,
                            )

                            # Convert to BGRA
                            bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)

                            # HARD-MASK THE RGB CHANNELS
                            bgra[:, :, :3] = cv2.bitwise_and(
                                bgra[:, :, :3], bgra[:, :, :3], mask=mask_resized
                            )

                            # # INVERT THE MASK AREA TO 255 (Turns background from 0 to 255 / White)
                            bgra[mask_resized == 0, :3] = 255

                            # Apply mask to Alpha
                            bgra[:, :, 3] = mask_resized
                            final_output = bgra

                            consecutive_failures = 0
                            prev_box = winner_coords
                    else:
                        # Fallback: No candidate in this frame matched the previous one
                        print(f"\n[!] REJECTION DEBUG - Frame {i + 1}")
                        print(f"    - Valid Candidates Found: {len(valid_boxes)}")
                        print(
                            f"    - Target Thresholds: IoU > {iou_threshold} | Drift < {drift_limit}px"
                        )
                        if len(valid_boxes) > 0:
                            print(
                                f"    - Best Failed Candidate (#{best_failed_stats['idx']}):"
                            )
                            print(f"      IoU: {best_failed_stats['iou']:.4f}")
                            print(f"      Drift: {best_failed_stats['drift']:.1f}px")
                        else:
                            print(
                                "    - Reason: YOLOE found 0 valid boxes (Area < 70%)."
                            )
                        print("-" * 30)
                        consecutive_failures += 1
                        if consecutive_failures >= max_yoloe_failures:
                            print(
                                f"[*] Lost track for {consecutive_failures} frames. Resetting anchor at Frame {i + 1}."
                            )
                            prev_box = None

            # 5. Asynchronous Save
            target_path = output_dir / f"{img_path.stem}.png"
            executor.submit(cv2.imwrite, str(target_path), final_output)

            # 6. Live Progress Reporting
            current_percent = min(int(((i + 1) / total_expected_frames) * 100), 99)
            if current_percent >= last_percent + 5:
                print(f"PROGRESS: {current_percent}")
                sys.stdout.flush()
                last_percent = current_percent

    total_time = time.perf_counter() - start_perf
    print("PROGRESS: 100")

    # Finalize Manifest
    manifest["status"]["phase"] = 2
    if "masking" not in manifest["status"]["completed"]:
        manifest["status"]["completed"].append("masking")

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    print(f"[*] Complete. Filtered visualization saved to: {output_dir}")
    print(f"[*] Speed: {total_expected_frames / total_time:.2f} fps")
    print(f"[*] Total Time: {total_time:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--iou_threshold", type=float)
    parser.add_argument("--drift_limit", type=int)
    parser.add_argument("--max_yoloe_failures", type=int)
    parser.add_argument(
        "--yoloe_model_size", type=str, choices=["n", "s", "m", "l", "x"]
    )

    args = parser.parse_args()
    run_remove_background(
        args.manifest,
        iou_threshold=args.iou_threshold,
        drift_limit=args.drift_limit,
        max_yoloe_failures=args.max_yoloe_failures,
        yoloe_model_size=args.yoloe_model_size,
        force=args.force,
    )
