from pathlib import Path

from manifest import initialize_manifest


def init_workspace(project_root: Path, workspace_dir: Path, args: dict) -> tuple[Path, Path]:
    """Creates the run folder tree, validates input, and writes initial manifest.json."""
    name = args.get("name") or "unnamed_run"
    input_src = args.get("input") or ""

    base_dir = (workspace_dir / name).resolve()
    capture_dir = base_dir / "01_capture"
    mask_dir = base_dir / "02_masking"
    spatial_dir = base_dir / "03_spatial"
    geometry_dir = base_dir / "04_geometry"
    export_dir = (project_root / "data" / "output" / name).resolve()
    manifest_path = base_dir / "manifest.json"

    for d in [capture_dir, mask_dir, spatial_dir, geometry_dir, export_dir]:
        d.mkdir(parents=True, exist_ok=True)

    input_path = (project_root / "data" / "input" / input_src).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input source not found: {input_src}")

    paths_dict = {
        "run_root": str(base_dir),
        "raw_frames": str(capture_dir),
        "masked_frames": str(mask_dir),
        "spatial": str(spatial_dir),
        "geometry": str(geometry_dir),
        "export": str(export_dir),
    }

    initialize_manifest(manifest_path, name, input_path, args, paths_dict)

    return base_dir, manifest_path
