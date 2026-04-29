import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

# DIRECTORY RESOLUTION
MODULE_PATH = Path(__file__).resolve()  # /src/pipeline/modules/capture.py
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent
if sys.platform == "darwin":
    PLATFORM_SUBFOLDER = "mac_arm"
    BINARY_EXT = ""
elif sys.platform == "win32":
    PLATFORM_SUBFOLDER = "win_x64"
    BINARY_EXT = ".exe"
VENDOR_FFMPEG_DIR = (
    PROJECT_ROOT / "vendor" / "ffmpeg" / PLATFORM_SUBFOLDER / f"ffmpeg{BINARY_EXT}"
)  # /vendor/ffmpeg/PLATFORM_SUBFOLDER/ffmpeg(.exe)
VENDOR_FFPROBE_DIR = (
    PROJECT_ROOT / "vendor" / "ffmpeg" / PLATFORM_SUBFOLDER / f"ffprobe{BINARY_EXT}"
)  # /vendor/ffmpeg/PLATFORM_SUBFOLDER/ffprobe(.exe)

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')

def get_video_duration(video_path):
    """Uses vendored ffprobe to get duration in seconds."""
    cmd = [
        str(VENDOR_FFPROBE_DIR),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[!] ffprobe error: {e}")
        return 0.0


def run_capture(manifest_path, force=False):
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

    # --- Image Folder Detection Logic ---
    if input_source.is_dir():
        print(f"[*] Input is a directory. Processing as image sequence: {input_source}")
        
        # Get sorted list of images
        source_images = sorted([
            f for f in input_source.iterdir() 
            if f.suffix.lower() in IMAGE_EXTENSIONS
        ])
        
        total_source = len(source_images)
        if total_source == 0:
            print(f"[!] Error: No valid images found in {input_source}")
            sys.exit(1)

        print(f"[*] Found {total_source} images. Copying to output...")
        
        for i, img_path in enumerate(source_images):
            # Format filename to match FFmpeg style: frame_0001.jpg
            target_name = f"frame_{i+1:04d}.jpg"
            shutil.copy2(img_path, output_dir / target_name)
            
            # Progress tracking
            if i % 5 == 0 or i == total_source - 1:
                percent = int(((i + 1) / total_source) * 100)
                print(f"PROGRESS: {percent}")
                sys.stdout.flush()
        
        print("[*] Image copy complete.")
        print("PROGRESS: 100")
        return
    # --- End Image Folder Detection ---

    duration = get_video_duration(input_source)
    total_expected_frames = int(duration * target_fps)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 3. Check if we already have the frames we need
    existing_frame_count = len(list(output_dir.glob("*.jpg")))

    if total_expected_frames > 0:
        print(f"[*] Found {existing_frame_count} existing frames in {output_dir}.")
        if existing_frame_count >= total_expected_frames:
            print(f"[*] Expected ~{total_expected_frames}. Skipping extraction phase.")
            print("PROGRESS: 100")
            return

    # 4. Extraction Logic
    start_perf = time.perf_counter()

    ffmpeg_cmd = [
        str(VENDOR_FFMPEG_DIR),
        "-i",
        str(input_source),
        "-vf",
        f"fps={target_fps}",
        "-q:v",
        "2",
        str(output_dir / "frame_%04d.jpg"),
        "-y",
    ]

    print(f"[*] Extracting frames to: {output_dir}")

    process = subprocess.Popen(
        ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    last_count = 0
    while process.poll() is None:
        current_count = len(list(output_dir.glob("*.jpg")))

        if current_count > last_count:
            last_count = current_count
            if total_expected_frames > 0:
                percent = min(int((current_count / total_expected_frames) * 100), 99)
                print(f"PROGRESS: {percent}")
                sys.stdout.flush()

        time.sleep(0.1)

    print("PROGRESS: 100")

    end_perf = time.perf_counter()
    total_time = end_perf - start_perf
    final_frame_count = len(list(output_dir.glob("*.jpg")))

    if total_time > 0:
        extraction_speed = final_frame_count / total_time
    else:
        extraction_speed = 0

    print("[*] Capture Phase Complete.")
    print(f"[*] Total Frames: {final_frame_count} frames")
    print(f"[*] Total Time: {total_time:.2f}s")
    print(f"[*] Extraction Speed: {extraction_speed:.2f} frames/sec")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run_capture(args.manifest, force=args.force)
