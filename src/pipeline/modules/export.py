import argparse
import json
import sys
import time
from pathlib import Path

try:
    import pymeshlab
except ImportError:
    pymeshlab = None


def run_export_and_baking(
    manifest_path: str | Path,
    force: bool = False,
    progress_cb=None,
    log_cb=None,
    is_cancelled=None,
) -> str:
    def log(msg: str):
        if log_cb:
            log_cb(msg)
        else:
            print(f"[*] {msg}")

    def progress(val: float, label: str):
        if progress_cb:
            progress_cb(5, val, label)

    def check_cancel():
        if is_cancelled and is_cancelled():
            raise RuntimeError("Pipeline cancelled by user during Phase 5 (Export)")

    manifest_path = Path(manifest_path).resolve()
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    run_name = manifest["run_name"]
    quality_preset = manifest["settings"]["quality"]

    geometry_dir = Path(manifest["paths"]["geometry"])
    export_dir = Path(manifest["paths"]["export"])

    input_ply = geometry_dir / "fused_mesh.ply"

    if not input_ply.exists():
        raise FileNotFoundError(f"Could not find raw geometry at {input_ply}. Did Phase 4 complete?")

    export_dir.mkdir(parents=True, exist_ok=True)

    final_obj_name = f"{run_name}_{quality_preset}.obj"
    final_texture_name = f"{run_name}_{quality_preset}_tex.png"
    final_obj_path = export_dir / final_obj_name

    # --- SKIP LOGIC ---
    if final_obj_path.exists() and not force:
        log(f"Found existing exported asset: {final_obj_path}")
        manifest["status"]["phase"] = 5
        if "export" not in manifest["status"]["completed"]:
            manifest["status"]["completed"].append("export")
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=4)

        progress(1.0, "Phase 5: Export complete (cached)")
        return str(final_obj_path)
    # ------------------

    if pymeshlab is None:
        raise RuntimeError("pymeshlab is not installed. Please run: pip install pymeshlab")

    start_time = time.perf_counter()
    log("Starting Automated Retopology and Texture Baking Phase...")
    progress(0.0, "Phase 5: Loading mesh...")

    try:
        check_cancel()
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
        check_cancel()
        ms.meshing_decimation_quadric_edge_collapse(
            targetfacenum=target_faces,
            preservenormal=True,
            planarquadric=True,
            preservetopology=True,
        )

        progress(0.45, "Phase 5: Computing normals...")
        ms.compute_normal_per_vertex()

        progress(0.50, "Phase 5: Unwrapping UVs...")
        check_cancel()
        try:
            log("Attempting Voronoi Atlas parameterization...")
            ms.compute_texcoord_parametrization_voronoi_atlas()
        except Exception:
            log("Voronoi failed. Falling back to Trivial Unwrapping...")
            ms.compute_texcoord_parametrization_triangle_trivial_per_wedge(textdim=4096)

        progress(0.80, "Phase 5: Baking 4K texture...")
        check_cancel()
        ms.transfer_attributes_to_texture_per_vertex(
            textname=final_texture_name, textw=4096, texth=4096
        )

        progress(0.95, "Phase 5: Exporting OBJ...")
        check_cancel()
        ms.save_current_mesh(str(final_obj_path))

    except Exception as e:
        raise RuntimeError(f"Fatal error during mesh processing: {e}") from e

    total_time = time.perf_counter() - start_time

    manifest["status"]["phase"] = 5
    if "export" not in manifest["status"]["completed"]:
        manifest["status"]["completed"].append("export")

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    log(f"Export Phase Complete. Final asset: {final_obj_path} ({total_time:.2f}s)")
    progress(1.0, "Phase 5: Export complete")

    return str(final_obj_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 5: Export and Texture Bake")
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--ipc", action="store_true")

    args = parser.parse_args()
    run_export_and_baking(manifest_path=args.manifest, force=args.force)
