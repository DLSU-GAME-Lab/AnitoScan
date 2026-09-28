import argparse
import json
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

from benchmark import append_failed_phase_benchmark, append_phase_benchmark, fail_pending_quality_report, reset_quality_report
from cancellation import check_cancelled
from config import normalize_evaluation_settings
from evaluation_split import PREPARATION_VERSION, build_evaluation_split, content_digest, write_evaluation_json
from log import log_error, log_info, log_progress, set_ipc_mode, set_phase
from manifest import load_manifest, update_manifest


def prepare_spatial_image(
    source: Path,
    target: Path,
    *,
    require_mask: bool = False,
) -> None:
    """Apply the same existing white-background preparation to train and test."""
    img_rgba = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
    if require_mask and (
        img_rgba is None or img_rgba.ndim != 3 or img_rgba.shape[2] != 4
        or img_rgba.dtype != np.uint8 or not np.any(img_rgba[:, :, 3])
    ):
        raise ValueError(f"BM5 masked frame changed or is invalid during preparation: {source.name}.")
    if img_rgba is not None and img_rgba.shape[2] == 4:
        bgr = img_rgba[:, :, :3].astype(np.float32)
        alpha = img_rgba[:, :, 3].astype(np.float32) / 255.0
        alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
        alpha_3c = np.expand_dims(alpha, axis=2)

        white_bg = np.ones_like(bgr) * 255.0
        composited_bgr = (bgr * alpha_3c) + (white_bg * (1.0 - alpha_3c))
        written = cv2.imwrite(str(target), composited_bgr.astype(np.uint8))
        if require_mask and not written:
            raise OSError(f"BM5 could not write prepared image: {target}")
    else:
        shutil.copy2(str(source), str(target))


