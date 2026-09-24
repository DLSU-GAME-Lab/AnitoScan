"""BM-5 held-out rendering; never constructs a Scene or runs an optimizer.

The supported backend is the standard CUDA 2DGS API. Imports and signatures are
checked at runtime because the vendor checkout may be absent. Geometry runs
--preflight before training; standalone evaluation only accepts marked checkpoints.
"""

import argparse
import ast
import csv
import hashlib
import importlib
import inspect
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

CORE_PATH = Path(__file__).resolve().parent.parent / "core"
sys.path.insert(0, str(CORE_PATH))

from config import normalize_evaluation_settings
from log import log_error, log_info, set_phase
from manifest import load_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GS_PATH = PROJECT_ROOT / "vendor" / "2d-gaussian-splatting"
MARKER_NAME = "bm5_training.json"
ADAPTER_VERSION = 1

CENTER_TOLERANCE_PX = 0.0001
CSV_FIELDS = [
    "frame", "status", "width", "height", "fx", "fy", "cx", "cy",
    "psnr_db", "ssim", "reference_sha256", "render_preview", "reference_preview", "error",
]


class QualityIncompleteError(RuntimeError):
    """The requested held-out set could not be evaluated in its entirety."""


def quality_settings(manifest):
    return normalize_evaluation_settings(manifest.get("settings", {}))


def report_paths(manifest):
    root = Path(manifest["paths"]["run_root"]) / "evaluation"
    return {
        "evaluation_dir": root,
        "split": root / "split.json",
        "test_poses": root / "test_poses.json",
        "evaluation_images": root / "images",
        "quality_summary": root / "summary.json",
        "quality_per_frame": root / "per_frame.csv",
        "quality_previews": root / "previews",
        "quality_training_plan": root / "training_plan.json",
    }


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def value_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()


def new_summary(manifest):
    settings = manifest.get("settings", {})
    return {
        "benchmark": "BM-5", "status": "incomplete", "run_name": manifest.get("run_name"),
        "quality": settings.get("quality", "fast"), "train_frames": 0, "test_frames": 0,
        "requested_train_frames": 0, "requested_test_frames": 0,
        "psnr_db": None, "ssim": None, "train_iterations": None, "split_fingerprint": None,
        "settings": {
            "evaluate_quality": settings.get("evaluate_quality", False),
            "test_fraction": settings.get("test_fraction", 0.2),
            "adapter_version": ADAPTER_VERSION, "background": [1.0, 1.0, 1.0],
            "reference_protocol": "Phase 3 white-composited RGB, vendor loadCam resizing, no crop/mask",
            "render_protocol": "CUDA 2DGS, inference_mode, RGB clamped to [0,1]",
            "aggregation": "arithmetic mean of per-image scores (not pooled MSE)",
            "psnr": "float64 NumPy MSE; 10*log10(1/MSE); exact matches are +inf, never epsilon-capped",
            "ssim": {"data_range": 1.0, "channel_axis": -1, "gaussian_weights": True,
                     "sigma": 1.5, "use_sample_covariance": False},
            "principal_point": "centered PINHOLE/SIMPLE_PINHOLE only, cx=width/2, cy=height/2",
            "principal_point_tolerance_px": CENTER_TOLERANCE_PX,
        },
        "details": {"paths": {key: str(path) for key, path in report_paths(manifest).items()}},
        "errors": [],
    }


def save_report(manifest, summary, rows):
    paths = report_paths(manifest)
    paths["evaluation_dir"].mkdir(parents=True, exist_ok=True)
    temporary = paths["quality_per_frame"].with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(paths["quality_per_frame"])
    write_json(paths["quality_summary"], summary)


