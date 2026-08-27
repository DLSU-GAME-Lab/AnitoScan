import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pycolmap

core_path = str(Path(__file__).resolve().parent.parent / "core")
sys.path.insert(0, core_path)

from benchmark import append_failed_phase_benchmark, append_phase_benchmark
from cancellation import check_cancelled
from log import log_error, log_info, log_progress, set_ipc_mode, set_phase
from manifest import load_manifest, update_manifest


def run_bundle_adjustment(
    image_dir: Path,
    output_dir: Path,
    cancel_event=None,
) -> tuple[Path, int, int]:
    """
    Runs a mathematically rigorous Bundle Adjustment pass using pycolmap
    to generate sub-pixel perfect camera poses and a sparse feature cloud.
    """
    check_cancelled(cancel_event)
    log_info("Starting Geometric Bundle Adjustment...")
    database_path = output_dir / "database.db"
    if database_path.exists():
        database_path.unlink()  # Start fresh

    log_info("Extracting SIFT features...")
    reader_options = pycolmap.ImageReaderOptions()  # type: ignore
    reader_options.camera_model = "PINHOLE"

    pycolmap.extract_features(  # type: ignore
        database_path,
        image_dir,
        camera_mode=pycolmap.CameraMode.SINGLE,  # type: ignore
        reader_options=reader_options,
    )
    check_cancelled(cancel_event)

    log_info("Matching features...")
    pycolmap.match_exhaustive(database_path)  # type: ignore
    check_cancelled(cancel_event)

    log_info("Running Ceres Solver (Bundle Adjustment)...")
    maps = pycolmap.incremental_mapping(database_path, image_dir, output_dir)  # type: ignore
    check_cancelled(cancel_event)

    if not maps or len(maps) == 0:
        raise RuntimeError(
            "Bundle Adjustment failed to converge. The solver couldn't find enough matches."
        )

    map_values = list(maps.values()) if isinstance(maps, dict) else list(maps)
    best_map = max(map_values, key=lambda m: len(m.images))

    log_info(f"Bundle Adjustment complete. Registered {len(best_map.images)} cameras.")

    total_input_images = len(list(image_dir.glob("*")))
    if len(best_map.images) < max(3, int(0.5 * total_input_images)):
        raise RuntimeError(
            f"Bundle Adjustment only registered {len(best_map.images)}/{total_input_images} images "
            "in the largest reconstructed map. Scene may lack sufficient overlap/texture."
        )

    # Export to the raw text format 2DGS expects
    best_map.write_text(str(output_dir))
    return output_dir, len(best_map.images), total_input_images


