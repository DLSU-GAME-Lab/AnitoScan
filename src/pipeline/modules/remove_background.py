import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics.models.sam import SAM
from ultralytics.models.yolo import YOLOE

MODULE_PATH = Path(__file__).resolve()
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models" / "02_masking"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def calculate_iou(boxA, boxB):
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
    centerA = np.array([(boxA[0] + boxA[2]) / 2, (boxA[1] + boxA[3]) / 2])
    centerB = np.array([(boxB[0] + boxB[2]) / 2, (boxB[1] + boxB[3]) / 2])
    return np.linalg.norm(centerA - centerB)


def get_user_selection(
    img, detector, temp_dir, frame_name, device, action_cb=None, log_cb=None
):
    start_wait = time.perf_counter()
    if log_cb:
        log_cb(f"Running YOLOE-26 on {frame_name}...")

    results = detector.predict(source=img, conf=0.35, device=device, verbose=False)[0]

    if results.boxes is None or len(results.boxes) == 0:
        if log_cb:
            log_cb("YOLOE found no valid subjects in this frame.")
        return None, time.perf_counter() - start_wait

    h_img, w_img = img.shape[:2]
    img_area = h_img * w_img
    valid_boxes = []

    for box in results.boxes:
        coords = box.xyxy[0].cpu().numpy()
        box_area = (coords[2] - coords[0]) * (coords[3] - coords[1])
        if (box_area / img_area) < 0.70:
            valid_boxes.append(coords.tolist())

    if not valid_boxes:
        return None, time.perf_counter() - start_wait

    preview_img = img.copy()
    overlay = img.copy()

    palette = [
        (0, 255, 0),
        (255, 255, 0),
        (0, 0, 255),
        (255, 0, 255),
        (0, 165, 255),
        (255, 0, 0),
        (0, 255, 255),
        (140, 0, 140),
    ]

    drawn_labels = []

    for idx, coords in enumerate(valid_boxes):
        x1, y1, x2, y2 = map(int, coords)
        color = palette[idx % len(palette)]
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)

        label_y = y1
        shift_amount = 35
        while any(
            abs(label_y - dy) < shift_amount and abs(x1 - dx) < 40
            for dx, dy in drawn_labels
        ):
            label_y += shift_amount

        drawn_labels.append((x1, label_y))
        cv2.rectangle(overlay, (x1, label_y - 30), (x1 + 40, label_y), color, -1)
        cv2.putText(
            overlay,
            str(idx),
            (x1 + 5, label_y - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 0),
            2,
        )

    alpha = 0.6
    cv2.addWeighted(overlay, alpha, preview_img, 1 - alpha, 0, preview_img)

    temp_dir.mkdir(parents=True, exist_ok=True)
    preview_path = temp_dir / f"{frame_name}_candidates.png"

    write_success = cv2.imwrite(str(preview_path), preview_img)
    if not write_success:
        raise RuntimeError(f"OpenCV failed to write preview image to: {preview_path}")

    if action_cb is not None:
        # Injected callback emits action_required and waits for choice
        choice = action_cb(str(preview_path), len(valid_boxes), frame_name)
        if choice is None or choice == "skip":
            return None, time.perf_counter() - start_wait
        if isinstance(choice, int) and 0 <= choice < len(valid_boxes):
            return valid_boxes[choice], time.perf_counter() - start_wait
        return None, time.perf_counter() - start_wait
    else:
        # Fallback GUI window for interactive local execution
        window_title = f"Selection Required - {frame_name}"
        cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_title, 1280, 720)
        cv2.imshow(window_title, preview_img)

        while True:
            key = cv2.waitKey(50) & 0xFF
            if cv2.getWindowProperty(window_title, cv2.WND_PROP_VISIBLE) < 1 or key == ord("s"):
                cv2.destroyWindow(window_title)
                cv2.waitKey(1)
                return None, time.perf_counter() - start_wait

            elif ord("0") <= key <= ord("9"):
                idx = int(chr(key))
                if 0 <= idx < len(valid_boxes):
                    cv2.destroyWindow(window_title)
                    cv2.waitKey(1)
                    return valid_boxes[idx], time.perf_counter() - start_wait


