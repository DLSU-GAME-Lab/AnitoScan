import argparse
import gc
import shutil
import sys
import time
from collections.abc import Generator
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics.models.sam import SAM
from ultralytics.models.yolo import YOLOE

core_path = str(Path(__file__).resolve().parent.parent / "core")
sys.path.insert(0, core_path)

from benchmark import append_failed_phase_benchmark, append_phase_benchmark
from cancellation import PipelineCancelled, check_cancelled
from log import log_error, log_info, log_progress, set_ipc_mode, set_phase
from manifest import load_manifest, update_manifest

MODULE_PATH = Path(__file__).resolve()
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models" / "02_masking"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def _release_accelerator_memory() -> None:
    """Release masking allocations before the separate 2DGS process starts."""
    gc.collect()
    try:
        if torch.cuda.is_available():
            reserved_before = torch.cuda.memory_reserved()
            torch.cuda.empty_cache()
            reserved_after = torch.cuda.memory_reserved()
            released_mib = max(0, reserved_before - reserved_after) / (1024 * 1024)
            log_info(f"Released {released_mib:.0f} MiB of cached CUDA memory after masking")
        elif (
            hasattr(torch, "mps")
            and hasattr(torch.mps, "empty_cache")
            and torch.backends.mps.is_available()
        ):
            torch.mps.empty_cache()
    except RuntimeError as error:
        log_info(f"Could not release cached accelerator memory: {error}")


def _calculate_iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA + 1) * max(0, yB - yA + 1)
    boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
    boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)
    iou = interArea / float(boxAArea + boxBArea - interArea)
    return iou


def _calculate_centroid_drift(boxA, boxB):
    centerA = np.array([(boxA[0] + boxA[2]) / 2, (boxA[1] + boxA[3]) / 2])
    centerB = np.array([(boxB[0] + boxB[2]) / 2, (boxB[1] + boxB[3]) / 2])
    return np.linalg.norm(centerA - centerB)


def _get_user_selection(img, detector, temp_dir, frame_name, device, cancel_event=None):
    """Yields an intervention request to the pipeline orchestrator."""
    check_cancelled(cancel_event)
    start_wait = time.perf_counter()
    log_info(f"Running YOLOE-26 on {frame_name}...")
    results = detector.predict(source=img, conf=0.35, device=device, verbose=False)[0]
    check_cancelled(cancel_event)

    if results.boxes is None or len(results.boxes) == 0:
        log_error("YOLOE found no valid subjects in this frame.")
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
    overlay = img.copy()  # Create an overlay for transparency

    # Distinct high-contrast colors in BGR format
    palette = [
        (0, 255, 0),  # Bright Green
        (255, 255, 0),  # Cyan
        (0, 0, 255),  # Pure Red
        (255, 0, 255),  # Magenta
        (0, 165, 255),  # Orange
        (255, 0, 0),  # Pure Blue
        (0, 255, 255),  # Bright Yellow
        (140, 0, 140),  # Dark Purple
    ]

    # Store label positions to prevent overlapping text
    drawn_labels = []

    for idx, coords in enumerate(valid_boxes):
        x1, y1, x2, y2 = map(int, coords)

        # Select a unique color from the palette based on index
        color = palette[idx % len(palette)]

        # 1. Draw the semi-transparent box
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)

        # 2. Collision detection for the label
        label_y = y1
        shift_amount = 35  # Height of the label background + padding

        # Check if this new label is going to collide with any existing label
        while any(
            abs(label_y - dy) < shift_amount and abs(x1 - dx) < 40
            for dx, dy in drawn_labels
        ):
            label_y += shift_amount  # Push it down below the colliding label

        # Keep track of where we are putting this one
        drawn_labels.append((x1, label_y))

        # 3. Draw the dynamic color label background and text on the overlay
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

    # Blend the overlay with the original image (60% opacity for the boxes/labels)
    alpha = 0.6
    cv2.addWeighted(overlay, alpha, preview_img, 1 - alpha, 0, preview_img)

    check_cancelled(cancel_event)
    temp_dir.mkdir(parents=True, exist_ok=True)
    preview_path = temp_dir / f"{frame_name}_candidates.png"

    write_success = cv2.imwrite(str(preview_path), preview_img)
    if not write_success:
        raise RuntimeError(
            f"OpenCV failed to write the preview image to: {preview_path}"
        )

    check_cancelled(cancel_event)
    choice, wait_time = (yield {
        "type": "SELECTION_REQUIRED",
        "preview_path": str(preview_path),
        "total_candidates": len(valid_boxes),
        "frame_name": frame_name,
    })
    check_cancelled(cancel_event)

    if choice is not None and 0 <= choice < len(valid_boxes):
        return valid_boxes[choice], wait_time

    return None, wait_time


