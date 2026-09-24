"""Localize BM5 queries without registering them in, or modifying, the train map."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import shutil
import sys
from typing import Any

import cv2
import numpy as np
import pycolmap

core_path = str(Path(__file__).resolve().parent.parent / "core")
sys.path.insert(0, core_path)

from cancellation import check_cancelled
from evaluation_split import write_evaluation_json
from log import log_info

MIN_POSE_INLIERS = 6
MIN_POSE_INLIER_RATIO = 0.25
MAX_REPROJECTION_ERROR = 4.0


class UnsupportedPycolmapError(RuntimeError):
    """The installed bindings cannot provide the frozen-map BM5 contract."""


def _unsupported(detail: str) -> UnsupportedPycolmapError:
    return UnsupportedPycolmapError(
        "BM5 requires pycolmap >= 4.0.4 with frozen-map localization APIs; "
        f"installed version: {getattr(pycolmap, '__version__', 'unknown')}. {detail}"
    )


def require_localization_api() -> None:
    """Reject unsupported bindings explicitly, before starting train reconstruction."""
    version = re.match(r"^(\d+)\.(\d+)\.(\d+)", getattr(pycolmap, "__version__", ""))
    if version is None or tuple(map(int, version.groups())) < (4, 0, 4):
        raise _unsupported("Unsupported version.")
    # These bindings/signatures are defined in the upstream 4.0.4 sources under
    # src/pycolmap/{pipeline,scene,estimators}; no COLMAP CLI fallback is used.
    required = (
        "extract_features", "match_image_pairs", "estimate_and_refine_absolute_pose",
        "match_exhaustive", "incremental_mapping",
        "Database.open", "Database.update_camera", "Database.read_camera", "Database.read_all_images",
        "Database.read_image_with_name", "Database.read_keypoints",
        "Database.exists_keypoints", "Database.exists_descriptors",
        "Database.exists_two_view_geometry", "Database.read_two_view_geometry",
        "Reconstruction.read_text", "Reconstruction.reg_image_ids",
        "Reconstruction.num_reg_images", "Reconstruction.write_text",
        "Camera", "CameraModelId.PINHOLE", "CameraMode.SINGLE", "Device.cpu",
        "ImageReaderOptions.existing_camera_id", "FeatureExtractionOptions.type",
        "FeatureExtractorType.SIFT", "FeatureMatchingOptions.type",
        "FeatureMatchingOptions.skip_geometric_verification",
        "FeatureMatcherType.SIFT_BRUTEFORCE", "ImportedPairingOptions.match_list_path",
        "AbsolutePoseEstimationOptions.estimate_focal_length",
        "AbsolutePoseRefinementOptions.refine_focal_length",
        "AbsolutePoseRefinementOptions.refine_extra_params", "RANSACOptions.random_seed",
        "TwoViewGeometry.inlier_matches", "Rigid3d.matrix",
    )
    for name in required:
        attribute = pycolmap
        for component in name.split("."):
            attribute = getattr(attribute, component, None)
            if attribute is None:
                raise _unsupported(f"Missing API: pycolmap.{name}.")


def _fixed_camera(camera: pycolmap.Camera) -> pycolmap.Camera:
    return pycolmap.Camera(
        camera_id=camera.camera_id,
        model=pycolmap.CameraModelId.PINHOLE,
        width=camera.width,
        height=camera.height,
        params=np.array(camera.params, dtype=np.float64, copy=True),
        has_prior_focal_length=True,
    )


def _copy_training_database(
    sparse_dir: Path,
    work_dir: Path,
    registered: list[pycolmap.Image],
    train_names: set[str],
    camera: pycolmap.Camera,
) -> Path:
    source = sparse_dir / "database.db"
    if not source.is_file():
        raise RuntimeError("BM5 training database is missing; rerun Phase 3 with --force.")
    if (
        work_dir.resolve().is_relative_to(sparse_dir.resolve())
        or sparse_dir.resolve().is_relative_to(work_dir.resolve())
    ):
        raise ValueError("BM5 localization work directory must not overlap the training sparse directory.")
    wal_path = source.with_name(source.name + "-wal")
    if wal_path.exists() and wal_path.stat().st_size:
        raise RuntimeError(
            "BM5 training database has an uncheckpointed WAL; close its writer "
            "and rerun Phase 3 with --force."
        )
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    database_path = work_dir / "database.db"
    # Never open the source with Database.open: even a read via COLMAP may write
    # SQLite metadata. Every subsequent database operation targets this copy.
    shutil.copy2(source, database_path)
    with pycolmap.Database.open(database_path) as database:
        database_images = {image.name: image for image in database.read_all_images()}
        if set(database_images) != train_names:
            raise RuntimeError("BM5 training database membership differs from split; rerun Phase 3 with --force.")
        for image in registered:
            stored = database_images[image.name]
            if stored.image_id != image.image_id or stored.camera_id != camera.camera_id:
                raise RuntimeError("BM5 training database does not match frozen map; rerun Phase 3 with --force.")
            if not database.exists_keypoints(image.image_id) or not database.exists_descriptors(image.image_id):
                raise RuntimeError("BM5 registered training features are missing; rerun Phase 3 with --force.")
            keypoints = database.read_keypoints(image.image_id)
            observations = np.asarray([point.xy for point in image.points2D], dtype=np.float64).reshape(-1, 2)
            if len(keypoints) != len(observations) or not np.allclose(
                keypoints[:, :2], observations, rtol=0, atol=1e-4
            ):
                raise RuntimeError("BM5 training keypoints do not match frozen map; rerun Phase 3 with --force.")
        # Mapping refines intrinsics in the reconstruction, not in database.db.
        database.update_camera(camera)
    return database_path


def _query_correspondences(
    database: pycolmap.Database,
    query: pycolmap.Image,
    registered: list[pycolmap.Image],
    reconstruction: pycolmap.Reconstruction,
    cancel_event=None,
) -> tuple[np.ndarray, np.ndarray]:
    keypoints = database.read_keypoints(query.image_id)
    votes: dict[int, Counter[int]] = {}
    for train_image in registered:
        check_cancelled(cancel_event)
        first, second = sorted((query.image_id, train_image.image_id))
        if not database.exists_two_view_geometry(first, second):
            continue
        geometry = database.read_two_view_geometry(first, second)
        # Request canonical ID order explicitly; match columns follow that order.
        query_column = 0 if query.image_id == first else 1
        for match in geometry.inlier_matches:
            query_idx = int(match[query_column])
            train_idx = int(match[1 - query_column])
            if not 0 <= query_idx < len(keypoints) or not 0 <= train_idx < len(train_image.points2D):
                raise RuntimeError("Verified match contains an out-of-range feature index.")
            point = train_image.points2D[train_idx]
            if point.has_point3D() and point.point3D_id in reconstruction.points3D:
                votes.setdefault(query_idx, Counter())[int(point.point3D_id)] += 1

    candidates = []
    for query_idx, counts in votes.items():
        ranked = counts.most_common()
        # Conflicting equal-support associations cannot identify a unique 3D point.
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            continue
        point_id, support = ranked[0]
        candidates.append((-support, query_idx, point_id))
    used_points = set()
    points2D = []
    points3D = []
    for _, query_idx, point_id in sorted(candidates):
        if point_id in used_points:
            continue
        xy = keypoints[query_idx, :2]
        xyz = reconstruction.points3D[point_id].xyz
        if not np.isfinite(xy).all() or not np.isfinite(xyz).all():
            continue
        used_points.add(point_id)
        points2D.append(xy)
        points3D.append(xyz)
    return (
        np.asarray(points2D, dtype=np.float64).reshape(-1, 2),
        np.asarray(points3D, dtype=np.float64).reshape(-1, 3),
    )


def _localize_frame(
    frame: str,
    image_dir: Path,
    database_path: Path,
    registered: list[pycolmap.Image],
    reconstruction: pycolmap.Reconstruction,
    camera: pycolmap.Camera,
    cancel_event=None,
) -> dict[str, Any]:
    image = cv2.imread(str(image_dir / frame), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError("Prepared held-out image is missing or unreadable.")
    if image.shape[:2] != (camera.height, camera.width):
        raise ValueError(
            f"Held-out image dimensions {image.shape[1]}x{image.shape[0]} differ "
            f"from fixed training camera {camera.width}x{camera.height}."
        )
    del image
    reader_options = pycolmap.ImageReaderOptions()
    reader_options.camera_model = "PINHOLE"
    reader_options.existing_camera_id = camera.camera_id
    extraction_options = pycolmap.FeatureExtractionOptions()
    extraction_options.type = pycolmap.FeatureExtractorType.SIFT
    check_cancelled(cancel_event)
    pycolmap.extract_features(
        database_path,
        image_dir,
        image_names=[frame],
        camera_mode=pycolmap.CameraMode.SINGLE,
        reader_options=reader_options,
        extraction_options=extraction_options,
        device=pycolmap.Device.cpu,
    )
    check_cancelled(cancel_event)
    with pycolmap.Database.open(database_path) as database:
        query = database.read_image_with_name(frame)
        if query is None or not database.exists_keypoints(query.image_id) or not database.exists_descriptors(query.image_id):
            raise RuntimeError("Held-out SIFT feature extraction failed.")
        if query.camera_id != camera.camera_id:
            raise _unsupported("Held-out feature extraction did not use the fixed training camera.")
        extracted_camera = database.read_camera(query.camera_id)
        if (
            extracted_camera.model != camera.model
            or extracted_camera.width != camera.width or extracted_camera.height != camera.height
            or not np.array_equal(extracted_camera.params, camera.params)
        ):
            raise _unsupported("Held-out feature extraction changed fixed camera intrinsics.")

    pairs_path = database_path.parent / "pairs.txt"
    pairs_path.write_text(
        "".join(f"{frame} {image.name}\n" for image in registered), encoding="utf-8"
    )
    pairing_options = pycolmap.ImportedPairingOptions()
    pairing_options.match_list_path = pairs_path
    matching_options = pycolmap.FeatureMatchingOptions()
    matching_options.type = pycolmap.FeatureMatcherType.SIFT_BRUTEFORCE
    matching_options.skip_geometric_verification = False
    verification_options = pycolmap.TwoViewGeometryOptions()
    verification_options.ransac.random_seed = 0
    pycolmap.match_image_pairs(
        database_path,
        matching_options=matching_options,
        pairing_options=pairing_options,
        verification_options=verification_options,
        device=pycolmap.Device.cpu,
    )
    check_cancelled(cancel_event)
    with pycolmap.Database.open(database_path) as database:
        points2D, points3D = _query_correspondences(
            database, query, registered, reconstruction, cancel_event
        )
    if len(points2D) < MIN_POSE_INLIERS:
        raise RuntimeError(
            f"Insufficient verified 2D-to-training-3D associations: {len(points2D)} "
            f"(need {MIN_POSE_INLIERS})."
        )

    estimation_options = pycolmap.AbsolutePoseEstimationOptions()
    estimation_options.estimate_focal_length = False
    estimation_options.ransac.max_error = MAX_REPROJECTION_ERROR
    estimation_options.ransac.min_inlier_ratio = MIN_POSE_INLIER_RATIO
    estimation_options.ransac.random_seed = 0
    refinement_options = pycolmap.AbsolutePoseRefinementOptions()
    refinement_options.refine_focal_length = False
    refinement_options.refine_extra_params = False
    pose_camera = _fixed_camera(camera)
    pose = pycolmap.estimate_and_refine_absolute_pose(
        points2D,
        points3D,
        pose_camera,
        estimation_options=estimation_options,
        refinement_options=refinement_options,
    )
    check_cancelled(cancel_event)
    if pose is None:
        raise RuntimeError("Robust absolute pose estimation/refinement failed.")
    if pose["num_inliers"] < MIN_POSE_INLIERS or pose["num_inliers"] / len(points2D) < MIN_POSE_INLIER_RATIO:
        raise RuntimeError(f"Absolute pose has insufficient RANSAC support: {pose['num_inliers']}/{len(points2D)}.")
    if not np.array_equal(pose_camera.params, camera.params):
        raise _unsupported("Absolute pose estimation changed fixed camera intrinsics.")
    transform = np.asarray(pose["cam_from_world"].matrix(), dtype=np.float64)
    if transform.shape != (3, 4):
        raise _unsupported("Rigid3d.matrix() must return a 3x4 world-to-camera transform.")
    if not np.isfinite(transform).all():
        raise RuntimeError("Absolute pose contains non-finite values.")
    world_to_camera = np.eye(4)
    world_to_camera[:3, :] = transform
    fx, fy, cx, cy = map(float, camera.params)
    return {
        "frame": frame,
        "width": int(camera.width),
        "height": int(camera.height),
        "fx": fx, "fy": fy, "cx": cx, "cy": cy,
        "world_to_camera": world_to_camera.tolist(),
    }


def localize_heldout_poses(
    sparse_dir: Path,
    evaluation_dir: Path,
    split: dict[str, Any],
    cancel_event=None,
) -> dict[str, Any]:
    """Write/return test_poses.json, including excluded and unlocalized test frames.

    Uses only the exported training text model and a disposable COPY of its DB.
    Individual image failures are recorded and do not discard successful poses.
    Global setup/API errors are raised after saving partial results; cancellation
    also saves results. No query is added to the reconstruction or its tracks.
    """
    if (
        evaluation_dir.resolve().is_relative_to(sparse_dir.resolve())
        or sparse_dir.resolve().is_relative_to(evaluation_dir.resolve())
    ):
        raise ValueError("BM5 evaluation directory must not overlap the training sparse directory.")
    result: dict[str, Any] = {
        "split_fingerprint": split["fingerprint"],
        "train_registered": 0,
        "cameras": [],
        "failed": [],
    }
    failures = {frame: "localization_not_completed" for frame in split["test"]}
    for excluded in split["excluded"]:
        if excluded["split"] == "test":
            failures[excluded["frame"]] = f"excluded: {excluded['reason']}"

    def save() -> None:
        result["failed"] = [
            {"frame": frame, "reason": failures[frame]}
            for frame in split["test"] if frame in failures
        ]
        write_evaluation_json(evaluation_dir / "test_poses.json", result)

    def fail_pending(reason: str) -> None:
        for frame in failures:
            if failures[frame] == "localization_not_completed":
                failures[frame] = reason

    save()
    try:
        check_cancelled(cancel_event)
        require_localization_api()
        train_names = set(split["usable_train"])
        if train_names.intersection(split["test"]):
            raise ValueError("BM5 train and test membership must be disjoint.")
        if any(any(character.isspace() for character in name) for name in train_names | set(split["test"])):
            raise ValueError("BM5 COLMAP pair filenames must not contain whitespace.")
        reconstruction = pycolmap.Reconstruction()
        reconstruction.read_text(sparse_dir)
        if any(image.name not in train_names for image in reconstruction.images.values()):
            raise RuntimeError("BM5 frozen map contains non-training images; rerun Phase 3 with --force.")
        registered = sorted(
            (reconstruction.images[image_id] for image_id in reconstruction.reg_image_ids()),
            key=lambda image: image.name,
        )
        result["train_registered"] = len(registered)
        if not registered:
            raise RuntimeError("BM5 frozen map has no registered training images.")
        camera_ids = {image.camera_id for image in registered}
        if len(camera_ids) != 1:
            raise RuntimeError("BM5 requires one shared trained PINHOLE camera.")
        trained_camera = reconstruction.cameras[next(iter(camera_ids))]
        params = np.asarray(trained_camera.params)
        if (
            trained_camera.model != pycolmap.CameraModelId.PINHOLE
            or params.shape != (4,)
            or not np.isfinite(params).all()
            or np.any(params[:2] <= 0)
            or trained_camera.width <= 0 or trained_camera.height <= 0
        ):
            raise RuntimeError("BM5 requires valid fixed trained PINHOLE intrinsics (fx, fy, cx, cy).")
        camera = _fixed_camera(trained_camera)
        database_path = _copy_training_database(
            sparse_dir, evaluation_dir / "localization", registered, train_names, camera
        )
        save()
        for frame in split["usable_test"]:
            check_cancelled(cancel_event)
            try:
                pose = _localize_frame(
                    frame, evaluation_dir / "images", database_path,
                    registered, reconstruction, camera, cancel_event,
                )
            except UnsupportedPycolmapError:
                raise
            except (RuntimeError, ValueError, OSError, cv2.error) as error:
                failures[frame] = str(error)
                log_info(f"BM5 held-out localization failed for {frame}: {error}")
            else:
                result["cameras"].append(pose)
                failures.pop(frame, None)
            save()
    except (AttributeError, TypeError, KeyError) as error:
        unsupported = _unsupported(f"Incompatible localization API: {error}")
        fail_pending(str(unsupported))
        raise unsupported from error
    except (RuntimeError, ValueError, OSError, cv2.error) as error:
        fail_pending(f"localization_aborted: {error}")
        raise
    finally:
        save()
    return result
