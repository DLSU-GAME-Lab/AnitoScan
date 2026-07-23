from dataclasses import dataclass
from pathlib import Path
import time

try:
    import pymeshlab
except ImportError:
    pymeshlab = None

from src.pipeline.core.config import RunCancelled


@dataclass
class ExportResult:
    export_dir: Path
    primary_obj_path: Path
    texture_path: Path | None = None


def run_export_and_baking(
    fused_mesh_path: str | Path,
    output_dir: str | Path,
    run_name: str,
    quality_preset: str = "fast",
    force: bool = False,
    progress_cb=None,
    log_cb=None,
    check_cancelled=None,
    is_cancelled=None,
) -> ExportResult:
    def log(msg: str):
        if log_cb:
            log_cb(msg)
        else:
            print(f"[*] {msg}")

    def progress(val: float, label: str):
        if progress_cb:
            progress_cb(val, label)

    def do_check_cancel():
        if check_cancelled:
            check_cancelled()
        elif is_cancelled and is_cancelled():
            raise RunCancelled("Pipeline cancelled by user during Phase 5 (Export)")

    input_ply = Path(fused_mesh_path).resolve()
    export_dir = Path(output_dir).resolve()

    if not input_ply.exists():
        raise FileNotFoundError(f"Could not find raw geometry at {input_ply}. Did Phase 4 complete?")

    export_dir.mkdir(parents=True, exist_ok=True)

    final_obj_name = f"{run_name}_{quality_preset}.obj"
    final_texture_name = f"{run_name}_{quality_preset}_tex.png"
    final_obj_path = export_dir / final_obj_name
    final_texture_path = export_dir / final_texture_name

    # --- SKIP LOGIC (CACHED) ---
    if final_obj_path.exists() and not force:
        log(f"Found existing exported asset: {final_obj_path}")
        progress(1.0, "Phase 5: Export complete (cached)")
        return ExportResult(
            export_dir=export_dir,
            primary_obj_path=final_obj_path,
            texture_path=final_texture_path if final_texture_path.exists() else None,
        )

    if pymeshlab is None:
        raise RuntimeError("pymeshlab is not installed. Please run: pip install pymeshlab")

    start_time = time.perf_counter()
    log("Starting Automated Retopology and Texture Baking Phase...")
    progress(0.0, "Phase 5: Loading mesh...")

    try:
        do_check_cancel()
        ms = pymeshlab.MeshSet()
        ms.load_new_mesh(str(input_ply))

        progress(0.05, "Phase 5: Cleaning topology...")
        ms.meshing_remove_unreferenced_vertices()
        ms.meshing_remove_duplicate_faces()
        ms.meshing_repair_non_manifold_edges()
        ms.meshing_repair_non_manifold_vertices()

        target_faces = {"fast": 100000, "medium": 300000, "detailed": 600000}.get(
            quality_preset, 300000
        )

        progress(0.15, f"Phase 5: Decimating to {target_faces:,} faces...")
        do_check_cancel()
        ms.meshing_decimation_quadric_edge_collapse(
            targetfacenum=target_faces,
            preservenormal=True,
            planarquadric=True,
            preservetopology=True,
        )

        progress(0.45, "Phase 5: Computing normals...")
        ms.compute_normal_per_vertex()

        progress(0.50, "Phase 5: Unwrapping UVs...")
        do_check_cancel()
        try:
            log("Attempting Voronoi Atlas parameterization...")
            ms.compute_texcoord_parametrization_voronoi_atlas()
        except RunCancelled:
            raise
        except Exception:
            log("Voronoi failed. Falling back to Trivial Unwrapping...")
            ms.compute_texcoord_parametrization_triangle_trivial_per_wedge(textdim=4096)

        progress(0.80, "Phase 5: Baking 4K texture...")
        do_check_cancel()
        ms.transfer_attributes_to_texture_per_vertex(
            textname=final_texture_name, textw=4096, texth=4096
        )

        progress(0.95, "Phase 5: Exporting OBJ...")
        do_check_cancel()
        ms.save_current_mesh(str(final_obj_path))

    except RunCancelled:
        raise
    except Exception as e:
        raise RuntimeError(f"Fatal error during mesh processing: {e}") from e

    total_time = time.perf_counter() - start_time
    log(f"Export Phase Complete. Final asset: {final_obj_path} ({total_time:.2f}s)")
    progress(1.0, "Phase 5: Export complete")

    return ExportResult(
        export_dir=export_dir,
        primary_obj_path=final_obj_path,
        texture_path=final_texture_path if final_texture_path.exists() else None,
    )
