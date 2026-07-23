from dataclasses import dataclass, field
from pathlib import Path
import shutil
import time
import cv2

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


class RunCancelled(Exception):
    """Raised when pipeline execution is cancelled by user request."""
    pass


@dataclass
class CaptureResult:
    extracted_frames: list[Path] = field(default_factory=list)
    frame_count: int = 0
    source_type: str = "image"


def run_capture(
    input_source: str | Path,
    output_dir: str | Path,
    minimum_frames: int = 45,
    is_image_mode: bool = False,
    is_video_mode: bool = False,
    force: bool = False,
    progress_cb=None,
    log_cb=None,
    check_cancelled=None,
    is_cancelled=None,
) -> CaptureResult:
    def log(msg: str):
        if log_cb:
            log_cb(msg)
        else:
            print(f"[*] {msg}")

    def progress(val: float, label: str):
        if progress_cb:
            progress_cb(val, label)

    def do_check_cancel():
        if check_cancelled:
            check_cancelled()
        elif is_cancelled and is_cancelled():
            raise RunCancelled("Pipeline cancelled by user during Phase 1 (Capture)")

    input_source = Path(input_source).resolve()
    output_dir = Path(output_dir).resolve()

    if not input_source.exists():
        raise FileNotFoundError(f"Input not found: {input_source}")

    # --- SKIP LOGIC (CACHED) ---
    if output_dir.exists() and not force:
        existing_frames = sorted(
            [f for f in output_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS]
        )
        if len(existing_frames) > 0:
            log(f"Found {len(existing_frames)} existing frames in {output_dir}.")
            log("Skipping capture phase...")
            progress(1.0, "Phase 1: Capture complete (cached)")
            return CaptureResult(
                extracted_frames=existing_frames,
                frame_count=len(existing_frames),
                source_type="image" if input_source.is_dir() else "video",
            )

    if force and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start_perf = time.perf_counter()

    if not is_image_mode and not is_video_mode:
        is_image_mode = input_source.is_dir()
        is_video_mode = not input_source.is_dir()

    extracted_frames: list[Path] = []
    source_type = "image" if is_image_mode else "video"

    if is_image_mode:
        log("Image directory source detected. Copying frames to workspace...")
        source_images = sorted(
            [f for f in input_source.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS]
        )

        if len(source_images) == 0:
            raise ValueError(f"No valid images found in {input_source}")

        total_imgs = len(source_images)
        for i, img_path in enumerate(source_images):
            do_check_cancel()
            target_path = output_dir / f"frame_{i:04d}{img_path.suffix}"
            shutil.copy2(img_path, target_path)
            extracted_frames.append(target_path)
            progress((i + 1) / total_imgs, f"Copying frame {i + 1} of {total_imgs}")

        log(f"Transferred {len(source_images)} frames to capture directory.")
        if len(source_images) < minimum_frames:
            log(f"[!] WARNING: Dataset size ({len(source_images)}) is lower than requested minimum ({minimum_frames}).")

    elif is_video_mode:
        cap = cv2.VideoCapture(str(input_source))
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video file: {input_source}")

        total_frames_in = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_skip = max(1, total_frames_in // minimum_frames) if minimum_frames > 0 else 1

        log(f"Total Video Frames: {total_frames_in} | Targeted Minimum Dataset: {minimum_frames}")
        log(f"Extracting every {frame_skip} frames directly to PNG...")

        frame_idx = 0
        saved_count = 0

        while True:
            do_check_cancel()
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_skip == 0:
                target_path = output_dir / f"frame_{saved_count:04d}.png"
                cv2.imwrite(str(target_path), frame)
                extracted_frames.append(target_path)
                saved_count += 1

            if frame_idx % 30 == 0 and total_frames_in > 0:
                frac = frame_idx / total_frames_in
                progress(frac, f"Extracting frame {saved_count} of ~{minimum_frames}")

            frame_idx += 1

        cap.release()
        log(f"Successfully extracted {saved_count} frames to capture directory.")

    total_time = time.perf_counter() - start_perf
    log(f"Total Extraction Time: {total_time:.2f}s")
    progress(1.0, "Phase 1: Capture complete")

    return CaptureResult(
        extracted_frames=extracted_frames,
        frame_count=len(extracted_frames),
        source_type=source_type,
    )
