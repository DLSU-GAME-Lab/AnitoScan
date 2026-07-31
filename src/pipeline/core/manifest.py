import json
from pathlib import Path
from typing import Any

PHASE_NAMES = {
    1: "capture",
    2: "masking",
    3: "spatial",
    4: "geometry",
    5: "export",
}

__all__ = ["build_manifest", "initialize_manifest", "load_manifest", "update_manifest"]


def build_manifest(
    name: str,
    input_path: Path,
    args: dict,
    paths_dict: dict,
) -> dict:
    """Builds the manifest schema for a pipeline invocation without saving it."""
    capture_mode = "image" if args.get("image") else "video" if args.get("video") else "auto"

    return {
        "run_name": name,
        "input_source": str(input_path),
        "mode": args.get("mode", "disk"),
        "settings": {
            "minimum_frames": args.get("minimum_frames", 45),
            "quality": args.get("quality", "fast"),
            "capture_mode": capture_mode,
            "yoloe_model_size": args.get("yoloe_model_size", "s"),
            "iou_threshold": args.get("iou_threshold", 0.50),
            "drift_limit": args.get("drift_limit", 200),
        },
        "status": {
            "phase": 0,
            "completed": [],
        },
        "paths": paths_dict,
    }


def initialize_manifest(
    manifest_path: Path,
    name: str,
    input_path: Path,
    args: dict,
    paths_dict: dict,
) -> dict:
    """Creates the initial manifest schema and saves it to disk."""
    manifest = build_manifest(name, input_path, args, paths_dict)
    _save_manifest(manifest_path, manifest)
    return manifest


def load_manifest(manifest_path: str | Path) -> tuple[Path, dict[str, Any]]:
    """Loads and parses the manifest JSON, returning its resolved Path and data dictionary."""
    path = Path(manifest_path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    return path, data


def update_manifest(
    manifest_path: Path,
    manifest: dict,
    phase: int,
    source_type: str | None = None,
) -> None:
    """Updates phase status, completion tracking, and optional settings in the manifest."""
    phase_name = PHASE_NAMES.get(phase)

    if phase_name:
        manifest["status"]["phase"] = phase
        if phase_name not in manifest["status"]["completed"]:
            manifest["status"]["completed"].append(phase_name)

    if source_type:
        manifest["settings"]["source_type"] = source_type

    _save_manifest(manifest_path, manifest)


def _save_manifest(manifest_path: Path, manifest_data: dict) -> None:
    """Saves the manifest dictionary back to disk formatted cleanly."""
    manifest_path.write_text(json.dumps(manifest_data, indent=4), encoding="utf-8")
