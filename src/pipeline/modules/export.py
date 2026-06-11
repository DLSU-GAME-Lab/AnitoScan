import argparse
import json
import sys
import time
from pathlib import Path

try:
    import pymeshlab
except ImportError:
    print("[!] ERROR: pymeshlab is not installed. Please run: pip install pymeshlab")
    sys.exit(1)


def run_export_and_baking(manifest_path, force=False):
    # 1. Load Manifest Context
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    run_name = manifest["run_name"]
    quality_preset = manifest["settings"]["quality"]

    geometry_dir = Path(manifest["paths"]["geometry"])
    export_dir = Path(manifest["paths"]["export"])

    input_ply = geometry_dir / "fused_mesh.ply"

    if not input_ply.exists():
        print(
            f"[!] Error: Could not find raw geometry at {input_ply}. Did Phase 4 complete?"
        )
        sys.exit(1)

    export_dir.mkdir(parents=True, exist_ok=True)

    # Format the final asset names
    final_obj_name = f"{run_name}_{quality_preset}.obj"
    final_texture_name = f"{run_name}_{quality_preset}_tex.png"

    final_obj_path = export_dir / final_obj_name

    # --- SKIP LOGIC ---
    if final_obj_path.exists() and not force:
        print(f"[*] Found existing exported asset: {final_obj_path}")
        print("[*] Skipping Phase 5 (Export & Baking)... (Use --force to override)")
        print("PROGRESS: 100")
        return
    # ------------------

    start_time = time.perf_counter()
    print("\n[*] Starting Automated Retopology and Texture Baking Phase...")

    try:
        ms = pymeshlab.MeshSet()  # type: ignore
        ms.load_new_mesh(str(input_ply))

        print("[*] Mesh loaded. Cleaning raw topology...")
        ms.meshing_remove_unreferenced_vertices()
        ms.meshing_remove_duplicate_faces()
        ms.meshing_repair_non_manifold_edges()
        ms.meshing_repair_non_manifold_vertices()

        # --- NEW: AUTOMATED RETOPOLOGY / REMESHING ---
        # Map the pipeline quality preset to a target polycount
        target_faces = {"fast": 100000, "medium": 300000, "detailed": 600000}.get(
            quality_preset, 300000
        )

        print(f"[*] Decimating and smoothing mesh to {target_faces:,} faces...")
        ms.meshing_decimation_quadric_edge_collapse(
            targetfacenum=target_faces,
            preservenormal=True,
            planarquadric=True,
            preservetopology=True,
        )

        print("[*] Generating smooth surface normals...")
        ms.compute_normal_per_vertex()

        print("[*] Unwrapping UV Coordinates...")
        try:
            # Primary Strategy: Voronoi Atlas
            print("    -> Attempting Voronoi Atlas parameterization...")
            ms.compute_texcoord_parametrization_voronoi_atlas()
        except Exception as uv_error:
            # Fallback Strategy: Trivial Per-Wedge
            print(f"    [!] Voronoi failed. Falling back to Trivial Unwrapping...")
            ms.compute_texcoord_parametrization_triangle_trivial_per_wedge(textdim=4096)

        print(f"[*] Baking vertex colors to {final_texture_name} (4K Resolution)...")
        ms.transfer_attributes_to_texture_per_vertex(
            textname=final_texture_name, textw=4096, texth=4096
        )

        print(f"[*] Exporting final optimized OBJ package to {export_dir}...")
        ms.save_current_mesh(str(final_obj_path))

    except Exception as e:
        print(f"\n[!] A fatal error occurred during mesh processing: {e}")
        sys.exit(1)

    total_time = time.perf_counter() - start_time

    manifest["status"]["phase"] = 5
    if "export" not in manifest["status"]["completed"]:
        manifest["status"]["completed"].append("export")

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    print("\nPROGRESS: 100")
    print(f"[*] Export Phase Complete. Final textured asset ready: {final_obj_path}")
    print(f"[*] Phase 5 Total Time: {total_time:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 5: Export and Texture Bake")
    parser.add_argument(
        "--manifest", type=str, required=True, help="Path to project manifest.json"
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing export data"
    )

    args = parser.parse_args()

    run_export_and_baking(manifest_path=args.manifest, force=args.force)
