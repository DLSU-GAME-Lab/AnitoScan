import argparse
import sys
import time
from pathlib import Path

import pymeshlab

core_path = str(Path(__file__).resolve().parent.parent / "core")
sys.path.insert(0, core_path)

from benchmark import append_failed_phase_benchmark, append_phase_benchmark
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
EXPORT_PROCESSING_EXCEPTIONS = (*MESH_PROCESSING_EXCEPTIONS, AttributeError)


def run_export_and_baking(manifest_path_string: str, force: bool = False, ipc_mode: bool = False):
    set_ipc_mode(ipc_mode)
    set_phase(5)

    manifest_path, manifest = load_manifest(manifest_path_string)
    phase_start = time.perf_counter()

    run_name = manifest["run_name"]
    quality_preset = manifest["settings"]["quality"]

    geometry_dir = Path(manifest["paths"]["geometry"])
    export_dir = Path(manifest["paths"]["export"])

    input_ply = geometry_dir / "fused_mesh.ply"
    target_faces = {"fast": 100000, "medium": 300000, "detailed": 600000}.get(
        quality_preset, 300000
    )
    benchmark_settings = {
        "force": force,
        "quality_preset": quality_preset,
        "target_faces": target_faces,
        "uv_method": "trivial_per_wedge",
        "texture_width": 4096,
        "texture_height": 4096,
    }
    benchmark_metrics = {
        "input_mesh_bytes": input_ply.stat().st_size if input_ply.exists() else 0,
        "final_obj_exists": False,
        "final_obj_bytes": 0,
        "final_texture_exists": False,
        "final_texture_bytes": 0,
        "mesh_loaded": False,
        "topology_cleaned": False,
        "decimated": False,
        "normals_computed": False,
        "uv_unwrapped": False,
        "texture_baked": False,
    }

    if not input_ply.exists():
        error = FileNotFoundError(
            f"Could not find raw geometry at {input_ply}. Did Phase 4 complete?"
        )
        append_failed_phase_benchmark(
            manifest,
            5,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths={"input_mesh": input_ply, "export_dir": export_dir},
            error=error,
        )
        raise error

    export_dir.mkdir(parents=True, exist_ok=True)

    # Format the final asset names
    final_obj_name = f"{run_name}_{quality_preset}.obj"
    final_texture_name = f"{run_name}_{quality_preset}_tex.png"

    final_obj_path = export_dir / final_obj_name
    final_texture_path = export_dir / final_texture_name
    benchmark_paths = {
        "input_mesh": input_ply,
        "export_dir": export_dir,
        "final_obj": final_obj_path,
        "final_texture": final_texture_path,
    }

    # --- SKIP LOGIC ---
    if final_obj_path.exists() and not force:
        log_info(f"Found existing exported asset: {final_obj_path}")
        log_info("Skipping Phase 5 (Export & Baking)...")
        update_manifest(manifest_path, manifest, phase=5)
        append_phase_benchmark(
            manifest,
            5,
            status="skipped",
            skipped=True,
            duration_seconds=time.perf_counter() - phase_start,
            settings=benchmark_settings,
            metrics={"final_obj_exists": final_obj_path.exists()},
            paths=benchmark_paths,
        )
        log_progress(1.0, "Phase 5: Export complete (cached)")
        return
    # ------------------

    log_info("Starting Automated Retopology and Texture Baking Phase...")
    log_progress(0.0, "Phase 5: Loading mesh...")

    try:
        ms = pymeshlab.MeshSet()  # type: ignore
        ms.load_new_mesh(str(input_ply))
        benchmark_metrics["mesh_loaded"] = True

        log_info("Mesh loaded. Cleaning raw topology...")
        log_progress(0.05, "Phase 5: Cleaning topology...")
        ms.meshing_remove_unreferenced_vertices()
        ms.meshing_remove_duplicate_faces()
        ms.meshing_repair_non_manifold_edges()
        ms.meshing_repair_non_manifold_vertices()
        benchmark_metrics["topology_cleaned"] = True

        # --- AUTOMATED RETOPOLOGY / REMESHING ---
        # Map the pipeline quality preset to a target polycount
        log_info(f"Decimating and smoothing mesh to {target_faces:,} faces...")
        log_progress(0.15, f"Phase 5: Decimating to {target_faces:,} faces...")

        ms.meshing_decimation_quadric_edge_collapse(
            targetfacenum=target_faces,
            preservenormal=True,
            planarquadric=True,
            preservetopology=True,
        )
        benchmark_metrics["decimated"] = True

        log_info("Generating smooth surface normals...")
        log_progress(0.45, "Phase 5: Computing normals...")
        ms.compute_normal_per_vertex()
        benchmark_metrics["normals_computed"] = True

        log_info("Unwrapping UV Coordinates...")
        log_progress(0.50, "Phase 5: Unwrapping UVs...")
        log_info("Using Trivial Per-Wedge parameterization...")
        ms.compute_texcoord_parametrization_triangle_trivial_per_wedge(textdim=4096)
        benchmark_metrics["uv_unwrapped"] = True

        log_info(f"Baking vertex colors to {final_texture_name} (4K Resolution)...")
        log_progress(0.80, "Phase 5: Baking 4K texture...")
        ms.transfer_attributes_to_texture_per_vertex(
            textname=final_texture_name, textw=4096, texth=4096
        )
        benchmark_metrics["texture_baked"] = True

        log_info(f"Exporting final optimized OBJ package to {export_dir}...")
        log_progress(0.95, "Phase 5: Exporting OBJ...")
        ms.save_current_mesh(str(final_obj_path))

    except EXPORT_PROCESSING_EXCEPTIONS as error:
        append_failed_phase_benchmark(
            manifest,
            5,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        raise RuntimeError(
            f"A fatal error occurred during mesh processing: {error}"
        ) from error

    update_manifest(manifest_path, manifest, phase=5)

    total_time = time.perf_counter() - phase_start
    append_phase_benchmark(
        manifest,
        5,
        status="completed",
        skipped=False,
        duration_seconds=total_time,
        settings=benchmark_settings,
        metrics={
            **benchmark_metrics,
            "input_mesh_bytes": input_ply.stat().st_size if input_ply.exists() else 0,
            "final_obj_exists": final_obj_path.exists(),
            "final_obj_bytes": final_obj_path.stat().st_size if final_obj_path.exists() else 0,
            "final_texture_exists": final_texture_path.exists(),
            "final_texture_bytes": final_texture_path.stat().st_size if final_texture_path.exists() else 0,
        },
        paths=benchmark_paths,
    )

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
