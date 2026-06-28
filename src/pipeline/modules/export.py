import argparse
import json
import sys
import time
from pathlib import Path

core_path = str(Path(__file__).resolve().parent.parent / "core")
sys.path.insert(0, core_path)

from ipc import send_log, send_progress, send_error, status_error, status_update

try:
    import pymeshlab
except ImportError:
    print("[!] ERROR: pymeshlab is not installed. Please run: pip install pymeshlab")
    sys.exit(1)


def run_export_and_baking(manifest_path, force=False, ipc_mode=False):
    # 1. Load Manifest Context
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    run_name = manifest["run_name"]
    quality_preset = manifest["settings"]["quality"]

    geometry_dir = Path(manifest["paths"]["geometry"])
    export_dir = Path(manifest["paths"]["export"])

    input_ply = geometry_dir / "fused_mesh.ply"

    if not input_ply.exists():
        status_error(f"Could not find raw geometry at {input_ply}. Did Phase 4 complete?")
        sys.exit(1)

    export_dir.mkdir(parents=True, exist_ok=True)

    # Format the final asset names
    final_obj_name = f"{run_name}_{quality_preset}.obj"
    final_texture_name = f"{run_name}_{quality_preset}_tex.png"

    final_obj_path = export_dir / final_obj_name

    # --- SKIP LOGIC ---
    if final_obj_path.exists() and not force:
        status_update(f"Found existing exported asset: {final_obj_path}",
                      progress=1.0,
                      progress_msg="Phase 5: Export complete (cached)", 
                      phase=5)
        status_update("Skipping Phase 5 (Export & Baking)...")
        print("PROGRESS: 100") 
        
        return
    # ------------------

    start_time = time.perf_counter()
    print("\n")
    status_update("Starting Automated Retopology and Texture Baking Phase...",
                  progress=0.0,
                  progress_msg="Phase 5: Loading mesh...",
                  phase=5)

    try:
        ms = pymeshlab.MeshSet()  # type: ignore
        ms.load_new_mesh(str(input_ply))

        status_update("Mesh loaded. Cleaning raw topology...",
                      progress=0.05,
                      progress_msg="Phase 5: Cleaning topology...",
                      phase=5)
        ms.meshing_remove_unreferenced_vertices()
        ms.meshing_remove_duplicate_faces()
        ms.meshing_repair_non_manifold_edges()
        ms.meshing_repair_non_manifold_vertices()

        # --- NEW: AUTOMATED RETOPOLOGY / REMESHING ---
        # Map the pipeline quality preset to a target polycount
        target_faces = {"fast": 100000, "medium": 300000, "detailed": 600000}.get(
            quality_preset, 300000
        )

        # DECIMATION
        status_update(f"Decimating and smoothing mesh to {target_faces:,} faces...",
                      progress=0.15,
                      progress_msg=f"Phase 5: Decimating to {target_faces:,} faces...",
                      phase=5)

        ms.meshing_decimation_quadric_edge_collapse(
            targetfacenum=target_faces,
            preservenormal=True,
            planarquadric=True,
            preservetopology=True,
        )

        # COMPUTE NORMALS
        status_update("Generating smooth surface normals...",
                      progress=0.45,
                      progress_msg="Phase 5: Computing normals...",
                      phase=5)
        ms.compute_normal_per_vertex()

        # UNWRAP UVs
        status_update("Unwrapping UV Coordinates...",
                      progress=0.50,
                      progress_msg="Phase 5: Unwrapping UVs...",
                      phase=5)
        try:
            # Primary Strategy: Voronoi Atlas
            status_update("Attempting Voronoi Atlas parameterization...")
            ms.compute_texcoord_parametrization_voronoi_atlas()
        except Exception as uv_error:
            # Fallback Strategy: Trivial Per-Wedge
            status_update("Voronoi failed. Falling back to Trivial Unwrapping...")
            ms.compute_texcoord_parametrization_triangle_trivial_per_wedge(textdim=4096)

        # BAKING
        status_update(f"Baking vertex colors to {final_texture_name} (4K Resolution)...",
                      progress=0.80,
                      progress_msg="Phase 5: Baking 4K texture...",
                      phase=5)
        ms.transfer_attributes_to_texture_per_vertex(
            textname=final_texture_name, textw=4096, texth=4096
        )

        # EXPORT
        status_update(f"Exporting final optimized OBJ package to {export_dir}...",
                      progress=0.95,
                      progress_msg="Phase 5: Exporting OBJ...",
                      phase=5)
        ms.save_current_mesh(str(final_obj_path))

    except Exception as e:
        print("\n")
        status_error(f"A fatal error occurred during mesh processing: {e}")
        sys.exit(1)

    total_time = time.perf_counter() - start_time

    manifest["status"]["phase"] = 5
    if "export" not in manifest["status"]["completed"]:
        manifest["status"]["completed"].append("export")

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    print("\nPROGRESS: 100")
    status_update(f"Export Phase Complete. Final textured asset ready: {final_obj_path}")
    status_update(f"Phase 5 Total Time: {total_time:.2f}s")
    if ipc_mode: send_progress(1.0, "Phase 5: Export complete", phase=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 5: Export and Texture Bake")
    parser.add_argument(
        "--manifest", type=str, required=True, help="Path to project manifest.json"
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing export data"
    )
    parser.add_argument("--ipc", action="store_true")

    args = parser.parse_args()

    run_export_and_baking(manifest_path=args.manifest, force=args.force, ipc_mode=args.ipc)
