import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import cv2

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def run_capture(
    manifest_path: str | Path,
    is_image_mode: bool = False,
    is_video_mode: bool = False,
    force: bool = False,
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
            progress_cb(1, val, label)

    def check_cancel():
        if is_cancelled and is_cancelled():
            raise RuntimeError("Pipeline cancelled by user during Phase 1 (Capture)")

    manifest_path = Path(manifest_path).resolve()
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    input_source = Path(manifest["input_source"]).resolve()
    output_dir = Path(manifest["paths"]["raw_frames"]).resolve()

    if not input_source.exists():
        raise FileNotFoundError(f"Input not found: {input_source}")

    # --- SKIP LOGIC ---
    if output_dir.exists() and not force:
        existing_frames = [
            f for f in output_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS
        ]
        if len(existing_frames) > 0:
            log(f"Found {len(existing_frames)} existing frames in {output_dir}.")
            log("Skipping capture phase...")

            manifest["status"]["phase"] = 1
            if "capture" not in manifest["status"]["completed"]:
                manifest["status"]["completed"].append("capture")
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=4)

            progress(1.0, "Phase 1: Capture complete (cached)")
            return
    # -----------------------

    if force and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start_perf = time.perf_counter()

    if not is_image_mode and not is_video_mode:
        is_image_mode = input_source.is_dir()
        is_video_mode = not input_source.is_dir()

    target_min_frames = manifest["settings"].get("minimum_frames", 45)

    if is_image_mode:
        log("Image directory source detected. Copying frames to workspace...")
        source_images = sorted(
            [f for f in input_source.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS]
        )

        if len(source_images) == 0:
            raise ValueError(f"No valid images found in {input_source}")

        for i, img_path in enumerate(source_images):
            check_cancel()
            target_path = output_dir / f"frame_{i:04d}{img_path.suffix}"
            shutil.copy2(img_path, target_path)

        manifest["settings"]["source_type"] = "image"
        log(f"Transferred {len(source_images)} frames to capture directory.")
        if len(source_images) < target_min_frames:
            log(f"[!] WARNING: Dataset size ({len(source_images)}) is lower than requested minimum ({target_min_frames}).")

    elif is_video_mode:
        cap = cv2.VideoCapture(str(input_source))
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video file: {input_source}")

        total_frames_in = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_skip = max(1, total_frames_in // target_min_frames)

        log(f"Total Video Frames: {total_frames_in} | Targeted Minimum Dataset: {target_min_frames}")
        log(f"Extracting every {frame_skip} frames directly to PNG...")

        frame_idx = 0
        saved_count = 0

        while True:
            check_cancel()
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_skip == 0:
                target_path = output_dir / f"frame_{saved_count:04d}.png"
                cv2.imwrite(str(target_path), frame)
                saved_count += 1

            if frame_idx % 30 == 0 and total_frames_in > 0:
                frac = frame_idx / total_frames_in
                progress(frac, f"Extracting frame {saved_count} of ~{target_min_frames}")

            frame_idx += 1

        log(f"Successfully extracted {saved_count} frames to capture directory.")
        cap.release()
        manifest["settings"]["source_type"] = "video"

    total_time = time.perf_counter() - start_perf

    manifest["status"]["phase"] = 1
    if "capture" not in manifest["status"]["completed"]:
        manifest["status"]["completed"].append("capture")

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    log(f"Total Extraction Time: {total_time:.2f}s")
    progress(1.0, "Phase 1: Capture complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--image", action="store_true")
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--blur-threshold", type=float)
    parser.add_argument("--proxy-width", type=int)
    parser.add_argument("--jpg-quality", type=int)
    parser.add_argument("--max_search", type=int)
    parser.add_argument("--ipc", action="store_true")

    args = parser.parse_args()
    run_capture(
        args.manifest,
        is_image_mode=args.image,
        is_video_mode=args.video,
        force=args.force,
    )
