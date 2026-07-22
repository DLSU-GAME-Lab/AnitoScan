import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import trimesh
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import KDTree
from sklearn.neighbors import NearestNeighbors

MODULE_PATH = Path(__file__).resolve()
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models" / "03_spatial"

MAST3R_PATH = PROJECT_ROOT / "vendor" / "mast3r"
DUST3R_PATH = MAST3R_PATH / "dust3r"

for p in [MAST3R_PATH, DUST3R_PATH]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from dust3r.image_pairs import make_pairs
    from dust3r.utils.image import load_images
    from mast3r.cloud_opt.sparse_ga import sparse_global_alignment
    from mast3r.model import AsymmetricMASt3R
except ImportError:
    pass


def convert_masked_frames(source_images, converted_dir):
    converted_images = []
    for png_path in source_images:
        out_path = converted_dir / (Path(png_path).stem + ".jpg")
        if not out_path.exists():
            img = cv2.imread(png_path, cv2.IMREAD_UNCHANGED)
            if img is None:
                continue

            if img.ndim == 3 and img.shape[2] == 4:
                alpha_channel = img[:, :, 3]
                bgr = img[:, :, :3]
                mask = (alpha_channel > 0).astype(np.uint8)
                composited = bgr.copy()
                composited[mask == 0] = 0
            else:
                composited = img

            cv2.imwrite(str(out_path), composited, [cv2.IMWRITE_JPEG_QUALITY, 95])

        converted_images.append(str(out_path))
    return converted_images


def filter_outliers(pts, colors, n_neighbors=20, std_multiplier=2.0):
    if len(pts) < n_neighbors:
        return pts, colors
    nbrs = NearestNeighbors(n_neighbors=n_neighbors).fit(pts)
    distances, _ = nbrs.kneighbors(pts)
    mean_distances = distances[:, 1:].mean(axis=1)

    threshold = mean_distances.mean() + std_multiplier * mean_distances.std()
    mask = mean_distances < threshold
    return pts[mask], colors[mask]


def filter_islands(pts, colors, connection_radius=0.03):
    if len(pts) == 0:
        return pts, colors

    tree = KDTree(pts)
    try:
        pairs = tree.query_pairs(connection_radius, output_type="ndarray")
    except MemoryError:
        pairs = tree.query_pairs(connection_radius * 0.5, output_type="ndarray")

    if len(pairs) == 0:
        return pts, colors

    n = len(pts)
    adj = csr_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))

    n_comp, labels = connected_components(adj, directed=False)
    unique, counts = np.unique(labels, return_counts=True)
    biggest_island_label = unique[np.argmax(counts)]

    mask = labels == biggest_island_label
    return pts[mask], colors[mask]