def write_failure_report(manifest, error, plan=None):
    """Lightweight fallback for child launch/training failures; no GPU imports."""
    summary = new_summary(manifest)
    try:
        split = read_json(report_paths(manifest)["split"])
        summary.update(requested_train_frames=len(split["train"]), requested_test_frames=len(split["test"]),
                       split_fingerprint=split["fingerprint"])
        poses = read_json(report_paths(manifest)["test_poses"])
        if poses["split_fingerprint"] == split["fingerprint"] and type(poses["train_registered"]) is int:
            summary["train_frames"] = max(0, poses["train_registered"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if plan:
        summary["train_frames"] = plan["train_registered"]
        summary["details"]["training_fingerprint"] = plan["fingerprint"]
        summary["details"]["vendor"] = plan["vendor"]
        summary["settings"]["training"] = plan["training_config"]
    summary["status"] = "failed"
    summary["errors"].append(str(error))
    save_report(manifest, summary, [])
    return summary


def _filenames(value, label):
    if not isinstance(value, list) or any(
        not isinstance(name, str) or not name or name in {".", ".."}
        or Path(name).name != name or "\\" in name for name in value
    ):
        raise ValueError(f"{label} must contain plain frame filenames, not paths")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicate frames")
    return value


def load_inputs(manifest, summary):
    paths = report_paths(manifest)
    options = quality_settings(manifest)
    if not options["evaluate_quality"]:
        raise ValueError("BM-5 is opt-in: set manifest.settings.evaluate_quality=true before Phases 3–4")
    try:
        split = read_json(paths["split"])
    except (OSError, ValueError) as error:
        raise QualityIncompleteError(f"Cannot read {paths['split']}. Regenerate the held-out split in Phase 3: {error}") from error
    for key in ("train", "test", "usable_train", "usable_test"):
        _filenames(split[key], f"split.{key}")
    summary.update(requested_train_frames=len(split["train"]), requested_test_frames=len(split["test"]),
                   split_fingerprint=split["fingerprint"])
    if not isinstance(split["fingerprint"], str) or not split["fingerprint"]:
        raise ValueError("split.fingerprint must be a nonempty string")
    if set(split["train"]) & set(split["test"]):
        raise ValueError("Train/test leakage: split.train and split.test overlap")
    for role in ("train", "test"):
        if not set(split[f"usable_{role}"]) <= set(split[role]):
            raise ValueError(f"split.usable_{role} must be a subset of split.{role}")
    if split["test_fraction"] != options["test_fraction"]:
        raise ValueError("Split test_fraction differs from the manifest. Regenerate Phase 3 before Phase 4")
    if not isinstance(split["excluded"], list) or not isinstance(split["foreground_coverage"], dict):
        raise ValueError("split.excluded must be a list and split.foreground_coverage must be a dictionary")
    summary["details"].update(split_sha256=file_hash(paths["split"]), split_algorithm=split["algorithm"],
                              excluded=split["excluded"], foreground_coverage=split["foreground_coverage"])
    if not split["test"]:
        raise QualityIncompleteError("The split requests no test frames. Regenerate a nonempty held-out split in Phase 3")
    if not split["usable_train"]:
        raise QualityIncompleteError("No usable training frames. Fix masking/splitting and rerun Phases 2–3")
    try:
        poses = read_json(paths["test_poses"])
    except (OSError, ValueError) as error:
        raise QualityIncompleteError(f"Cannot read {paths['test_poses']}. Run Phase 3 test localization: {error}") from error
    if poses["split_fingerprint"] != split["fingerprint"]:
        raise QualityIncompleteError("test_poses.json belongs to a different split. Rerun Phase 3 localization")
    count = poses["train_registered"]
    if type(count) is not int or count <= 0:
        raise QualityIncompleteError("test_poses.train_registered must be a positive actual registered-camera count")
    summary["train_frames"] = count
    cameras = poses["cameras"]
    failed = poses["failed"]
    if not isinstance(cameras, list) or not isinstance(failed, list):
        raise ValueError("test_poses.cameras and test_poses.failed must be lists")
    _filenames([item["frame"] for item in cameras], "test_poses.cameras")
    _filenames([item["frame"] for item in failed], "test_poses.failed")
    if not {item["frame"] for item in cameras + failed} <= set(split["test"]):
        raise ValueError("test_poses.json contains frames outside the requested test split")
    summary["details"]["test_poses_sha256"] = file_hash(paths["test_poses"])
    return split, poses


def training_flags(config):
    for key in ("train_iterations", "densify_until_iter", "opacity_reset_interval"):
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    return [
        "--iterations", str(config["train_iterations"]), "--densify_from_iter", "500",
        "--densify_until_iter", str(config["densify_until_iter"]),
        "--opacity_reset_interval", str(config["opacity_reset_interval"]),
        "--white_background", "--lambda_dist", "0.0", "--lambda_normal", "0.05",
        "--resolution", "-1", "--sh_degree", "3", "--data_device", "cuda",
    ]


def _vendor_revision(root):
    """Best-effort revision label only; content hashes are the identity guard."""
    try:
        metadata = root / ".git"
        if metadata.is_file():
            metadata = (root / metadata.read_text(encoding="utf-8").strip().removeprefix("gitdir: ")).resolve()
        head = (metadata / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref: "):
            return head
        ref = head[5:]
        if (metadata / ref).is_file():
            return (metadata / ref).read_text(encoding="utf-8").strip()
        for line in (metadata / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + ref):
                return line.split()[0]
    except (OSError, ValueError):
        pass
    return None


class VendorAdapter:
    """Small, deliberately strict adapter to standard 2DGS camera/render APIs."""

    def __init__(self, spatial_dir, model_dir, config):
        required = ["train.py", "render.py", "arguments/__init__.py", "scene/gaussian_model.py",
                    "scene/cameras.py", "scene/dataset_readers.py", "scene/colmap_loader.py",
                    "gaussian_renderer/__init__.py", "utils/camera_utils.py"]
        missing = [name for name in required if not (GS_PATH / name).is_file()]
        if missing:
            raise RuntimeError(
                f"2DGS vendor source is missing at {GS_PATH}: {', '.join(missing)}. "
                "Populate the standard 2d-gaussian-splatting checkout and its CUDA submodules, "
                "then install the project dependencies before retrying Phase 4. No substitute renderer is used."
            )
        sys.path.insert(0, str(GS_PATH))
        try:
            import numpy as np
            import torch
            from PIL import Image
            from skimage.metrics import structural_similarity

            arguments = importlib.import_module("arguments")
            gaussian_module = importlib.import_module("scene.gaussian_model")
            camera_module = importlib.import_module("scene.cameras")
            renderer = importlib.import_module("gaussian_renderer")
            camera_utils = importlib.import_module("utils.camera_utils")
            self.readers = importlib.import_module("scene.dataset_readers")
            self.colmap = importlib.import_module("scene.colmap_loader")
            raster_extension = importlib.import_module("diff_surfel_rasterization._C")
            knn_extension = importlib.import_module("simple_knn._C")
            for module in (arguments, gaussian_module, camera_module, renderer, camera_utils, self.readers, self.colmap):
                if not Path(module.__file__).resolve().is_relative_to(GS_PATH.resolve()):
                    raise RuntimeError(f"{module.__name__} was imported from outside the selected vendor: {module.__file__}")
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA is unavailable; standard 2DGS does not support this evaluator on CPU/MPS")
            self.np, self.torch, self.Image = np, torch, Image
            self.GaussianModel = gaussian_module.GaussianModel
            self.Camera, self.loadCam, self.render = camera_module.Camera, camera_utils.loadCam, renderer.render
            parser = argparse.ArgumentParser(add_help=False)
            model_group = arguments.ModelParams(parser)
            pipeline_group = arguments.PipelineParams(parser)
            optimization_group = arguments.OptimizationParams(parser)
            namespace = parser.parse_args(["-s", str(spatial_dir), "-m", str(model_dir), *training_flags(config)])
            self.model = model_group.extract(namespace)
            self.pipeline = pipeline_group.extract(namespace)
            optimization = optimization_group.extract(namespace)
            if self.model.eval or not self.model.white_background or self.model.images != "images":
                raise RuntimeError("Expected eval=False, white_background=True, images='images' in vendor ModelParams")
            for field in ("convert_SHs_python", "compute_cov3D_python", "depth_ratio"):
                if not hasattr(self.pipeline, field):
                    raise RuntimeError(f"Unsupported vendor PipelineParams: missing {field}")
            # Inspect, but do not execute, the vendor's training entry point.
            entrypoint = ast.parse((GS_PATH / "train.py").read_text(encoding="utf-8"))
            declarations = {}
            for node in ast.walk(entrypoint):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
                    for argument in node.args:
                        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                            declarations[argument.value] = node
            for flag in ("--test_iterations", "--save_iterations", "--quiet"):
                if flag not in declarations:
                    raise RuntimeError(f"Unsupported vendor train.py: no explicit {flag} argument")
            for flag in ("--test_iterations", "--save_iterations"):
                nargs = next((item.value for item in declarations[flag].keywords if item.arg == "nargs"), None)
                if not isinstance(nargs, ast.Constant) or nargs.value not in ("+", "*"):
                    raise RuntimeError(f"Unsupported vendor train.py: {flag} must accept an iteration list")
            inspect.signature(self.GaussianModel).bind(self.model.sh_degree)
            inspect.signature(self.GaussianModel.load_ply).bind(None, "checkpoint.ply")
            inspect.signature(self.render).bind(None, None, self.pipeline, None)
            inspect.signature(self.loadCam).bind(self.model, 0, None, 1.0)
            inspect.signature(self.readers.readColmapSceneInfo).bind(str(spatial_dir), self.model.images, False)
            inspect.signature(self.Camera).bind(colmap_id=0, R=None, T=None, FoVx=1.0, FoVy=1.0,
                                                image=None, gt_alpha_mask=None, image_name="preflight", uid=0,
                                                data_device="cuda")
            if "channel_axis" not in inspect.signature(structural_similarity).parameters:
                raise RuntimeError("scikit-image structural_similarity must support channel_axis (use the project dependency version)")
            inspect.signature(structural_similarity).bind(None, None, channel_axis=-1, data_range=1.0,
                                                         gaussian_weights=True, sigma=1.5,
                                                         use_sample_covariance=False)
        except (Exception, SystemExit) as error:
            raise RuntimeError(
                f"2DGS dependency/API preflight failed: {type(error).__name__}: {error}. "
                "Use the standard 2DGS GaussianModel/load_ply, Camera/loadCam and render APIs; "
                "install compatible CUDA PyTorch, diff-surfel-rasterization, simple-knn, Pillow and scikit-image."
            ) from error
        self.training_config = {
            "model": {key: value for key, value in vars(self.model).items() if key not in {"source_path", "model_path"}},
            "pipeline": vars(self.pipeline), "optimization": vars(optimization),
            "vendor_eval_split": False, "test_iterations": [-1], "save_iterations": [config["train_iterations"]],
        }
        files = {
            str(path.relative_to(GS_PATH)): file_hash(path)
            for path in sorted(GS_PATH.rglob("*"))
            if path.is_file() and path.suffix in {".py", ".cpp", ".cu", ".cuh", ".h", ".hpp"}
            and not set(path.relative_to(GS_PATH).parts) & {".git", "__pycache__", "build", ".venv"}
        }
        self.identity = {
            "revision": _vendor_revision(GS_PATH), "identity_method": "SHA-256 source and extension contents",
            "source_sha256": value_hash(files), "files": files,
            "extensions": {module.__name__: file_hash(module.__file__) for module in (raster_extension, knn_extension)},
            "torch_version": str(torch.__version__), "cuda_version": torch.version.cuda,
        }
        self.environment = {"device": torch.cuda.get_device_name(), "numpy": np.__version__,
                            "skimage": importlib.import_module("skimage").__version__,
                            "pillow": importlib.import_module("PIL").__version__}

    def check_intrinsics(self, width, height, fx, fy, cx, cy):
        if type(width) is not int or type(height) is not int or min(width, height) <= 0:
            raise ValueError("Camera width/height must be positive integers")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in (fx, fy, cx, cy)) or min(fx, fy) <= 0:
            raise ValueError("Camera intrinsics must be finite numbers with positive focal lengths")
        if abs(cx - width / 2) > CENTER_TOLERANCE_PX or abs(cy - height / 2) > CENTER_TOLERANCE_PX:
            raise ValueError(
                f"Unsupported off-center principal point ({cx}, {cy}) for {width}x{height}. "
                "Standard 2DGS Camera/loadCam uses centered FoV projection and discards cx/cy. "
                "Provide centered, undistorted images and matching Phase 3 poses; do not just edit cx/cy."
            )

    def camera(self, info, intrinsics, uid):
        np, torch = self.np, self.torch
        width, height, fx, fy, cx, cy = intrinsics
        self.check_intrinsics(*intrinsics)
        if info.image.mode != "RGB" or info.image.size != (width, height):
            raise ValueError("Expected white-composited RGB matching the camera's original width/height")
        with torch.inference_mode():
            camera = self.loadCam(self.model, uid, info, 1.0)
        if not isinstance(camera, self.Camera):
            raise RuntimeError("Vendor loadCam did not return the expected scene.cameras.Camera")
        w, h = int(camera.image_width), int(camera.image_height)
        if min(w, h) < 11:
            raise ValueError("Effective render dimensions must be at least 11x11 for the specified Gaussian SSIM")
        scaled = {"width": w, "height": h, "fx": fx * w / width, "fy": fy * h / height,
                  "cx": cx * w / width, "cy": cy * h / height}
        world_to_camera = np.eye(4)
        world_to_camera[:3, :3] = np.asarray(info.R).T
        world_to_camera[:3, 3] = info.T
        view = camera.world_view_transform.detach().cpu().numpy()
        projection = camera.projection_matrix.detach().cpu().numpy().T
        if not np.allclose(view.T, world_to_camera, atol=1e-5, rtol=1e-5):
            raise RuntimeError("Unsupported vendor camera convention: expected transposed COLMAP world-to-camera")
        expected_xy = np.array([[2 * scaled["fx"] / w, 0, 0, 0], [0, 2 * scaled["fy"] / h, 0, 0]])
        if not np.allclose(projection[:2], expected_xy, atol=1e-5, rtol=1e-5) or not np.allclose(projection[3], [0, 0, 1, 0]):
            raise RuntimeError("Unsupported vendor projection: expected centered positive-Z pinhole projection")
        if not np.allclose(camera.full_proj_transform.detach().cpu().numpy(), view @ projection.T, atol=1e-5, rtol=1e-5):
            raise RuntimeError("Unsupported vendor full projection transform")
        if tuple(camera.original_image.shape) != (3, h, w):
            raise RuntimeError("Vendor Camera.original_image must be a resized RGB CHW tensor")
        return camera, scaled

    def training_dataset(self, spatial_dir, split, poses):
        sparse = spatial_dir / "sparse" / "0"
        image_dir = spatial_dir / self.model.images
        names = {path.name for path in image_dir.iterdir() if path.is_file()}
        if any(path.is_dir() for path in image_dir.iterdir()) or names != set(split["usable_train"]):
            raise ValueError("Spatial images must contain exactly split.usable_train, with no held-out/extra images. Rerun Phase 3")
        binary = [(sparse / name).is_file() for name in ("images.bin", "cameras.bin")]
        if any(binary) and not all(binary):
            raise ValueError("Partial COLMAP binary model could shadow the train-only text model. Regenerate Phase 3")
        suffix = "bin" if all(binary) else "txt"
        if suffix == "bin":
            extrinsics = self.colmap.read_extrinsics_binary(str(sparse / "images.bin"))
            intrinsics = self.colmap.read_intrinsics_binary(str(sparse / "cameras.bin"))
        else:
            extrinsics = self.colmap.read_extrinsics_text(str(sparse / "images.txt"))
            intrinsics = self.colmap.read_intrinsics_text(str(sparse / "cameras.txt"))
        registered = {record.name for record in extrinsics.values()}
        if len(registered) != len(extrinsics) or not registered <= set(split["usable_train"]):
            raise ValueError("COLMAP registered cameras contain duplicate, non-training or held-out frames. Rerun Phase 3")
        if len(registered) != poses["train_registered"]:
            raise ValueError("test_poses.train_registered disagrees with the actual training reconstruction. Rerun Phase 3")
        camera_intrinsics = {}
        for record in extrinsics.values():
            calibration = intrinsics[record.camera_id]
            if calibration.model == "PINHOLE":
                fx, fy, cx, cy = map(float, calibration.params)
            elif calibration.model == "SIMPLE_PINHOLE":
                fx, cx, cy = map(float, calibration.params)
                fy = fx
            else:
                raise ValueError(f"Unsupported training camera model {calibration.model}; undistort to PINHOLE first")
            values = (int(calibration.width), int(calibration.height), fx, fy, cx, cy)
            self.check_intrinsics(*values)
            camera_intrinsics[record.name] = values
        # Explicit eval=False: the dataset is already train-only. The standard loader
        # also materializes its initial points3D.ply, which must be part of the hash.
        scene = self.readers.readColmapSceneInfo(str(spatial_dir), self.model.images, False)
        if scene.test_cameras or {Path(info.image_path).name for info in scene.train_cameras} != registered:
            raise RuntimeError("Vendor dataset reader did not preserve the full train-only reconstruction with eval=False")
        resolutions = []
        for uid, info in enumerate(scene.train_cameras):
            name = Path(info.image_path).name
            camera, scaled = self.camera(info, camera_intrinsics[name], uid)
            resolutions.append({"frame": name, **scaled})
            del camera
        ply_path = Path(scene.ply_path)
        if ply_path.resolve() != (sparse / "points3D.ply").resolve() or scene.point_cloud is None:
            raise RuntimeError("Vendor did not load the standard train-only sparse/0/points3D.ply")
        sources = [sparse / f"images.{suffix}", sparse / f"cameras.{suffix}", ply_path]
        sources.extend(path for path in (sparse / "points3D.txt", sparse / "points3D.bin") if path.is_file())
        sources.extend(image_dir / name for name in sorted(names))
        hashes = {str(path.relative_to(spatial_dir)): file_hash(path) for path in sources}
        return {"registered_frames": sorted(registered), "sha256": hashes, "effective_cameras": resolutions}

    def test_camera(self, pose, reference_path, uid):
        np = self.np
        matrix = np.asarray(pose["world_to_camera"], dtype=np.float64)
        if matrix.shape != (4, 4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-6):
            raise ValueError("world_to_camera must be a finite row-major 4x4 rigid transform")
        rotation = matrix[:3, :3]
        if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-4) or not np.isclose(np.linalg.det(rotation), 1, atol=1e-4):
            raise ValueError("world_to_camera rotation is not a proper orthonormal rotation")
        values = (pose["width"], pose["height"], pose["fx"], pose["fy"], pose["cx"], pose["cy"])
        self.check_intrinsics(*values)
        with self.Image.open(reference_path) as source:
            source.load()
            if source.mode != "RGB":
                raise ValueError("Test reference must already be white-composited RGB; rerun Phase 3")
            if np.all(np.asarray(source) == 255):
                raise ValueError("Blank all-white held-out reference; fix masking and rerun Phases 2–3")
            info = SimpleNamespace(uid=uid, R=rotation.T, T=matrix[:3, 3],
                                   FovX=2 * math.atan(pose["width"] / (2 * pose["fx"])),
                                   FovY=2 * math.atan(pose["height"] / (2 * pose["fy"])),
                                   image=source, image_path=str(reference_path), image_name=reference_path.stem,
                                   width=pose["width"], height=pose["height"])
            return self.camera(info, values, uid)


def prepare_plan(manifest, split, poses, adapter, config):
    dataset = adapter.training_dataset(Path(manifest["paths"]["spatial"]), split, poses)
    payload = {
        "adapter_version": ADAPTER_VERSION, "split_fingerprint": split["fingerprint"],
        "split_sha256": file_hash(report_paths(manifest)["split"]), "requested_config": config,
        "training_config": adapter.training_config, "vendor": adapter.identity, "dataset": dataset,
    }
    return {**payload, "fingerprint": value_hash(payload), "train_registered": len(dataset["registered_frames"])}


def _checkpoint_files(model_dir):
    result = {}
    for path in (model_dir / "point_cloud").glob("iteration_*/point_cloud.ply"):
        name = path.parent.name.removeprefix("iteration_")
        if name.isdigit() and int(name) > 0 and path.stat().st_size:
            result[int(name)] = path
    return result


def _validate_cfg(model_dir, plan):
    path = model_dir / "cfg_args"
    # Vendor cfg_args is a Python Namespace repr, not JSON. Never eval untrusted files.
    try:
        node = ast.parse(path.read_text(encoding="utf-8"), mode="eval").body
    except SyntaxError as error:
        raise ValueError("Checkpoint cfg_args is malformed. Rerun Phase 4 with --force") from error
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "Namespace" or node.args:
        raise ValueError("Unsupported vendor cfg_args; expected a literal Namespace(...) record")
    if any(item.arg is None for item in node.keywords):
        raise ValueError("Unsupported expanded arguments in cfg_args")
    actual = {item.arg: ast.literal_eval(item.value) for item in node.keywords}
    for key, expected in plan["training_config"]["model"].items():
        if actual.get(key) != expected:
            raise ValueError(f"Checkpoint cfg_args mismatch for {key}: {actual.get(key)!r} != {expected!r}. Retrain with --force")
    return file_hash(path)


def validate_training_cache(model_dir, plan):
    model_dir = Path(model_dir)
    marker_path = model_dir / MARKER_NAME
    if not marker_path.exists():
        if model_dir.exists() and any(model_dir.iterdir()):
            raise ValueError(
                f"Unmarked training output at {model_dir}; it may be an all-frame checkpoint. "
                "BM-5 will not reuse it. Rerun Phase 4 with --force to train the held-out split."
            )
        return None
    marker = read_json(marker_path)
    if marker.get("status") != "completed" or marker.get("fingerprint") != plan["fingerprint"]:
        raise ValueError("BM-5 checkpoint is incomplete or its split/training/vendor/data fingerprint changed. Rerun Phase 4 with --force")
    if _validate_cfg(model_dir, plan) != marker["cfg_args_sha256"]:
        raise ValueError("Checkpoint cfg_args changed after training. Rerun Phase 4 with --force")
    checkpoints = _checkpoint_files(model_dir)
    if set(map(str, checkpoints)) != set(marker["checkpoints"]):
        raise ValueError("The checkpoint iteration set changed after BM-5 training. Rerun Phase 4 with --force")
    for iteration, path in checkpoints.items():
        if file_hash(path) != marker["checkpoints"][str(iteration)]["sha256"]:
            raise ValueError(f"Checkpoint iteration {iteration} changed after BM-5 training. Rerun Phase 4 with --force")
    if not checkpoints or max(checkpoints) != marker["final_iteration"]:
        raise ValueError("BM-5 final checkpoint is missing. Rerun Phase 4 with --force")
    return marker


def mark_training_started(model_dir, plan):
    write_json(Path(model_dir) / MARKER_NAME, {**plan, "status": "training"})


def finish_training(model_dir, plan):
    model_dir = Path(model_dir)
    checkpoints = _checkpoint_files(model_dir)
    expected = plan["requested_config"]["train_iterations"]
    if not checkpoints or max(checkpoints) != expected:
        raise RuntimeError(f"Phase 4: training did not produce its final iteration_{expected}/point_cloud.ply; refusing an earlier checkpoint")
    marker = {
        **plan, "status": "completed", "final_iteration": max(checkpoints),
        "cfg_args_sha256": _validate_cfg(model_dir, plan),
        "checkpoints": {str(iteration): {"path": str(path.relative_to(model_dir)), "sha256": file_hash(path)}
                        for iteration, path in sorted(checkpoints.items())},
    }
    write_json(model_dir / MARKER_NAME, marker)
    return marker


def image_scores(reference, rendered):
    """Full RGB image metrics; neither masking nor averaging MSE across frames."""
    import numpy as np
    from skimage.metrics import structural_similarity

    reference, rendered = np.asarray(reference, dtype=np.float64), np.asarray(rendered, dtype=np.float64)
    if reference.shape != rendered.shape or reference.ndim != 3 or reference.shape[2] != 3:
        raise ValueError("Metric inputs must have identical HxWx3 RGB shapes")
    if min(reference.shape[:2]) < 11:
        raise ValueError("The specified Gaussian SSIM requires dimensions of at least 11 pixels")
    if not np.isfinite(reference).all() or not np.isfinite(rendered).all():
        raise ValueError("Metric inputs contain non-finite values")
    if min(reference.min(), rendered.min()) < 0 or max(reference.max(), rendered.max()) > 1:
        raise ValueError("Metric inputs must be in [0,1]")
    mse = float(np.mean(np.square(reference - rendered), dtype=np.float64))
    psnr = math.inf if mse == 0 else float(-10 * np.log10(mse))
    ssim = float(structural_similarity(reference, rendered, data_range=1.0, channel_axis=-1,
                                       gaussian_weights=True, sigma=1.5, use_sample_covariance=False))
    if not math.isfinite(ssim):
        raise ValueError("SSIM returned a non-finite score")
    return psnr, ssim


def _evaluate_frames(manifest, split, poses, adapter, model, summary, rows):
    np, torch = adapter.np, adapter.torch
    paths = report_paths(manifest)
    cameras = {item["frame"]: item for item in poses["cameras"]}
    failed = {item["frame"]: item["reason"] for item in poses["failed"]}
    excluded = {item["frame"]: item["reason"] for item in split["excluded"] if item["split"] == "test"}
    scores = []
    rendering_failed = False
    background = torch.ones(3, dtype=torch.float32, device="cuda")
    preview_paths = []
    for index, frame in enumerate(split["test"]):
        row = {"frame": frame, "status": "incomplete"}
        camera = None
        try:
            if frame not in split["usable_test"] or frame in excluded:
                raise QualityIncompleteError(f"Excluded test frame: {excluded.get(frame, 'not in usable_test')}")
            if frame in failed or frame not in cameras:
                raise QualityIncompleteError(f"Test localization failed: {failed.get(frame, 'camera missing from test_poses.json')}")
            coverage = split["foreground_coverage"].get(frame)
            if coverage is not None:
                if isinstance(coverage, bool) or not isinstance(coverage, (int, float)) or not math.isfinite(coverage) or not 0 <= coverage <= 1:
                    raise QualityIncompleteError("foreground_coverage must be a finite fraction in [0,1]")
                if coverage == 0:
                    raise QualityIncompleteError("Blank test foreground (coverage=0); fix masking and regenerate the split")
            reference_path = paths["evaluation_images"] / frame
            try:
                row["reference_sha256"] = file_hash(reference_path)
                camera, scaled = adapter.test_camera(cameras[frame], reference_path, index)
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise QualityIncompleteError(str(error)) from error
            row.update(scaled)
            with torch.inference_mode():
                output = adapter.render(camera, model, adapter.pipeline, background)
                rendered_tensor = output["render"]
                if tuple(rendered_tensor.shape) != (3, scaled["height"], scaled["width"]):
                    raise RuntimeError("gaussian_renderer.render['render'] must be an RGB CHW tensor at the camera resolution")
                if not torch.isfinite(rendered_tensor).all().item():
                    raise RuntimeError("Renderer returned non-finite RGB values")
                rendered = rendered_tensor.clamp(0, 1).detach().cpu().numpy().transpose(1, 2, 0)
                reference = camera.original_image.detach().cpu().numpy().transpose(1, 2, 0)
            if np.all(reference == 1):
                raise QualityIncompleteError("Test reference is blank after vendor resolution scaling")
            psnr, ssim = image_scores(reference, rendered)
            paths["quality_previews"].mkdir(parents=True, exist_ok=True)
            preview = {}
            for label, pixels in (("render", rendered), ("reference", reference)):
                path = paths["quality_previews"] / f"bm5_{index:04d}_{label}.png"
                adapter.Image.fromarray(np.rint(pixels * 255).astype(np.uint8)).save(path)
                row[f"{label}_preview"] = str(path)
                preview[label] = str(path)
            preview_paths.append({"frame": frame, **preview})
            scores.append((psnr, ssim))
            row.update(status="evaluated", psnr_db=psnr, ssim=ssim)
        except QualityIncompleteError as error:
            row["error"] = str(error)
            summary["errors"].append(f"{frame}: {error}")
        except Exception as error:
            rendering_failed = True
            row.update(status="failed", error=f"{type(error).__name__}: {error}")
            summary["errors"].append(f"{frame}: {row['error']}")
        finally:
            del camera
        rows.append(row)
        log_info(f"BM5_PROGRESS {index + 1}/{len(split['test'])} {frame}: {row['status']}")
    summary["test_frames"] = len(scores)
    summary["details"]["previews"] = preview_paths
    if scores:
        psnr_mean = float(np.mean([score[0] for score in scores], dtype=np.float64))
        summary["psnr_db"] = psnr_mean if math.isfinite(psnr_mean) else None
        summary["ssim"] = float(np.mean([score[1] for score in scores], dtype=np.float64))
        summary["details"]["psnr_positive_infinity_frames"] = [row["frame"] for row in rows if row.get("psnr_db") == math.inf]
        if not math.isfinite(psnr_mean):
            summary["details"]["psnr_null_reason"] = "Mean PSNR is +infinity (exact image match); CSV records inf, strict JSON records null"
    summary["details"]["metrics_cover_evaluated_frames_only"] = len(scores) != len(split["test"])
    if rendering_failed:
        raise RuntimeError("One or more held-out renders/metrics failed; see per_frame.csv and summary.json")
    if len(scores) != len(split["test"]):
        raise QualityIncompleteError(
            f"Evaluated {len(scores)}/{len(split['test'])} requested test frames. "
            "Fix missing/blank references or failed Phase 3 localization and rerun Phase 4; do not drop requested test frames."
        )


def run_evaluation(manifest_path, model_dir=None, iteration=None, *, preflight=False, config=None):
    _, manifest = load_manifest(manifest_path)
    model_dir = Path(model_dir) if model_dir is not None else Path(manifest["paths"]["geometry"]) / "vanilla_2dgs"
    paths = report_paths(manifest)
    summary, rows = new_summary(manifest), []
    summary["details"].update(stage="preflight" if preflight else "evaluation", model_dir=str(model_dir))
    save_report(manifest, summary, rows)  # Invalidate old scores before any fallible dependency work.
    try:
        for pattern in ("bm5_*_render.png", "bm5_*_reference.png"):
            for path in paths["quality_previews"].glob(pattern):
                path.unlink()
        split, poses = load_inputs(manifest, summary)
        if not preflight:
            marker_path = model_dir / MARKER_NAME
            if not marker_path.is_file():
                raise ValueError(f"No {marker_path}; unmarked/all-frame checkpoints cannot be evaluated. Train BM-5 via Phase 4 with --force")
            config = read_json(marker_path)["requested_config"]
        if config is None:
            raise ValueError("Preflight requires the effective Phase 4 training configuration")
        log_info("BM-5: checking CUDA/vendor API and the train-only dataset...")
        adapter = VendorAdapter(Path(manifest["paths"]["spatial"]), model_dir, config)
        summary["details"].update(vendor=adapter.identity, vendor_dir=str(GS_PATH), environment=adapter.environment)
        summary["settings"]["training"] = adapter.training_config
        plan = prepare_plan(manifest, split, poses, adapter, config)
        summary["train_frames"] = plan["train_registered"]
        summary["details"].update(training_fingerprint=plan["fingerprint"],
                                  training_effective_cameras=plan["dataset"]["effective_cameras"],
                                  resolution_protocol="vendor utils.camera_utils.loadCam(args, ..., resolution_scale=1.0); intrinsics scaled by actual width/height")
        if preflight:
            write_json(paths["quality_training_plan"], plan)
            summary["details"]["stage"] = "ready_for_training"
            save_report(manifest, summary, rows)
            log_info("BM-5 preflight ready; no training or metric rendering was performed")
            return summary
        marker = validate_training_cache(model_dir, plan)
        if marker is None:
            raise ValueError("No validated BM-5 checkpoint is available; run Phase 4 training first")
        selected = marker["final_iteration"] if iteration is None else iteration
        if str(selected) not in marker["checkpoints"]:
            raise ValueError(f"Iteration {selected} is not a checkpoint recorded by this BM-5 training run")
        checkpoint = model_dir / "point_cloud" / f"iteration_{selected}" / "point_cloud.ply"
        summary["train_iterations"] = selected
        summary["details"].update(checkpoint=str(checkpoint), checkpoint_sha256=file_hash(checkpoint),
                                  cfg_args_sha256=marker["cfg_args_sha256"], training_marker=str(model_dir / MARKER_NAME))
        log_info(f"BM-5: evaluating actual checkpoint iteration {selected} on {len(split['test'])} requested test frames")
        with adapter.torch.inference_mode():
            gaussians = adapter.GaussianModel(adapter.model.sh_degree)
            gaussians.load_ply(str(checkpoint))
            if gaussians.get_xyz.shape[0] == 0 or not adapter.torch.isfinite(gaussians.get_xyz).all().item():
                raise RuntimeError("The saved Gaussian checkpoint is empty or contains non-finite positions")
            summary["details"]["gaussians"] = int(gaussians.get_xyz.shape[0])
            _evaluate_frames(manifest, split, poses, adapter, gaussians, summary, rows)
        summary["status"] = "completed"
        summary["details"]["stage"] = "evaluated"
        save_report(manifest, summary, rows)
        log_info(f"BM-5 completed: PSNR={summary['psnr_db']} dB, SSIM={summary['ssim']}; {paths['quality_summary']}")
        return summary
    except (Exception, SystemExit) as error:
        summary["status"] = "incomplete" if isinstance(error, QualityIncompleteError) else "failed"
        summary["errors"].append(f"{type(error).__name__}: {error}")
        save_report(manifest, summary, rows)
        raise RuntimeError(f"Phase 4 BM-5 {summary['status']}: {error}. Report: {paths['quality_summary']}") from error


def main():
    parser = argparse.ArgumentParser(description="BM-5 held-out 2DGS evaluation (no training)")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--iteration", type=int, help="A validated saved iteration; defaults to the final actual checkpoint")
    parser.add_argument("--model-dir", type=Path, help="Defaults to manifest.paths.geometry/vanilla_2dgs")
    parser.add_argument("--preflight", action="store_true", help="Internal Phase 4 dependency/API and train-only data preflight")
    parser.add_argument("--train-iterations", type=int)
    parser.add_argument("--densify-until-iter", type=int)
    parser.add_argument("--opacity-reset-interval", type=int)
    args = parser.parse_args()
    set_phase(4)
    config = {"train_iterations": args.train_iterations, "densify_until_iter": args.densify_until_iter,
              "opacity_reset_interval": args.opacity_reset_interval}
    try:
        run_evaluation(args.manifest, args.model_dir, args.iteration, preflight=args.preflight, config=config)
    except (RuntimeError, ValueError, OSError, KeyError) as error:
        log_error(str(error))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