def run_remove_background(
    manifest_path_string, yoloe_model_size, iou_threshold, drift_limit,
    force=False, ipc_mode=False, cancel_event=None
) -> Generator[dict, tuple[int | None, float], None]:
    set_ipc_mode(ipc_mode)
    set_phase(phase=2)
    check_cancelled(cancel_event)

    manifest_path, manifest = load_manifest(manifest_path_string)
    phase_start = time.perf_counter()

    input_dir = Path(manifest["paths"]["raw_frames"]).resolve()
    output_dir = Path(manifest["paths"]["masked_frames"]).resolve()
    temp_dir = output_dir / "temp"
    benchmark_settings = {
        "force": force,
        "yoloe_model_size": yoloe_model_size,
        "iou_threshold": iou_threshold,
        "drift_limit": drift_limit,
        "device": "unknown",
    }
    benchmark_paths = {"input_dir": input_dir, "output_dir": output_dir}
    benchmark_metrics = {
        "input_frames": 0,
        "output_masks": 0,
        "successful_masks": 0,
        "blank_masks": 0,
        "unreadable_frames": 0,
        "user_selection_requests": 0,
        "user_skip_or_failed_selection_count": 0,
        "tracking_breaks": 0,
        "sam_failures": 0,
        "processed_frames": 0,
        "total_user_interaction_seconds": 0.0,
        "ai_processing_seconds": 0.0,
    }

    if not input_dir.exists():
        error = RuntimeError(f"Input directory not found: {input_dir}")
        append_failed_phase_benchmark(
            manifest,
            2,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        raise error

    source_images = sorted(
        [f for f in input_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS]
    )
    total_frames = len(source_images)
    benchmark_metrics["input_frames"] = total_frames


    # --- SKIP LOGIC ---
    check_cancelled(cancel_event)
    if output_dir.exists() and not force:
        existing_masks = [f for f in output_dir.iterdir() if f.suffix.lower() == ".png"]
        if len(existing_masks) == total_frames and total_frames > 0:
            log_info(f"Found {len(existing_masks)} existing masked frames in {output_dir}.")
            log_info("Skipping Masking phase...")

            check_cancelled(cancel_event)
            update_manifest(manifest_path, manifest, phase=2)
            append_phase_benchmark(
                manifest,
                2,
                status="skipped",
                skipped=True,
                duration_seconds=time.perf_counter() - phase_start,
                settings={
                    "force": force,
                    "yoloe_model_size": yoloe_model_size,
                    "iou_threshold": iou_threshold,
                    "drift_limit": drift_limit,
                },
                metrics={
                    "input_frames": total_frames,
                    "existing_masks": len(existing_masks),
                    "output_masks": len(existing_masks),
                },
                paths={"input_dir": input_dir, "output_dir": output_dir},
            )

            log_info("Phase 2: Masking complete")
            log_progress(value=1.0, label="Masking phase skipped")

            return
    # -----------------------

    check_cancelled(cancel_event)
    if force and output_dir.exists():
        log_info(f"Force flag detected. Wiping: {output_dir}")
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    target_min_frames = manifest["settings"].get("minimum_frames", 45)

    log_info("Starting Masking Phase.")
    log_info(f"Total Frames Found in Workspace: {total_frames} (Target Minimum: {target_min_frames})")

    device = (
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )
    benchmark_settings["device"] = device

    detector = None
    segmenter = None
    try:
        check_cancelled(cancel_event)
        detector = YOLOE(str(MODELS_DIR / f"yoloe-26{yoloe_model_size}-seg-pf.pt"))
        check_cancelled(cancel_event)
        segmenter = SAM(str(MODELS_DIR / "sam2.1_s.pt"))
        check_cancelled(cancel_event)
    except (RuntimeError, ValueError, OSError) as error:
        detector = None
        segmenter = None
        _release_accelerator_memory()
        append_failed_phase_benchmark(
            manifest,
            2,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        raise

    start_perf = time.perf_counter()
    total_user_time = 0.0  # Tracks elapsed human intervention overhead
    user_selection_requests = 0
    user_skip_or_failed_selection_count = 0
    blank_mask_count = 0
    successful_mask_count = 0
    unreadable_frame_count = 0
    tracking_break_count = 0
    sam_failure_count = 0
    prev_box = None

    total_imgs = len(source_images)
    det_results = None
    sam_results = None
    try:
        for i, img_path in enumerate(source_images):
            check_cancelled(cancel_event)
            benchmark_metrics["processed_frames"] = i
            img = cv2.imread(str(img_path))
            check_cancelled(cancel_event)
            if img is None:
                unreadable_frame_count += 1
                benchmark_metrics["unreadable_frames"] = unreadable_frame_count
                continue

            h_img, w_img = img.shape[:2]
            img_area = h_img * w_img
            target_path = output_dir / f"{img_path.stem}.png"

            # 1. YOLOE Bounding Box Prediction
            check_cancelled(cancel_event)
            det_results = detector.predict(
                source=img, conf=0.25, device=device, verbose=False
            )[0]
            check_cancelled(cancel_event)
            valid_boxes = []

            if det_results.boxes is not None:
                for box in det_results.boxes:
                    check_cancelled(cancel_event)
                    coords = box.xyxy[0].cpu().numpy()
                    box_area = (coords[2] - coords[0]) * (coords[3] - coords[1])
                    if (box_area / img_area) < 0.70:
                        valid_boxes.append(coords.tolist())

            # 2. Strict Math Validation Heuristics (IoU & Drift Boundary Gates)
            chosen_box = None
            if prev_box is None:
                # First frame initialization anchor configuration
                user_selection_requests += 1
                benchmark_metrics["user_selection_requests"] = user_selection_requests
                chosen_box, wait_time = yield from _get_user_selection(
                    img, detector, temp_dir, img_path.stem, device, cancel_event
                )
                check_cancelled(cancel_event)
                total_user_time += wait_time
                benchmark_metrics["total_user_interaction_seconds"] = total_user_time
            elif valid_boxes:
                best_iou = -1.0
                best_match = None

                for candidate in valid_boxes:
                    check_cancelled(cancel_event)
                    iou = _calculate_iou(prev_box, candidate)
                    drift = _calculate_centroid_drift(prev_box, candidate)

                    if iou > iou_threshold and drift < drift_limit and iou > best_iou:
                        best_iou = iou
                        best_match = candidate

                if best_match is not None:
                    chosen_box = best_match
                else:
                    print("\n")
                    tracking_break_count += 1
                    benchmark_metrics["tracking_breaks"] = tracking_break_count
                    log_error(f"Tracking signature broke on {img_path.name} (Strict limits violated).")
                    user_selection_requests += 1
                    benchmark_metrics["user_selection_requests"] = user_selection_requests
                    chosen_box, wait_time = yield from _get_user_selection(
                        img, detector, temp_dir, img_path.stem, device, cancel_event
                    )
                    check_cancelled(cancel_event)
                    total_user_time += wait_time
                    benchmark_metrics["total_user_interaction_seconds"] = total_user_time
            else:
                user_selection_requests += 1
                benchmark_metrics["user_selection_requests"] = user_selection_requests
                chosen_box, wait_time = yield from _get_user_selection(
                    img, detector, temp_dir, img_path.stem, device, cancel_event
                )
                check_cancelled(cancel_event)
                total_user_time += wait_time
                benchmark_metrics["total_user_interaction_seconds"] = total_user_time

            # If skipped or failed, write zeroed blank structural mask frame matching target shape
            if chosen_box is None:
                check_cancelled(cancel_event)
                cv2.imwrite(str(target_path), np.zeros((h_img, w_img, 4), dtype=np.uint8))
                blank_mask_count += 1
                user_skip_or_failed_selection_count += 1
                benchmark_metrics["blank_masks"] = blank_mask_count
                benchmark_metrics["user_skip_or_failed_selection_count"] = user_skip_or_failed_selection_count
                prev_box = None
                benchmark_metrics["processed_frames"] = i + 1
                continue

            prev_box = chosen_box

            # 3. Static Segment Anything Model Extraction
            box_w, box_h = chosen_box[2] - chosen_box[0], chosen_box[3] - chosen_box[1]
            pad_x, pad_y = box_w * 0.08, box_h * 0.08
            padded_box = [
                max(0, chosen_box[0] - pad_x),
                max(0, chosen_box[1] - pad_y),
                min(w_img, chosen_box[2] + pad_x),
                min(h_img, chosen_box[3] + pad_y),
            ]

            try:
                check_cancelled(cancel_event)
                sam_results = segmenter.predict(
                    source=img, bboxes=[padded_box], device=device, verbose=False
                )[0]
                check_cancelled(cancel_event)
            except (RuntimeError, ValueError, OSError) as e:
                log_info(f"[!] SAM failed on {img_path.name}: {e}")
                sam_failure_count += 1
                benchmark_metrics["sam_failures"] = sam_failure_count
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

                # executor.submit(cv2.imwrite, str(target_path), bgra)
                check_cancelled(cancel_event)
                cv2.imwrite(str(target_path), bgra)
                successful_mask_count += 1
                benchmark_metrics["successful_masks"] = successful_mask_count
            else:
                check_cancelled(cancel_event)
                cv2.imwrite(str(target_path), np.zeros((h_img, w_img, 4), dtype=np.uint8))
                blank_mask_count += 1
                benchmark_metrics["blank_masks"] = blank_mask_count
                prev_box = None

            benchmark_metrics["processed_frames"] = i + 1
            if i % 5 == 0 or i == total_imgs - 1:
                log_progress(value=(i+1)/total_imgs, label=f"Processed frame {i+1}/{total_imgs}")
    except PipelineCancelled:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise
    except (RuntimeError, ValueError, OSError, cv2.error) as error:
        output_mask_count = len([f for f in output_dir.iterdir() if f.suffix.lower() == ".png"])
        benchmark_metrics["output_masks"] = output_mask_count
        benchmark_metrics["ai_processing_seconds"] = max(
            0.0, time.perf_counter() - start_perf - total_user_time
        )
        append_failed_phase_benchmark(
            manifest,
            2,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise
    finally:
        detector = None
        segmenter = None
        det_results = None
        sam_results = None
        _release_accelerator_memory()

    total_time = time.perf_counter() - start_perf
    processing_time = total_time - total_user_time

    output_mask_count = len([f for f in output_dir.iterdir() if f.suffix.lower() == ".png"])

    check_cancelled(cancel_event)
    update_manifest(manifest_path, manifest, phase=2)
    append_phase_benchmark(
        manifest,
        2,
        status="completed",
        skipped=False,
        duration_seconds=total_time,
        settings={
            "force": force,
            "yoloe_model_size": yoloe_model_size,
            "iou_threshold": iou_threshold,
            "drift_limit": drift_limit,
            "device": device,
        },
        metrics={
            "input_frames": total_frames,
            "output_masks": output_mask_count,
            "successful_masks": successful_mask_count,
            "blank_masks": blank_mask_count,
            "unreadable_frames": unreadable_frame_count,
            "user_selection_requests": user_selection_requests,
            "user_skip_or_failed_selection_count": user_skip_or_failed_selection_count,
            "tracking_breaks": tracking_break_count,
            "sam_failures": sam_failure_count,
            "processed_frames": benchmark_metrics["processed_frames"],
            "total_user_interaction_seconds": total_user_time,
            "ai_processing_seconds": processing_time,
        },
        paths={"input_dir": input_dir, "output_dir": output_dir},
    )

    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    log_info(f"Complete. Filtered segmentation masks saved to: {output_dir}")
    log_info(f"Total Gross Session Duration: {total_time:.2f}s")
    log_info(f"Total User Interaction Hold Time: {total_user_time:.2f}s")
    log_info(f"Pure AI Processing Execution Speed: {processing_time:.2f}s")
    log_progress(value=1.0, label="Phase 2: Masking complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--yoloe_model_size", type=str, choices=["n", "s", "m", "l", "x"], default="s")
    parser.add_argument("--iou_threshold", type=float, required=True)
    parser.add_argument("--drift_limit", type=int, required=True)
    parser.add_argument("--ipc", action="store_true")
    args = parser.parse_args()

    gen = run_remove_background(
        args.manifest,
        yoloe_model_size=args.yoloe_model_size,
        iou_threshold=args.iou_threshold,
        drift_limit=args.drift_limit,
        force=args.force,
        ipc_mode=args.ipc
    )

    try:
        request = next(gen)
        while True:
            if request["type"] == "SELECTION_REQUIRED":
                start_wait = time.perf_counter()

                window_title = f"Selection Required - {request['frame_name']}"
                cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(window_title, 1280, 720)

                preview_img = cv2.imread(request["preview_path"])
                cv2.imshow(window_title, preview_img)

                print("\n==================================================")
                print(" ACTION REQUIRED: Click on the image window to focus it.")
                print(f" Press the number key (0-{request['total_candidates'] - 1}) corresponding to the correct subject.")
                print(" Press 's' to skip this frame.")
                print("==================================================")

                choice = None
                while True:
                    key = cv2.waitKey(50) & 0xFF
                    if cv2.getWindowProperty(window_title, cv2.WND_PROP_VISIBLE) < 1:
                        break
                    if key == ord("s"):
                        break
                    elif ord("0") <= key <= ord("9"):
                        idx = int(chr(key))
                        if 0 <= idx < request["total_candidates"]:
                            choice = idx
                            break

                cv2.destroyWindow(window_title)
                cv2.waitKey(1)

                wait_time = time.perf_counter() - start_wait
                request = gen.send((choice, wait_time))

    except StopIteration:
        pass
    except (RuntimeError, ValueError, OSError) as error:
        log_error(str(error))
        sys.exit(1)