def run_spatial_initialization(
    manifest_path_string: str,
    force: bool = False,
    ipc_mode: bool = False,
    cancel_event=None,
) -> None:
    set_ipc_mode(ipc_mode)
    set_phase(3)
    check_cancelled(cancel_event)

    manifest_path, manifest = load_manifest(manifest_path_string)
    phase_start = time.perf_counter()

    spatial_dir = Path(manifest["paths"]["spatial"])
    spatial_dir.mkdir(parents=True, exist_ok=True)

    input_data_path = spatial_dir
    sparse_dir = input_data_path / "sparse" / "0"
    image_dir = input_data_path / "images"
    benchmark_settings = {"force": force}
    benchmark_paths = {"spatial_dir": spatial_dir, "sparse_dir": sparse_dir, "image_dir": image_dir}
    benchmark_metrics: dict[str, Any] = {
        "input_frames": 0,
        "prepared_images": 0,
        "bundle_input_images": 0,
        "registered_cameras": 0,
        "registration_ratio": 0,
    }

    spatial_init_complete = (sparse_dir / "points3D.txt").exists() and (sparse_dir / "cameras.txt").exists()

    if spatial_init_complete and not force:
        log_info(f"Found existing spatial initialization in {input_data_path}. Skipping prep and bundle adjustment...")
        masked_frames = sorted(Path(manifest["paths"]["masked_frames"]).glob("*.png"))
        prepared_images = sorted(image_dir.glob("*")) if image_dir.exists() else []
        check_cancelled(cancel_event)
        update_manifest(manifest_path, manifest, phase=3)
        append_phase_benchmark(
            manifest,
            3,
            status="skipped",
            skipped=True,
            duration_seconds=time.perf_counter() - phase_start,
            settings={"force": force},
            metrics={
                "input_frames": len(masked_frames),
                "prepared_images": len(prepared_images),
                "has_points3D": (sparse_dir / "points3D.txt").exists(),
                "has_cameras": (sparse_dir / "cameras.txt").exists(),
            },
            paths={"spatial_dir": spatial_dir, "sparse_dir": sparse_dir, "image_dir": image_dir},
        )
        log_progress(1.0, "Phase 3: Spatial initialization complete (skipped)")
        return

    try:
        if force:
            if sparse_dir.exists():
                shutil.rmtree(sparse_dir)
            if image_dir.exists():
                shutil.rmtree(image_dir)

        sparse_dir.mkdir(parents=True, exist_ok=True)
        image_dir.mkdir(parents=True, exist_ok=True)

        log_info("Prepping images for Geometric Solver...")
        log_progress(0.0, "Phase 3: Preparing images...")

        start_time_pycolmap = time.perf_counter()
        masked_frames = sorted(Path(manifest["paths"]["masked_frames"]).glob("*.png"))
        total_frames = len(masked_frames)
        benchmark_metrics["input_frames"] = total_frames

        prepared_count = 0
        for i, original_png_path in enumerate(masked_frames):
            check_cancelled(cancel_event)
            target_image_path = image_dir / original_png_path.name
            img_rgba = cv2.imread(str(original_png_path), cv2.IMREAD_UNCHANGED)

            if img_rgba is not None and img_rgba.shape[2] == 4:
                bgr = img_rgba[:, :, :3].astype(np.float32)
                alpha = img_rgba[:, :, 3].astype(np.float32) / 255.0
                alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
                alpha_3c = np.expand_dims(alpha, axis=2)

                white_bg = np.ones_like(bgr) * 255.0
                composited_bgr = (bgr * alpha_3c) + (white_bg * (1.0 - alpha_3c))
                cv2.imwrite(str(target_image_path), composited_bgr.astype(np.uint8))
            else:
                shutil.copy2(str(original_png_path), str(target_image_path))

            prepared_count = i + 1
            benchmark_metrics["prepared_images"] = prepared_count

            if total_frames > 0 and i % 10 == 0:
                log_progress((i / total_frames) * 0.15, f"Preparing image {i + 1} of {total_frames}")

        log_info("Started running bundle adjustment...")
        log_progress(0.15, "Phase 3: Running Bundle Adjustment...")
        _, registered_cameras, bundle_input_images = run_bundle_adjustment(
            image_dir,
            sparse_dir,
            cancel_event,
        )

        benchmark_metrics.update({
            "bundle_input_images": bundle_input_images,
            "registered_cameras": registered_cameras,
            "registration_ratio": registered_cameras / bundle_input_images if bundle_input_images else 0,
        })
        total_time_pycolmap = time.perf_counter() - start_time_pycolmap

        check_cancelled(cancel_event)
        update_manifest(manifest_path, manifest, phase=3)
        append_phase_benchmark(
            manifest,
            3,
            status="completed",
            skipped=False,
            duration_seconds=total_time_pycolmap,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
        )

        log_info(f"Spatial Initialization via pycolmap Complete. Saved to: {input_data_path}")
        log_info(f"Total Time: {total_time_pycolmap:.2f}s")
        log_progress(1.0, "Phase 3: Spatial initialization complete")
    except (RuntimeError, ValueError, OSError, cv2.error) as error:
        append_failed_phase_benchmark(
            manifest,
            3,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True, help="Path to project manifest.json")
    parser.add_argument("--force", action="store_true", help="Overwrite existing spatial data")
    parser.add_argument("--ipc", action="store_true")
    args = parser.parse_args()

    try:
        run_spatial_initialization(args.manifest, force=args.force, ipc_mode=args.ipc)
    except (RuntimeError, ValueError, OSError) as error:
        log_error(str(error))
        sys.exit(1)
