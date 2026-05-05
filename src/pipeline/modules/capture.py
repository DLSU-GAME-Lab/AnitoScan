import argparse
import json
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2

# DIRECTORY RESOLUTION
MODULE_PATH = Path(__file__).resolve()
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def run_capture(
    manifest_path, blur_threshold, proxy_width, jpg_quality, max_search, force=False
):
    # 1. Load Manifest
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    input_source = Path(manifest["input_source"])
    output_dir = Path(manifest["paths"]["raw_frames"])
    target_fps = manifest["settings"]["requested_fps"]

    # 2. Preparation & Validation
    if not input_source.exists():
        print(f"[!] Input not found: {input_source}")
        sys.exit(1)

    if force and output_dir.exists():
        print(f"[!] Force flag detected. Wiping: {output_dir}")
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Skip Logic: Check if frames already exist ---
    existing_frames = [
        f for f in output_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS
    ]
    if len(existing_frames) > 0 and not force:
        print(
            f"[*] Found {len(existing_frames)} existing frames in {output_dir}. Skipping capture phase."
        )
        print("PROGRESS: 100")
        return

    # --- Image Folder Detection Logic ---
    if input_source.is_dir():
        print(f"[*] Input is a directory. Processing as image sequence: {input_source}")
        source_images = sorted(
            [f for f in input_source.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS]
        )

        total_source = len(source_images)
        if total_source == 0:
            print(f"[!] Error: No valid images found in {input_source}")
            sys.exit(1)

        print(f"[*] Found {total_source} images. Copying to output...")
        for i, img_path in enumerate(source_images):
            target_name = f"frame_{i + 1:04d}.jpg"
            shutil.copy2(img_path, output_dir / target_name)
            if i % 5 == 0 or i == total_source - 1:
                percent = int(((i + 1) / total_source) * 100)
                print(f"PROGRESS: {percent}")
                sys.stdout.flush()
        print("PROGRESS: 100")
        return

    # 3. OpenCV Video Capture
    cap = cv2.VideoCapture(str(input_source))
    if not cap.isOpened():
        print(f"[!] Could not open video: {input_source}")
        sys.exit(1)

    fps_in = cap.get(cv2.CAP_PROP_FPS)
    total_frames_in = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    sample_interval = max(1, int(fps_in / target_fps))

    print(
        f"[*] Extracting (Target: {target_fps} FPS | Threshold: {blur_threshold} | Proxy: {proxy_width}px | Quality: {jpg_quality} | Max Search: {max_search} adjacent frames)"
    )

    # 4. Extraction Loop
    start_perf = time.perf_counter()
    saved_count = 0
    frame_idx = 0
    saved_blurry = 0
    last_percent = -1

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    executor = ThreadPoolExecutor(max_workers=4)

    while True:
        if frame_idx % sample_interval != 0:
            if not cap.grab():
                break
            frame_idx += 1
            continue

        ret, frame = cap.read()
        if not ret:
            break

        best_frame = frame
        best_score = -1.0
        found_sharp = False

        # Search Window
        for search_offset in range(max_search):
            if search_offset > 0:
                ret, frame = cap.read()
                frame_idx += 1
                if not ret:
                    break

            # Proxy Resize Logic
            h, w = frame.shape[:2]
            aspect = h / w
            proxy_dim = (proxy_width, int(proxy_width * aspect))

            # Calculate sharpness on proxy
            gray = cv2.resize(
                cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                proxy_dim,
                interpolation=cv2.INTER_NEAREST,
            )
            enhanced_gray = clahe.apply(gray)
            score = cv2.Laplacian(enhanced_gray, cv2.CV_64F).var()

            if score > best_score:
                best_score = score
                best_frame = frame.copy()

            if score >= blur_threshold:
                found_sharp = True
                break

        saved_count += 1
        target_name = f"frame_{saved_count:04d}.jpg"
        target_path = str(output_dir / target_name)

        # Threaded Save
        executor.submit(
            cv2.imwrite,
            target_path,
            best_frame,
            [cv2.IMWRITE_JPEG_QUALITY, jpg_quality],
        )

        if not found_sharp:
            saved_blurry += 1

        # Progress Tracking
        current_percent = min(int((frame_idx / total_frames_in) * 100), 99)
        if current_percent >= last_percent + 5:
            print(f"PROGRESS: {current_percent}")
            sys.stdout.flush()
            last_percent = current_percent

        frame_idx += 1

    cap.release()
    executor.shutdown(wait=True)

    total_time = time.perf_counter() - start_perf

    print("PROGRESS: 100")

    # Finalize Manifest
    manifest["status"]["phase"] = 1
    if "spatial" not in manifest["status"]["completed"]:
        manifest["status"]["completed"].append("capture")

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    print("[*] Capture Phase Complete.")
    print(f"[*] Total Saved: {saved_count} frames | Blurry Fallbacks: {saved_blurry}")
    print(f"[*] Speed: {saved_count / total_time:.2f} frames/sec")
    print(f"[*] Total Time: {total_time:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--blur-threshold", type=float)
    parser.add_argument("--proxy-width", type=int)
    parser.add_argument("--jpg-quality", type=int)
    parser.add_argument("--max_search", type=int)

    args = parser.parse_args()

    run_capture(
        args.manifest,
        blur_threshold=args.blur_threshold,
        proxy_width=args.proxy_width,
        jpg_quality=args.jpg_quality,
        max_search=args.max_search,
        force=args.force,
    )
