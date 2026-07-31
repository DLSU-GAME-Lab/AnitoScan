import argparse
import shutil
import sys
import time
from pathlib import Path

import cv2

core_path = str(Path(__file__).resolve().parent.parent / "core")
sys.path.insert(0, core_path)

from benchmark import append_failed_phase_benchmark, append_phase_benchmark
from log import log_error, log_info, log_progress, set_ipc_mode, set_phase
from manifest import load_manifest, update_manifest

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def run_capture(manifest_path_string: str, is_image_mode=False, is_video_mode=False, force=False, ipc_mode=False):
    set_ipc_mode(ipc_mode)
    set_phase(phase=1)

    manifest_path, manifest = load_manifest(manifest_path_string)

    input_source = Path(manifest["input_source"]).resolve()
    output_dir = Path(manifest["paths"]["raw_frames"]).resolve()
    start_perf = time.perf_counter()

    if not input_source.exists():
        error = FileNotFoundError(f"Input not found: {input_source}")
        append_failed_phase_benchmark(
            manifest,
            1,
            start_time=start_perf,
            settings={"force": force},
            metrics={},
            paths={"input_source": input_source, "output_dir": output_dir},
            error=error,
        )
        raise error

    if not is_image_mode and not is_video_mode:
        is_image_mode = input_source.is_dir()
        is_video_mode = not input_source.is_dir()

    if "minimum_frames" not in manifest["settings"]:
        error = ValueError("Missing required setting 'minimum_frames' in manifest settings.")
        append_failed_phase_benchmark(
            manifest,
            1,
            start_time=start_perf,
            settings={
                "force": force,
                "source_type": "image" if is_image_mode else "video",
            },
            metrics={},
            paths={"input_source": input_source, "output_dir": output_dir},
            error=error,
        )
        raise error

    target_min_frames = manifest["settings"]["minimum_frames"]
    source_type = "image" if is_image_mode else "video"
    benchmark_settings = {
        "source_type": source_type,
        "minimum_frames": target_min_frames,
        "force": force,
    }
    benchmark_paths = {
        "input_source": input_source,
        "output_dir": output_dir,
    }
    benchmark_metrics = {}

    try:
        # --- SKIP LOGIC ---
        if output_dir.exists() and not force:
            existing_frames = [
                f for f in output_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS
            ]
            benchmark_metrics["existing_frames"] = len(existing_frames)
            if len(existing_frames) > 0:
                log_info(f"Found {len(existing_frames)} existing frames in {output_dir}.")
                log_info("Skipping capture phase...")

                update_manifest(manifest_path, manifest, phase=1, source_type=source_type)
                append_phase_benchmark(
                    manifest,
                    1,
                    status="skipped",
                    skipped=True,
                    duration_seconds=time.perf_counter() - start_perf,
                    settings=benchmark_settings,
                    metrics=benchmark_metrics,
                    paths=benchmark_paths,
                )

                log_info("Phase 1: Capture complete")
                log_progress(value=1.0, label="Capture phase skipped")

                return
        # -----------------------

        if force and output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # ==========================================
        # IMAGE MODE LOGIC
        # ==========================================
        if is_image_mode:
            log_info("Image directory source detected. Copying frames to workspace...")

            source_images = sorted(
                [f for f in input_source.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS]
            )

            if len(source_images) == 0:
                raise ValueError(f"No valid images found in {input_source}")

            total_imgs = len(source_images)
            benchmark_metrics["input_images"] = total_imgs
            for i, img_path in enumerate(source_images):
                target_path = output_dir / f"frame_{i:04d}{img_path.suffix}"
                shutil.copy2(img_path, target_path)
                benchmark_metrics["output_frames"] = i + 1

                if i % 5 == 0 or i < total_imgs - 1:
                    log_progress(value=(i+1) / total_imgs, label=f"Copying frame {i+1}/{total_imgs}")

            log_info(f"Transferred {len(source_images)} frames to capture directory.")
            if len(source_images) < target_min_frames:
                log_info(f"[!] WARNING: Dataset size ({len(source_images)}) is lower than requested minimum ({target_min_frames}).")

        # ==========================================
        # VIDEO MODE LOGIC (Dynamic Downsampling)
        # ==========================================
        elif is_video_mode:
            cap = cv2.VideoCapture(str(input_source))
            if not cap.isOpened():
                raise RuntimeError(f"Could not open video file: {input_source}")

            total_frames_in = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            # Calculate optimal skip index step based on required target frame constraint
            frame_skip = max(1, total_frames_in // target_min_frames)
            benchmark_metrics.update({
                "input_video_frames": total_frames_in,
                "frame_skip": frame_skip,
                "processed_video_frames": 0,
                "output_frames": 0,
            })

            log_info(f"Total Video Frames: {total_frames_in} | Targeted Minimum Dataset: {target_min_frames}")
            log_info(f"Extracting every {frame_skip} frames directly to PNG...")

            frame_idx = 0
            saved_count = 0

            try:
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    if frame_idx % frame_skip == 0:
                        target_path = output_dir / f"frame_{saved_count:04d}.png"
                        cv2.imwrite(str(target_path), frame)
                        saved_count += 1
                        benchmark_metrics["output_frames"] = saved_count

                    benchmark_metrics["processed_video_frames"] = frame_idx + 1
                    if frame_idx % 30 == 0:
                        log_progress(
                            value=frame_idx / total_frames_in,
                            label=f"Extracting frame {saved_count} of ~{target_min_frames}"
                        )

                    frame_idx += 1
            finally:
                cap.release()

            log_info(f"Successfully extracted {saved_count} frames to capture directory.")

        total_time = time.perf_counter() - start_perf

        update_manifest(manifest_path, manifest, phase=1, source_type=source_type)
        append_phase_benchmark(
            manifest,
            1,
            status="completed",
            skipped=False,
            duration_seconds=total_time,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
        )

        log_info(f"Total Extraction Time: {total_time:.2f}s")
        log_progress(value=1.0, label="Phase 1: Capture complete")
    except (RuntimeError, ValueError, OSError, cv2.error) as error:
        append_failed_phase_benchmark(
            manifest,
            1,
            start_time=start_perf,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--image", action="store_true")
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--ipc", action="store_true")

    args = parser.parse_args()
    try:
        run_capture(
            args.manifest,
            is_image_mode=args.image,
            is_video_mode=args.video,
            force=args.force,
            ipc_mode=args.ipc
        )
    except (RuntimeError, ValueError, OSError) as error:
        log_error(str(error))
        sys.exit(1)
