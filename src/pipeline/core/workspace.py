import re
from pathlib import Path
from typing import Any

from manifest import (
    build_manifest,
    initialize_manifest,
    load_manifest,
    update_manifest_settings,
)

INVALID_RUN_NAME_PATTERN = re.compile(r'[<>:"/\\|?*]|[\x00-\x1f]')

CACHE_RELEVANT_FIELDS = [
    ("run_name",),
    ("input_source",),
    ("mode",),
    ("settings", "minimum_frames"),
    # ("settings", "quality"),
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


def _validate_run_name(name: Any, workspace_dir: Path) -> str:
    if (
        not isinstance(name, str)
        or not name
        or name in {".", ".."}
        or name.endswith((" ", "."))
        or INVALID_RUN_NAME_PATTERN.search(name) is not None
    ):
        raise ValueError(f"Invalid run name: {name!r}")

    workspace_root = workspace_dir.resolve()
    run_root = (workspace_root / name).resolve()
    if run_root.parent != workspace_root:
        raise ValueError(f"Run name escapes the workspace directory: {name!r}")
    return name


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


def init_workspace(
    project_root: Path,
    workspace_dir: Path,
    args: dict,
    validate_input: bool = True,
) -> tuple[Path, Path]:
    """Create the run folder tree and initial manifest, optionally validating input."""
    name = _validate_run_name(args.get("name") or "unnamed_run", workspace_dir)
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
    if validate_input and not input_path.exists():
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
        try:
            _, existing_manifest = load_manifest(manifest_path)
        except (OSError, ValueError) as error:
            if not force:
                raise RuntimeError(
                    f"Existing manifest at {manifest_path} could not be read. "
                    "Use --force to recreate this run folder's manifest, or choose a new --name."
                ) from error
        else:
            conflicts = _find_manifest_conflicts(existing_manifest, desired_manifest)
            if conflicts and not force:
                conflict_lines = "\n".join(f"  - {conflict}" for conflict in conflicts)
                raise RuntimeError(
                    "This run folder already exists with different cache-relevant settings.\n"
                    f"Run folder: {base_dir}\n"
                    f"Conflicts:\n{conflict_lines}\n"
                    "Use --force to rebuild the run with the requested settings, or choose a new --name."
                )

        if not force:
            update_manifest_settings(
                manifest_path,
                existing_manifest,
                {
                    "quality": desired_manifest["settings"]["quality"],
                },
            )
            return base_dir, manifest_path


    initialize_manifest(manifest_path, name, input_path, args, paths_dict)

    return base_dir, manifest_path
