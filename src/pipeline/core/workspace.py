from pathlib import Path
from typing import Any

from manifest import build_manifest, initialize_manifest, load_manifest

CACHE_RELEVANT_FIELDS = [
    ("run_name",),
    ("input_source",),
    ("mode",),
    ("settings", "minimum_frames"),
    ("settings", "quality"),
    ("settings", "capture_mode"),
    ("settings", "yoloe_model_size"),
    ("settings", "iou_threshold"),
    ("settings", "drift_limit"),
]


def _nested_get(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _format_field(keys: tuple[str, ...]) -> str:
    return ".".join(keys)


def _is_editor_pending_manifest(manifest: dict[str, Any]) -> bool:
    """Returns whether an editor stub is waiting to be expanded by the real pipeline."""
    status = manifest.get("status")
    return isinstance(status, dict) and status.get("state") == "pending"


def _find_manifest_conflicts(existing: dict[str, Any], desired: dict[str, Any]) -> list[str]:
    conflicts: list[str] = []

    for keys in CACHE_RELEVANT_FIELDS:
        existing_value = _nested_get(existing, keys)
        desired_value = _nested_get(desired, keys)
        if existing_value != desired_value:
            conflicts.append(
                f"{_format_field(keys)}: existing={existing_value!r}, requested={desired_value!r}"
            )

    return conflicts


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

    desired_manifest = build_manifest(name, input_path, args, paths_dict)
    force = bool(args.get("force", False))

    if manifest_path.exists():
        pending_upgrade = False
        try:
            _, existing_manifest = load_manifest(manifest_path)
        except (OSError, ValueError) as error:
            if not force:
                raise RuntimeError(
                    f"Existing manifest at {manifest_path} could not be read. "
                    "Use --force to recreate this run folder's manifest, or choose a new --name."
                ) from error
        else:
            pending_upgrade = _is_editor_pending_manifest(existing_manifest)
            conflicts = _find_manifest_conflicts(existing_manifest, desired_manifest)
            if conflicts and not force and not pending_upgrade:
                conflict_lines = "\n".join(f"  - {conflict}" for conflict in conflicts)
                raise RuntimeError(
                    "This run folder already exists with different cache-relevant settings.\n"
                    f"Run folder: {base_dir}\n"
                    f"Conflicts:\n{conflict_lines}\n"
                    "Use --force to rebuild the run with the requested settings, or choose a new --name."
                )

        if not force and not pending_upgrade:
            return base_dir, manifest_path

    initialize_manifest(manifest_path, name, input_path, args, paths_dict)

    return base_dir, manifest_path