def run_remove_background(
    manifest_path: str | Path,
    yoloe_model_size: str,
    iou_threshold: float,
    drift_limit: int,
    force: bool = False,
    action_cb=None,
    progress_cb=None,
    log_cb=None,
    is_cancelled=None,
):
    def log(msg: str):
        if log_cb:
            log_cb(msg)
        else:
            print(f"[*] {msg}")

    def progress(val: float, label: str):
        if progress_cb:
            progress_cb(2, val, label)

    def check_cancel():
        if is_cancelled and is_cancelled():
            raise RuntimeError("Pipeline cancelled by user during Phase 2 (Masking)")

    manifest_path = Path(manifest_path).resolve()
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    input_dir = Path(manifest["paths"]["raw_frames"]).resolve()
    output_dir = Path(manifest["paths"]["masked_frames"]).resolve()
    temp_dir = output_dir / "temp"

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    source_images = sorted(
        [f for f in input_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS]
    )
    total_frames = len(source_images)

    # --- SKIP LOGIC ---
    if output_dir.exists() and not force:
        existing_masks = [f for f in output_dir.iterdir() if f.suffix.lower() == ".png"]
        if len(existing_masks) == total_frames and total_frames > 0:
            log(f"Found {len(existing_masks)} existing masked frames in {output_dir}.")
            log("Skipping background removal phase...")

            manifest["status"]["phase"] = 2
            if "masking" not in manifest["status"]["completed"]:
                manifest["status"]["completed"].append("masking")
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=4)

            progress(1.0, "Phase 2: Masking complete (cached)")
            return

    if force and output_dir.exists():
        log(f"Force flag detected. Wiping: {output_dir}")
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    target_min_frames = manifest["settings"].get("minimum_frames", 45)
    log("Starting Background Removal Phase.")
    log(f"[*] Total Frames Found in Workspace: {total_frames} (Target Minimum: {target_min_frames})")

    device = (
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )

    detector = YOLOE(str(MODELS_DIR / f"yoloe-26{yoloe_model_size}-seg-pf.pt"))
    segmenter = SAM(str(MODELS_DIR / "sam2.1_s.pt"))

    start_perf = time.perf_counter()
    total_user_time = 0.0
    prev_box = None

    for i, img_path in enumerate(source_images):
        check_cancel()
        current_frame_number = i + 1
        progress_fraction = current_frame_number / max(1, total_frames)

        progress(
            progress_fraction,
            f"Processing frame {current_frame_number} of {total_frames}",
        )

        img = cv2.imread(str(img_path))
        if img is None:
            continue

        h_img, w_img = img.shape[:2]
        img_area = h_img * w_img
        target_path = output_dir / f"{img_path.stem}.png"

        det_results = detector.predict(
            source=img, conf=0.25, device=device, verbose=False
        )[0]
        valid_boxes = []

        if det_results.boxes is not None:
            for box in det_results.boxes:
                coords = box.xyxy[0].cpu().numpy()
                box_area = (coords[2] - coords[0]) * (coords[3] - coords[1])
                if (box_area / img_area) < 0.70:
                    valid_boxes.append(coords.tolist())

        chosen_box = None
        if prev_box is None:
            chosen_box, wait_time = get_user_selection(
                img, detector, temp_dir, img_path.stem, device, action_cb, log_cb
            )
            total_user_time += wait_time
        elif valid_boxes:
            best_iou = -1.0
            best_match = None

            for candidate in valid_boxes:
                iou = calculate_iou(prev_box, candidate)
                drift = calculate_centroid_drift(prev_box, candidate)

                if iou > iou_threshold and drift < drift_limit:
                    if iou > best_iou:
                        best_iou = iou
                        best_match = candidate

            if best_match is not None:
                chosen_box = best_match
            else:
                log(f"Tracking signature broke on {img_path.name} (Limits violated).")
                chosen_box, wait_time = get_user_selection(
                    img, detector, temp_dir, img_path.stem, device, action_cb, log_cb
                )
                total_user_time += wait_time
        else:
            chosen_box, wait_time = get_user_selection(
                img, detector, temp_dir, img_path.stem, device, action_cb, log_cb
            )
            total_user_time += wait_time

        if chosen_box is None:
            cv2.imwrite(str(target_path), np.zeros((h_img, w_img, 4), dtype=np.uint8))
            prev_box = None
            continue

        prev_box = chosen_box

        box_w, box_h = chosen_box[2] - chosen_box[0], chosen_box[3] - chosen_box[1]
        pad_x, pad_y = box_w * 0.08, box_h * 0.08
        padded_box = [
            max(0, chosen_box[0] - pad_x),
            max(0, chosen_box[1] - pad_y),
            min(w_img, chosen_box[2] + pad_x),
            min(h_img, chosen_box[3] + pad_y),
        ]

        try:
            sam_results = segmenter.predict(
                source=img, bboxes=[padded_box], device=device, verbose=False
            )[0]
        except Exception as e:
            log(f"[!] SAM failed on {img_path.name}: {e}")
            sam_results = None

        if sam_results is not None and sam_results.masks is not None and len(sam_results.masks.data) > 0:
            mask_np = sam_results.masks.data[0].cpu().numpy()
            mask_resized = cv2.resize(
                (mask_np > 0).astype(np.uint8) * 255,
                (w_img, h_img),
                interpolation=cv2.INTER_NEAREST,
            )

            bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
            bgra[:, :, :3] = cv2.bitwise_and(
                bgra[:, :, :3], bgra[:, :, :3], mask=mask_resized
            )
            bgra[mask_resized == 0, :3] = 255
            bgra[:, :, 3] = mask_resized

            cv2.imwrite(str(target_path), bgra)
        else:
            cv2.imwrite(str(target_path), np.zeros((h_img, w_img, 4), dtype=np.uint8))
            prev_box = None

    total_time = time.perf_counter() - start_perf
    processing_time = total_time - total_user_time

    manifest["status"]["phase"] = 2
    if "masking" not in manifest["status"]["completed"]:
        manifest["status"]["completed"].append("masking")

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    log(f"Complete. Filtered segmentation masks saved to: {output_dir}")
    log(f"Total Gross Session Duration: {total_time:.2f}s")
    log(f"Total User Interaction Hold Time: {total_user_time:.2f}s")
    log(f"Pure AI Processing Execution Speed: {processing_time:.2f}s")
    progress(1.0, "Phase 2: Masking complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--yoloe_model_size", type=str, choices=["n", "s", "m", "l", "x"], default="s"
    )
    parser.add_argument("--iou_threshold", type=float, required=True)
    parser.add_argument("--drift_limit", type=int, required=True)
    parser.add_argument("--ipc", action="store_true")

    args = parser.parse_args()
    run_remove_background(
        args.manifest,
        yoloe_model_size=args.yoloe_model_size,
        iou_threshold=args.iou_threshold,
        drift_limit=args.drift_limit,
        force=args.force,
    )
