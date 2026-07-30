import argparse
import sys
import time
from pathlib import Path
from typing import Any

import pymeshlab

core_path = str(Path(__file__).resolve().parent.parent / "core")
sys.path.insert(0, core_path)

from log import log_error, log_info, log_progress, set_ipc_mode, set_phase
from manifest import load_manifest, update_manifest


def _mesh_processing_exceptions() -> tuple[type[BaseException], ...]:
    exception_types: list[type[BaseException]] = [RuntimeError, ValueError, OSError]

    for container in (pymeshlab, getattr(pymeshlab, "pmeshlab", None)):
        exception_type = getattr(container, "PyMeshLabException", None)
        if (
            isinstance(exception_type, type)
            and issubclass(exception_type, BaseException)
            and exception_type not in exception_types
        ):
            exception_types.append(exception_type)

    return tuple(exception_types)


MESH_PROCESSING_EXCEPTIONS = _mesh_processing_exceptions()


def _compute_uv_parameterization(ms: Any) -> None:
    uv_strategies = [
        (
            "Voronoi Atlas",
            "compute_texcoord_parametrization_voronoi_atlas",
            {},
        ),
        (
            "Harmonic",
            "compute_texcoord_parametrization_harmonic",
            {},
        ),
        (
            "Trivial Per-Wedge",
            "compute_texcoord_parametrization_triangle_trivial_per_wedge",
            {"textdim": 4096},
        ),
    ]

    last_error: BaseException | None = None

    for label, method_name, kwargs in uv_strategies:
        method = getattr(ms, method_name, None)
        if method is None:
            log_info(f"{label} parameterization is unavailable in this PyMeshLab build.")
            continue

        try:
            log_info(f"Attempting {label} parameterization...")
            method(**kwargs)
            return
        except MESH_PROCESSING_EXCEPTIONS as uv_error:
            last_error = uv_error
            log_info(f"{label} failed ({uv_error}). Trying next UV unwrap strategy...")

    error_details = f" Last error: {last_error}" if last_error else ""
    raise RuntimeError(f"No supported UV parameterization method succeeded.{error_details}")


def run_export_and_baking(manifest_path_string: str, force: bool = False, ipc_mode: bool = False):
    set_ipc_mode(ipc_mode)
    set_phase(5)

    manifest_path, manifest = load_manifest(manifest_path_string)

    run_name = manifest["run_name"]
    quality_preset = manifest["settings"]["quality"]

    geometry_dir = Path(manifest["paths"]["geometry"])
    export_dir = Path(manifest["paths"]["export"])

    input_ply = geometry_dir / "fused_mesh.ply"

    if not input_ply.exists():
        raise FileNotFoundError(
            f"Could not find raw geometry at {input_ply}. Did Phase 4 complete?"
        )

    export_dir.mkdir(parents=True, exist_ok=True)

    # Format the final asset names
    final_obj_name = f"{run_name}_{quality_preset}.obj"
    final_texture_name = f"{run_name}_{quality_preset}_tex.png"

    final_obj_path = export_dir / final_obj_name

    # --- SKIP LOGIC ---
    if final_obj_path.exists() and not force:
        log_info(f"Found existing exported asset: {final_obj_path}")
        log_info("Skipping Phase 5 (Export & Baking)...")
        update_manifest(manifest_path, manifest, phase=5)
        log_progress(1.0, "Phase 5: Export complete (cached)")
        return
    # ------------------

    start_time = time.perf_counter()

    log_info("Starting Automated Retopology and Texture Baking Phase...")
    log_progress(0.0, "Phase 5: Loading mesh...")

    try:
        ms = pymeshlab.MeshSet()  # type: ignore
        ms.load_new_mesh(str(input_ply))

        log_info("Mesh loaded. Cleaning raw topology...")
        log_progress(0.05, "Phase 5: Cleaning topology...")
        ms.meshing_remove_unreferenced_vertices()
        ms.meshing_remove_duplicate_faces()
        ms.meshing_repair_non_manifold_edges()
        ms.meshing_repair_non_manifold_vertices()

        # --- AUTOMATED RETOPOLOGY / REMESHING ---
        # Map the pipeline quality preset to a target polycount
        target_faces = {"fast": 100000, "medium": 300000, "detailed": 600000}.get(
            quality_preset, 300000
        )

        log_info(f"Decimating and smoothing mesh to {target_faces:,} faces...")
        log_progress(0.15, f"Phase 5: Decimating to {target_faces:,} faces...")

        ms.meshing_decimation_quadric_edge_collapse(
            targetfacenum=target_faces,
            preservenormal=True,
            planarquadric=True,
            preservetopology=True,
        )

        log_info("Generating smooth surface normals...")
        log_progress(0.45, "Phase 5: Computing normals...")
        ms.compute_normal_per_vertex()

        log_info("Unwrapping UV Coordinates...")
        log_progress(0.50, "Phase 5: Unwrapping UVs...")
        _compute_uv_parameterization(ms)

        log_info(f"Baking vertex colors to {final_texture_name} (4K Resolution)...")
        log_progress(0.80, "Phase 5: Baking 4K texture...")
        ms.transfer_attributes_to_texture_per_vertex(
            textname=final_texture_name, textw=4096, texth=4096
        )

        log_info(f"Exporting final optimized OBJ package to {export_dir}...")
        log_progress(0.95, "Phase 5: Exporting OBJ...")
        ms.save_current_mesh(str(final_obj_path))

    except MESH_PROCESSING_EXCEPTIONS as error:
        raise RuntimeError(
            f"A fatal error occurred during mesh processing: {error}"
        ) from error

    update_manifest(manifest_path, manifest, phase=5)

    total_time = time.perf_counter() - start_time

    log_info(f"Export Phase Complete. Final textured asset ready: {final_obj_path}")
    log_info(f"Phase 5 Total Time: {total_time:.2f}s")
    log_progress(1.0, "Phase 5: Export complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 5: Export and Texture Bake")
    parser.add_argument("--manifest", type=str, required=True, help="Path to project manifest.json")
    parser.add_argument("--force", action="store_true", help="Overwrite existing export data")
    parser.add_argument("--ipc", action="store_true")

    args = parser.parse_args()

    try:
        run_export_and_baking(
            manifest_path_string=args.manifest, force=args.force, ipc_mode=args.ipc
        )
    except (RuntimeError, ValueError, OSError) as error:
        log_error(str(error))
        sys.exit(1)