def run_bundle_adjustment(
    image_dir: Path,
    output_dir: Path,
    cancel_event=None,
    *,
    train_only: bool = False,
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
    extraction_kwargs = {}
    if train_only:
        extraction_options = pycolmap.FeatureExtractionOptions()
        extraction_options.type = pycolmap.FeatureExtractorType.SIFT
        extraction_kwargs = {"extraction_options": extraction_options, "device": pycolmap.Device.cpu}

    pycolmap.extract_features(  # type: ignore
        database_path,
        image_dir,
        camera_mode=pycolmap.CameraMode.SINGLE,  # type: ignore
        reader_options=reader_options,
        **extraction_kwargs,
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
    best_map = max(map_values, key=lambda m: m.num_reg_images() if train_only else len(m.images))
    registered_cameras = best_map.num_reg_images() if train_only else len(best_map.images)

    log_info(f"Bundle Adjustment complete. Registered {registered_cameras} cameras.")

    total_input_images = len(list(image_dir.glob("*")))
    if registered_cameras < max(3, int(0.5 * total_input_images)):
        raise RuntimeError(
            f"Bundle Adjustment only registered {registered_cameras}/{total_input_images} images "
            "in the largest reconstructed map. Scene may lack sufficient overlap/texture."
        )

    # Export to the raw text format 2DGS expects
    best_map.write_text(str(output_dir))
    return output_dir, registered_cameras, total_input_images


def _spatial_cache_hashes(spatial_dir: Path, cancel_event=None) -> dict[str, str]:
    sparse_dir = spatial_dir / "sparse" / "0"
    sources = [path for path in sparse_dir.iterdir()
               if path.is_file() and (path.suffix in {".txt", ".bin"} or path.name == "database.db")]
    sources.extend(path for path in (spatial_dir / "images").iterdir() if path.is_file())
    return {str(path.relative_to(spatial_dir)): content_digest(path, cancel_event) for path in sorted(sources)}


def _run_evaluation_spatial(
    manifest_path: Path,
    manifest: dict[str, Any],
    force: bool,
    phase_start: float,
    cancel_event=None,
) -> None:
    if __package__:
        from .heldout_poses import localize_heldout_poses, require_localization_api
    else:
        from heldout_poses import localize_heldout_poses, require_localization_api

    spatial_dir = Path(manifest["paths"]["spatial"])
    sparse_dir = spatial_dir / "sparse" / "0"
    image_dir = spatial_dir / "images"
    evaluation_dir = Path(manifest["paths"]["run_root"]) / "evaluation"
    test_image_dir = evaluation_dir / "images"
    identity_path = spatial_dir / "evaluation_identity.json"
    settings = {
        "force": force,
        "evaluate_quality": True,
        "test_fraction": manifest.get("settings", {}).get("test_fraction", 0.2),
    }
    paths = {
        "spatial_dir": spatial_dir, "sparse_dir": sparse_dir,
        "image_dir": image_dir, "evaluation_dir": evaluation_dir,
    }
    metrics: dict[str, Any] = {}
    reset_quality_report(manifest)
    try:
        identity = None
        has_cache = any(
            path.name not in {"evaluation_identity.json", ".DS_Store"}
            for path in spatial_dir.iterdir()
        )
        if not force:
            if identity_path.exists():
                try:
                    identity = json.loads(identity_path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as error:
                    raise RuntimeError("BM5 spatial cache identity is unreadable; rerun Phase 3 with --force.") from error
                if not isinstance(identity, dict) or identity.get("evaluate_quality") is not True:
                    raise RuntimeError("BM5 spatial cache identity is invalid; rerun Phase 3 with --force.")
            elif has_cache:
                raise RuntimeError(
                    "BM5 cannot reuse an unmarked/all-frame spatial cache; rerun Phase 3 with --force."
                )

        split = build_evaluation_split(
            Path(manifest["paths"]["raw_frames"]),
            Path(manifest["paths"]["masked_frames"]),
            settings["test_fraction"],
            cancel_event,
        )
        if identity is not None and (
            identity.get("split_fingerprint") != split["fingerprint"]
            or identity.get("preparation_version") != PREPARATION_VERSION
        ):
            raise RuntimeError("BM5 spatial cache fingerprint differs from current inputs/split; rerun Phase 3 with --force.")

        reuse_training = identity is not None and identity.get("training_complete") is True
        if reuse_training:
            required_files = ("points3D.txt", "cameras.txt", "images.txt", "database.db")
            prepared = list(image_dir.iterdir()) if image_dir.is_dir() else []
            if (
                not all((sparse_dir / name).is_file() for name in required_files)
                or any(not path.is_file() for path in prepared)
                or {path.name for path in prepared} != set(split["usable_train"])
            ):
                raise RuntimeError("BM5 spatial cache is incomplete or has non-training images; rerun Phase 3 with --force.")
            if identity.get("sha256") != _spatial_cache_hashes(spatial_dir, cancel_event):
                raise RuntimeError("BM5 prepared images or training map changed; rerun Phase 3 with --force.")

        write_evaluation_json(evaluation_dir / "split.json", split)
        (evaluation_dir / "test_poses.json").unlink(missing_ok=True)
        metrics.update({
            "input_frames": len(split["train"]) + len(split["test"]),
            "train_frames": len(split["train"]), "test_frames": len(split["test"]),
            "usable_train": len(split["usable_train"]), "usable_test": len(split["usable_test"]),
            "excluded_frames": len(split["excluded"]), "training_skipped": reuse_training,
        })
        if not split["test"]:
            raise ValueError("BM5 split has no held-out frames (floor(N * test_fraction) is 0).")
        if len(split["usable_train"]) < 3:
            raise ValueError("BM5 requires at least 3 usable training images; exclusions are recorded in evaluation/split.json.")
        require_localization_api()
        masked_dir = Path(manifest["paths"]["masked_frames"])

        if not reuse_training:
            for directory in (spatial_dir / "sparse", image_dir):
                if directory.exists():
                    shutil.rmtree(directory)
            identity_path.unlink(missing_ok=True)
            sparse_dir.mkdir(parents=True, exist_ok=True)
            image_dir.mkdir(parents=True, exist_ok=True)
            log_info("BM5: preparing training images only for the geometric solver...")
            for i, frame in enumerate(split["usable_train"]):
                check_cancelled(cancel_event)
                prepare_spatial_image(masked_dir / frame, image_dir / frame, require_mask=True)
                metrics["prepared_images"] = i + 1
                if i % 10 == 0:
                    log_progress(0.15 * i / len(split["usable_train"]), "Phase 3: Preparing BM5 training images...")
            # This marker must never certify an old all-frame map or failed prep.
            identity = {
                "evaluate_quality": True,
                "split_fingerprint": split["fingerprint"],
                "preparation_version": PREPARATION_VERSION,
                "training_complete": False,
            }
            write_evaluation_json(identity_path, identity)
        else:
            log_info("BM5: reusing fingerprint-matched training reconstruction.")
            metrics["prepared_images"] = len(split["usable_train"])

        if test_image_dir.exists():
            shutil.rmtree(test_image_dir)
        test_image_dir.mkdir(parents=True, exist_ok=True)
        for frame in split["usable_test"]:
            check_cancelled(cancel_event)
            prepare_spatial_image(masked_dir / frame, test_image_dir / frame, require_mask=True)

        if not reuse_training:
            log_progress(0.15, "Phase 3: Reconstructing BM5 training images...")
            _, registered_cameras, bundle_input_images = run_bundle_adjustment(
                image_dir, sparse_dir, cancel_event, train_only=True
            )
            metrics.update({
                "registered_cameras": registered_cameras,
                "bundle_input_images": bundle_input_images,
            })
            identity["training_complete"] = True
            identity["sha256"] = _spatial_cache_hashes(spatial_dir, cancel_event)
            write_evaluation_json(identity_path, identity)

        log_progress(0.85, "Phase 3: Localizing held-out images against the frozen training map...")
        poses = localize_heldout_poses(sparse_dir, evaluation_dir, split, cancel_event)
        metrics.update({
            "bundle_input_images": len(split["usable_train"]),
            "registered_cameras": poses["train_registered"],
            "registration_ratio": poses["train_registered"] / len(split["usable_train"]),
            "localized_test": len(poses["cameras"]), "failed_test": len(poses["failed"]),
        })
        check_cancelled(cancel_event)
        update_manifest(manifest_path, manifest, phase=3)
        append_phase_benchmark(
            manifest, 3, status="completed", skipped=False,
            duration_seconds=time.perf_counter() - phase_start,
            settings=settings, metrics=metrics, paths=paths,
        )
        log_info(
            f"BM5 localized {len(poses['cameras'])}/{len(split['test'])} held-out frames. "
            "Unavailable frames are recorded in evaluation/test_poses.json; "
            "a complete evaluation requires every test frame."
        )
        log_progress(1.0, "Phase 3: Spatial initialization complete")
    except Exception as error:
        fail_pending_quality_report(manifest, error)
        append_failed_phase_benchmark(
            manifest, 3, start_time=phase_start,
            settings=settings, metrics=metrics, paths=paths, error=error,
        )
        raise


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

    if normalize_evaluation_settings(manifest.get("settings", {}))["evaluate_quality"]:
        _run_evaluation_spatial(manifest_path, manifest, force, phase_start, cancel_event)
        return
    evaluation_identity_path = spatial_dir / "evaluation_identity.json"
    evaluation_dir = Path(manifest["paths"]["run_root"]) / "evaluation"
    has_evaluation_cache = evaluation_identity_path.exists() or (evaluation_dir / "split.json").exists()
    if has_evaluation_cache and not force:
        raise RuntimeError("BM5 spatial cache cannot be reused with evaluate_quality disabled; rerun Phase 3 with --force.")

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
            if has_evaluation_cache:
                reset_quality_report(manifest, status="disabled")
                evaluation_identity_path.unlink(missing_ok=True)
                (evaluation_dir / "split.json").unlink(missing_ok=True)
                (evaluation_dir / "test_poses.json").unlink(missing_ok=True)

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
            prepare_spatial_image(original_png_path, image_dir / original_png_path.name)

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
