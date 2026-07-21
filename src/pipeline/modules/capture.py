import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import cv2

core_path = str(Path(__file__).resolve().parent.parent / "core")
sys.path.insert(0, core_path)

from ipc import send, send_progress, send_log, status_update, status_error

MODULE_PATH = Path(__file__).resolve()
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def run_capture(manifest_path, is_image_mode=False, is_video_mode=False, force=False, ipc_mode=False):
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    input_source = Path(manifest["input_source"]).resolve()
    output_dir = Path(manifest["paths"]["raw_frames"]).resolve()

    if not input_source.exists():
        status_error(f"Input not found: {input_source}")
        sys.exit(1)

    # --- SKIP LOGIC ---
    if output_dir.exists() and not force:
        existing_frames = [
            f for f in output_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS
        ]
        if len(existing_frames) > 0:
            status_update(f"Found {len(existing_frames)} existing frames in {output_dir}.")
            status_update("Skipping capture phase...")

            # Ensure the manifest is correctly updated even when skipping
            manifest["status"]["phase"] = 1
            if "capture" not in manifest["status"]["completed"]:
                manifest["status"]["completed"].append("capture")
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=4)

            print("\nPROGRESS: 100")
            status_update("Phase 1: Capture complete", progress=1.0, phase=1)

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

    # ==========================================
    # IMAGE MODE LOGIC
    # ==========================================
    if is_image_mode:
        status_update("Image directory source detected. Copying frames to workspace...")

        source_images = sorted(
            [f for f in input_source.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS]
        )

        if len(source_images) == 0:
            status_error(f"Error: No valid images found in {input_source}")
            sys.exit(1)

        for i, img_path in enumerate(source_images):
            target_path = output_dir / f"frame_{i:04d}{img_path.suffix}"
            shutil.copy2(img_path, target_path)

        manifest["settings"]["source_type"] = "image"
        status_update(f"Transferred {len(source_images)} frames to capture directory.")
        if len(source_images) < target_min_frames:
            status_error(f"[!] WARNING: Dataset size ({len(source_images)}) is lower than requested minimum ({target_min_frames}).")
        print("PROGRESS: 100")

    # ==========================================
    # VIDEO MODE LOGIC (Dynamic Downsampling)
    # ==========================================
    elif is_video_mode:
        cap = cv2.VideoCapture(str(input_source))
        if not cap.isOpened():
            status_error(f"Could not open video file: {input_source}")
            sys.exit(1)

        total_frames_in = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Calculate optimal skip index step based on required target frame constraint
        frame_skip = max(1, total_frames_in // target_min_frames)

        status_update(f"Total Video Frames: {total_frames_in} | Targeted Minimum Dataset: {target_min_frames}")
        status_update(f"Extracting every {frame_skip} frames directly to PNG...")

        frame_idx = 0
        saved_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_skip == 0:
                target_path = output_dir / f"frame_{saved_count:04d}.png"
                cv2.imwrite(str(target_path), frame)
                saved_count += 1

            if frame_idx % 30 == 0:
                #print(f"PROGRESS: {int((frame_idx / total_frames_in) * 100)}")
               # sys.stdout.flush()
                
                if ipc_mode:
                    send_progress(
                        frame_idx / total_frames_in,
                        f"Extracting frame {saved_count} of ~{target_min_frames}",
                        phase=1
                    )

            frame_idx += 1

        status_update(f"Successfully extracted {saved_count} frames to capture directory.")

        cap.release()
        manifest["settings"]["source_type"] = "video"

    total_time = time.perf_counter() - start_perf

    manifest["status"]["phase"] = 1
    if "capture" not in manifest["status"]["completed"]:
        manifest["status"]["completed"].append("capture")

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    status_update(f"Total Extraction Time: {total_time:.2f}s",
                    1.0,
                    "Phase 1: Capture complete",
                    phase=1)


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
        ipc_mode=args.ipc
    )
    