def run_spatial_reconstruction(
    manifest_path: str | Path,
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
            progress_cb(3, val, label)

    def check_cancel():
        if is_cancelled and is_cancelled():
            raise RuntimeError("Pipeline cancelled by user during Phase 3 (Spatial)")

    manifest_path = Path(manifest_path).resolve()
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    input_dir = Path(manifest["paths"]["masked_frames"])
    output_dir = Path(manifest["paths"]["spatial"])

    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    if force and output_dir.exists():
        log(f"Force flag detected. Wiping: {output_dir}")
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    required_artifacts = ["transforms.json", "init_points.ply"]
    if output_dir.exists() and not force:
        artifacts_present = all((output_dir / f).exists() for f in required_artifacts)
        if artifacts_present:
            log(f"Found completed artifacts in {output_dir}. Skipping spatial reconstruction.")
            manifest["status"]["phase"] = 3
            if "spatial" not in manifest["status"]["completed"]:
                manifest["status"]["completed"].append("spatial")
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=4)
            progress(1.0, "Phase 3: Spatial complete (cached)")
            return

    all_images = sorted([str(p) for p in input_dir.glob("*.png")])
    total_available = len(all_images)

    if total_available < 2:
        raise ValueError(f"Found only {total_available} masked frames in {input_dir}")

    N = 1 if total_available <= 30 else 3
    source_images = all_images[::N]

    converted_dir = output_dir / "converted_for_mast3r"
    converted_dir.mkdir(exist_ok=True)

    log("Converting masked frames...")
    source_images = convert_masked_frames(source_images, converted_dir)
    total_images = len(source_images)

    if total_images < 2:
        raise ValueError(f"MASt3R requires at least 2 images. Got {total_images}.")

    device = (
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )

    log(f"Initializing MASt3R on device: {device}")
    model_path = str(MODELS_DIR / "MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric")
    model = AsymmetricMASt3R.from_pretrained(model_path).to(device)
    model.eval()

    imgs_meta = load_images(source_images, size=512)
    n = len(imgs_meta)

    swin_size = min(10, n)
    pairs_swin = make_pairs(imgs_meta, scene_graph=f"swin-{swin_size}", symmetrize=True)

    pairs_boundary = []
    if n > 10:
        actual_window = min(n // 2, 15)
        boundary_indices = sorted(
            list(set(list(range(actual_window)) + list(range(n - actual_window, n))))
        )
        boundary_imgs = [imgs_meta[i] for i in boundary_indices]
        pairs_boundary = make_pairs(
            boundary_imgs, scene_graph="complete", symmetrize=True
        )

    pairs = pairs_swin + pairs_boundary
    log(f"Total pairs: {len(pairs)} (swin-{swin_size}): {len(pairs_swin)} + boundary: {len(pairs_boundary)}")

    cache_path = output_dir / "matching_cache"
    cache_path.mkdir(exist_ok=True)

    log(f"Running Sparse Global Alignment on {total_images} frames...")
    start_perf = time.perf_counter()

    check_cancel()
    scene = sparse_global_alignment(
        imgs=source_images,
        pairs_in=pairs,
        model=model,
        device=device,
        cache_path=str(cache_path),
        niter1=500,
        niter2=300,
    )

    poses = scene.get_im_poses().detach().cpu().numpy()
    focals = scene.get_focals().detach().cpu().numpy()
    principal_points = scene.get_principal_points().detach().cpu().numpy()

    pts3d_raw = scene.pts3d
    colors_raw = scene.pts3d_colors

    pts3d_world_list = []
    colors_list = []

    for pts_cam, col in zip(pts3d_raw, colors_raw):
        pts = (
            pts_cam.detach().cpu().numpy()
            if not isinstance(pts_cam, np.ndarray)
            else pts_cam
        )
        col = col.detach().cpu().numpy() if not isinstance(col, np.ndarray) else col

        is_not_black = np.any(col > 0.05, axis=1)
        pts = pts[is_not_black]
        col = col[is_not_black]

        if len(pts) == 0:
            continue

        pts3d_world_list.append(pts)
        colors_list.append(col)

    pts3d_all = np.concatenate(pts3d_world_list, axis=0)
    colors_float = np.concatenate(colors_list, axis=0)

    pts3d_all, colors_float = filter_outliers(pts3d_all, colors_float)
    pts3d_all, colors_float = filter_islands(pts3d_all, colors_float)
    colors_all = (colors_float * 255).astype(np.uint8)

    transforms = {"camera_model": "PINHOLE", "frames": []}

    for i, path in enumerate(source_images):
        h, w = cv2.imread(path).shape[:2]
        transforms["frames"].append(
            {
                "file_path": f"./{Path(path).name}",
                "transform_matrix": poses[i].tolist(),
                "focal_length": float(focals[i]),
                "cx": float(principal_points[i, 0]),
                "cy": float(principal_points[i, 1]),
                "w": w,
                "h": h,
            }
        )

    with open(output_dir / "transforms.json", "w") as f:
        json.dump(transforms, f, indent=4)

    pc = trimesh.PointCloud(vertices=pts3d_all, colors=colors_all)
    pc.export(str(output_dir / "init_points.ply"))

    total_time = time.perf_counter() - start_perf

    manifest["status"]["phase"] = 3
    if "spatial" not in manifest["status"]["completed"]:
        manifest["status"]["completed"].append("spatial")

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    log(f"Spatial Reconstruction Complete. Total Time: {total_time:.2f}s")
    progress(1.0, "Phase 3: Spatial complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--ipc", action="store_true")

    args = parser.parse_args()
    run_spatial_reconstruction(args.manifest, force=args.force)
