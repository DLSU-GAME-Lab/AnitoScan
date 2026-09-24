import argparse
from collections import deque
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

core_path = str(Path(__file__).resolve().parent.parent / "core")
sys.path.insert(0, core_path)

from benchmark import append_failed_phase_benchmark, append_phase_benchmark
from cancellation import check_cancelled
from log import log_error, log_info, log_progress, set_ipc_mode, set_phase
from manifest import load_manifest, update_manifest

# This module is stdlib-only at import time; CUDA/vendor imports stay in the child.
try:
    from . import evaluate_quality as bm5
except ImportError:
    import evaluate_quality as bm5

# =====================================================================
# DIRECTORY RESOLUTION
# =====================================================================
MODULE_PATH = Path(__file__).resolve()  # /src/pipeline/modules/geometry.py
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent
GS_PATH = PROJECT_ROOT / "vendor" / "2d-gaussian-splatting"  # Vendor Path for 2DGS
TRAIN_END = 0.85  # training ends at 85% and meshing begins for progress logging


def _check_child_cancelled(process: subprocess.Popen, cancel_event) -> None:
    if cancel_event is None or not cancel_event.is_set():
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    check_cancelled(cancel_event)


def _iter_child_output(process: subprocess.Popen, cancel_event):
    """Yield child output while polling cancellation even when the child is quiet."""
    assert process.stdout is not None
    output_queue = queue.Queue()
    finished = object()

    def read_output() -> None:
        buffered = []
        try:
            while True:
                character = process.stdout.read(1)
                if character == "":
                    break
                if character in "\r\n":
                    if buffered:
                        output_queue.put("".join(buffered))
                        buffered.clear()
                else:
                    buffered.append(character)
            if buffered:
                output_queue.put("".join(buffered))
        finally:
            process.stdout.close()
            output_queue.put(finished)

    reader = threading.Thread(target=read_output, name="geometry-output", daemon=True)
    reader.start()

    while True:
        _check_child_cancelled(process, cancel_event)
        try:
            item = output_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        if item is finished:
            break
        yield item

    reader.join()


def _quality_metrics(manifest, metrics):
    summary = bm5.read_json(bm5.report_paths(manifest)["quality_summary"])
    metrics.update({
        "quality_status": summary["status"],
        "quality_train_frames": summary["train_frames"],
        "quality_test_frames": summary["test_frames"],
        "quality_requested_train_frames": summary["requested_train_frames"],
        "quality_requested_test_frames": summary["requested_test_frames"],
        "psnr_db": summary["psnr_db"],
        "ssim": summary["ssim"],
        "quality_train_iterations": summary["train_iterations"],
        "split_fingerprint": summary["split_fingerprint"],
    })
    return summary


def _run_quality_child(manifest_path, manifest, model_dir, config, metrics, cancel_event, *, preflight=False, iteration=None):
    command = [sys.executable, str(MODULE_PATH.with_name("evaluate_quality.py")),
               "--manifest", str(manifest_path), "--model-dir", str(model_dir)]
    if preflight:
        command.extend([
            "--preflight", "--train-iterations", str(config["train_iterations"]),
            "--densify-until-iter", str(config["densify_until_iter"]),
            "--opacity-reset-interval", str(config["opacity_reset_interval"]),
        ])
    elif iteration is not None:
        command.extend(["--iteration", str(iteration)])
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    # Clear stale scores even if the interpreter fails before importing the evaluator.
    pending = bm5.new_summary(manifest)
    pending["details"]["stage"] = "preflight" if preflight else "evaluation"
    bm5.save_report(manifest, pending, [])
    output = deque(maxlen=20)
    try:
        check_cancelled(cancel_event)
        process = subprocess.Popen(
            command, cwd=str(PROJECT_ROOT), env=environment, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
        )
        for line in _iter_child_output(process, cancel_event):
            stripped = line.strip()
            if stripped:
                output.append(stripped)
                log_info(f"[BM-5] {stripped}")
            match = re.search(r"BM5_PROGRESS (\d+)/(\d+)", line)
            if match:
                current, total = map(int, match.groups())
                log_progress(TRAIN_END + 0.05 * current / max(total, 1),
                             f"Phase 4: BM-5 held-out frames {current}/{total}")
        process.wait()
        _check_child_cancelled(process, cancel_event)
        summary = _quality_metrics(manifest, metrics)
        if process.returncode != 0:
            detail = "; ".join(summary["errors"]) or (output[-1] if output else "No child-process output")
            raise RuntimeError(f"Phase 4 BM-5 failed (exit {process.returncode}): {detail}. "
                               f"Report: {bm5.report_paths(manifest)['quality_summary']}")
        if not preflight and summary["status"] != "completed":
            raise RuntimeError("Phase 4 BM-5 did not evaluate every requested test frame; see evaluation/summary.json")
        return summary
    except Exception as error:
        try:
            summary = bm5.read_json(bm5.report_paths(manifest)["quality_summary"])
        except (OSError, ValueError, TypeError):
            summary = {}
        if not summary.get("errors"):
            bm5.write_failure_report(manifest, error)
        _quality_metrics(manifest, metrics)
        raise


def run_surface_reconstruction(
    manifest_path_string,
    train_iterations,
    densify_until_iter,
    opacity_reset_interval,
    force=False,
    ipc_mode=False,
    cancel_event=None,
):
    set_ipc_mode(ipc_mode)
    set_phase(4)
    check_cancelled(cancel_event)

    manifest_path, manifest = load_manifest(manifest_path_string)
    phase_start = time.perf_counter()

    output_dir = Path(manifest["paths"]["geometry"])
    output_dir.mkdir(parents=True, exist_ok=True)

    input_data_path = Path(manifest["paths"]["spatial"])
    sparse_dir = input_data_path / "sparse" / "0"
    gs_model_dir = output_dir / "vanilla_2dgs"
    benchmark_settings = {
        "force": force,
        "train_iterations": train_iterations,
        "densify_until_iter": densify_until_iter,
        "opacity_reset_interval": opacity_reset_interval,
    }
    benchmark_metrics = {
        "training_skipped": False,
        "meshing_skipped": False,
        "train_checkpoint_exists": False,
        "training_iteration": 0,
        "candidate_meshes": 0,
        "fused_mesh_bytes": 0,
    }
    benchmark_paths = {
        "input_data_path": input_data_path,
        "sparse_dir": sparse_dir,
        "gs_model_dir": gs_model_dir,
    }
    training_config = {
        "train_iterations": train_iterations,
        "densify_until_iter": densify_until_iter,
        "opacity_reset_interval": opacity_reset_interval,
    }
    evaluate_quality = manifest.get("settings", {}).get("evaluate_quality", False)
    plan = None
    training_marker = None
    try:
        options = bm5.quality_settings(manifest)
        evaluate_quality = options["evaluate_quality"]
        benchmark_settings.update(options)
        if not evaluate_quality:
            if (input_data_path / "evaluation_identity.json").exists():
                raise ValueError("BM-5 spatial data cannot be used for normal training. Rerun Phase 3 with evaluation disabled and --force first.")
            if (gs_model_dir / bm5.MARKER_NAME).exists() and not force:
                raise ValueError("BM-5 checkpoint cannot be reused with evaluation disabled. Rerun Phase 4 with --force.")
        if evaluate_quality:
            benchmark_settings.update(benchmark="BM-5", vendor_eval_split=False, white_background=True)
            benchmark_paths.update(bm5.report_paths(manifest))
            benchmark_paths["quality_training_marker"] = gs_model_dir / bm5.MARKER_NAME
    except (ValueError, TypeError) as error:
        if evaluate_quality:
            bm5.write_failure_report(manifest, error)
        append_failed_phase_benchmark(
            manifest, 4, start_time=phase_start, settings=benchmark_settings,
            metrics=benchmark_metrics, paths=benchmark_paths, error=error,
        )
        raise

    if not (sparse_dir / "points3D.txt").exists():
        error = FileNotFoundError(f"Spatial initialization missing in {input_data_path}. Run Phase 3 first.")
        if evaluate_quality:
            bm5.write_failure_report(manifest, error)
            _quality_metrics(manifest, benchmark_metrics)
        append_failed_phase_benchmark(
            manifest,
            4,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        raise error

    check_cancelled(cancel_event)
    if evaluate_quality:
        try:
            log_progress(0, "Phase 4: BM-5 dependency/API preflight...")
            _run_quality_child(manifest_path, manifest, gs_model_dir, training_config,
                               benchmark_metrics, cancel_event, preflight=True)
            plan = bm5.read_json(bm5.report_paths(manifest)["quality_training_plan"])
            benchmark_settings["training_fingerprint"] = plan["fingerprint"]
            benchmark_settings["split_fingerprint"] = plan["split_fingerprint"]
            benchmark_settings["vendor_source_sha256"] = plan["vendor"]["source_sha256"]
            benchmark_settings["vendor_revision"] = plan["vendor"]["revision"]
            benchmark_settings["effective_training_config"] = plan["training_config"]
            if not force:
                training_marker = bm5.validate_training_cache(gs_model_dir, plan)
        except Exception as error:
            try:
                reported = bm5.read_json(bm5.report_paths(manifest)["quality_summary"])
            except (OSError, ValueError, TypeError):
                reported = {}
            if not reported.get("errors"):
                bm5.write_failure_report(manifest, error, plan)
            _quality_metrics(manifest, benchmark_metrics)
            append_failed_phase_benchmark(
                manifest, 4, start_time=phase_start, settings=benchmark_settings,
                metrics=benchmark_metrics, paths=benchmark_paths, error=error,
            )
            raise
    if force and gs_model_dir.exists():
        shutil.rmtree(gs_model_dir)
    gs_model_dir.mkdir(parents=True, exist_ok=True)

    train_cmd = [
        sys.executable,
        str(GS_PATH / "train.py"),
        "-s",
        str(input_data_path),
        "-m",
        str(gs_model_dir),
        "--iterations",
        str(train_iterations),
        "--densify_from_iter",
        "500",  # default is 500
        "--densify_until_iter",
        str(densify_until_iter),
        "--opacity_reset_interval",
        str(opacity_reset_interval),
        "--white_background",
        "--lambda_dist",
        "0.0",  # default is 0.0
        "--lambda_normal",
        "0.05",  # default is 0.05
        "--quiet",
    ]

    if evaluate_quality:
        # The upstream split is authoritative. Never pass --eval to the vendor;
        # disable its scheduled evaluation and explicitly save the final iteration.
        train_cmd = [sys.executable, str(GS_PATH / "train.py"), "-s", str(input_data_path),
                     "-m", str(gs_model_dir), *bm5.training_flags(training_config),
                     "--test_iterations", "-1", "--save_iterations", str(train_iterations), "--quiet"]

    render_cmd = [
        sys.executable,
        str(GS_PATH / "render.py"),
        "-s",
        str(input_data_path),
        "-m",
        str(gs_model_dir),
        "--skip_test",
        "--skip_train",  # Only interested in the mesh
        "--iteration",
        str(train_iterations),
    ]

    log_info(f"Starting 2DGS Training ({train_iterations} iterations)...")
    log_progress(0, "Phase 4: Training 2DGS...")
    start_time = phase_start if evaluate_quality else time.perf_counter()

    train_checkpoint_exists = (
        gs_model_dir / "point_cloud" / f"iteration_{train_iterations}"
    ).exists()
    if evaluate_quality:
        train_checkpoint_exists = training_marker is not None
    benchmark_metrics["train_checkpoint_exists"] = train_checkpoint_exists

    training_skipped = False
    if train_checkpoint_exists and not force:
        training_skipped = True
        benchmark_metrics["training_skipped"] = training_skipped
        benchmark_metrics["training_iteration"] = training_marker["final_iteration"] if training_marker else train_iterations
        log_info("Found validated BM-5 training output. Skipping training, not evaluation..." if evaluate_quality
                 else "Found existing training output. Skipping training...")
    else:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        try:
            check_cancelled(cancel_event)
            if evaluate_quality:
                bm5.mark_training_started(gs_model_dir, plan)
            process = subprocess.Popen(
                train_cmd,
                cwd=str(GS_PATH),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except (OSError, ValueError) as error:
            if evaluate_quality:
                bm5.write_failure_report(manifest, error, plan)
                _quality_metrics(manifest, benchmark_metrics)
            append_failed_phase_benchmark(
                manifest,
                4,
                start_time=phase_start,
                settings=benchmark_settings,
                metrics=benchmark_metrics,
                paths=benchmark_paths,
                error=error,
            )
            raise
        log_info(f"2DGS training process started (PID {process.pid})")
        training_output = deque(maxlen=20)
        for line in _iter_child_output(process, cancel_event):
            line = line.rstrip()
            if line:
                training_output.append(line)
            match = re.search(r'(\d+)\s*/\s*(\d+)', line)
            if match:
                current = int(match.group(1))
                total = int(match.group(2))
                benchmark_metrics["training_iteration"] = current
                progress = (current / total) * TRAIN_END
                log_progress(progress, f"Training {current}/{total} iterations")
            else:
                stripped = line.strip()
                if stripped and not stripped.startswith("("):
                    log_info(f"\r[train] {stripped}")

        process.wait()
        _check_child_cancelled(process, cancel_event)
        if process.returncode != 0:
            last_output = training_output[-1] if training_output else "No child-process output"
            error = RuntimeError(
                f"Phase 4: Training failed with exit code {process.returncode}. "
                f"Last output: {last_output}"
            )
            benchmark_metrics["training_return_code"] = process.returncode
            if evaluate_quality:
                bm5.write_failure_report(manifest, error, plan)
                _quality_metrics(manifest, benchmark_metrics)
            append_failed_phase_benchmark(
                manifest,
                4,
                start_time=phase_start,
                settings=benchmark_settings,
                metrics=benchmark_metrics,
                paths=benchmark_paths,
                error=error,
            )
            raise error

    actual_iteration = train_iterations
    if evaluate_quality:
        try:
            if not training_skipped:
                training_marker = bm5.finish_training(gs_model_dir, plan)
            actual_iteration = training_marker["final_iteration"]
            benchmark_metrics["training_iteration"] = actual_iteration
            benchmark_paths["quality_checkpoint"] = gs_model_dir / "point_cloud" / f"iteration_{actual_iteration}" / "point_cloud.ply"
        except (RuntimeError, ValueError, OSError, KeyError) as error:
            bm5.write_failure_report(manifest, error, plan)
            _quality_metrics(manifest, benchmark_metrics)
            append_failed_phase_benchmark(
                manifest, 4, start_time=phase_start, settings=benchmark_settings,
                metrics=benchmark_metrics, paths=benchmark_paths, error=error,
            )
            raise
        try:
            log_progress(TRAIN_END, "Phase 4: Evaluating held-out BM-5 frames...")
            _run_quality_child(manifest_path, manifest, gs_model_dir, training_config,
                               benchmark_metrics, cancel_event, iteration=actual_iteration)
        except Exception as error:
            append_failed_phase_benchmark(
                manifest, 4, start_time=phase_start, settings=benchmark_settings,
                metrics=benchmark_metrics, paths=benchmark_paths, error=error,
            )
            raise
        render_cmd[-1] = str(actual_iteration)

    # 6. Rendering / TSDF Fusion
    log_info("Starting Mesh Extraction (TSDF Fusion)...")
    log_progress(TRAIN_END + (0.05 if evaluate_quality else 0), "Phase 4: Extracting mesh...")
    mesh_output_dir = gs_model_dir / "train" / f"ours_{actual_iteration}"
    benchmark_paths["mesh_output_dir"] = mesh_output_dir

    meshing_skipped = False
    if mesh_output_dir.exists() and not force:
        meshing_skipped = True
        benchmark_metrics["meshing_skipped"] = meshing_skipped
        log_info("Found existing mesh output. Skipping meshing...")
    else:
        try:
            check_cancelled(cancel_event)
            process = subprocess.Popen(
                render_cmd,
                cwd=str(GS_PATH),
                env=os.environ.copy(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except (OSError, ValueError) as error:
            append_failed_phase_benchmark(
                manifest,
                4,
                start_time=phase_start,
                settings=benchmark_settings,
                metrics=benchmark_metrics,
                paths=benchmark_paths,
                error=error,
            )
            raise
        log_info(f"2DGS render process started (PID {process.pid})")
        render_output = deque(maxlen=20)
        for line in _iter_child_output(process, cancel_event):
            stripped = line.rstrip()
            if stripped:
                render_output.append(stripped)
                log_info(f"[render] {stripped}")
        process.wait()
        _check_child_cancelled(process, cancel_event)
        if process.returncode != 0:
            last_output = render_output[-1] if render_output else "No child-process output"
            error = RuntimeError(
                f"Phase 4: Meshing failed with exit code {process.returncode}. "
                f"Last output: {last_output}"
            )
            benchmark_metrics["meshing_return_code"] = process.returncode
            append_failed_phase_benchmark(
                manifest,
                4,
                start_time=phase_start,
                settings=benchmark_settings,
                metrics=benchmark_metrics,
                paths=benchmark_paths,
                error=error,
            )
            raise error

    # 7. Final Stage: Expose PLY to the workspace root for Phase 5
    target_fused_ply = output_dir / "fused_mesh.ply"

    if not mesh_output_dir.exists():
        error = FileNotFoundError(f"Mesh directory {mesh_output_dir} not found.")
        append_failed_phase_benchmark(
            manifest,
            4,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        raise error

    check_cancelled(cancel_event)
    possible_meshes = list(mesh_output_dir.rglob("*_post.ply"))
    benchmark_metrics["candidate_meshes"] = len(possible_meshes)
    if not possible_meshes:
        error = FileNotFoundError(f"No *_post.ply files found in {mesh_output_dir}.")
        append_failed_phase_benchmark(
            manifest,
            4,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        raise error

    best_mesh = possible_meshes[0]
    benchmark_paths["source_mesh"] = best_mesh
    try:
        check_cancelled(cancel_event)
        shutil.copy2(str(best_mesh), str(target_fused_ply))
        check_cancelled(cancel_event)
    except OSError as error:
        append_failed_phase_benchmark(
            manifest,
            4,
            start_time=phase_start,
            settings=benchmark_settings,
            metrics=benchmark_metrics,
            paths=benchmark_paths,
            error=error,
        )
        raise
    benchmark_paths["fused_mesh"] = target_fused_ply
    benchmark_metrics["fused_mesh_bytes"] = target_fused_ply.stat().st_size if target_fused_ply.exists() else 0
    log_info(f"Base geometry staged for Phase 5 at: {target_fused_ply}")

    check_cancelled(cancel_event)
    update_manifest(manifest_path, manifest, phase=4)

    total_time = time.perf_counter() - start_time
    append_phase_benchmark(
        manifest,
        4,
        status="completed",
        skipped=training_skipped and meshing_skipped and not evaluate_quality,
        duration_seconds=total_time,
        settings=benchmark_settings,
        metrics={
            **benchmark_metrics,
            "training_skipped": training_skipped,
            "meshing_skipped": meshing_skipped,
            "train_checkpoint_exists": train_checkpoint_exists,
            "candidate_meshes": len(possible_meshes),
            "fused_mesh_bytes": target_fused_ply.stat().st_size if target_fused_ply.exists() else 0,
        },
        paths=benchmark_paths,
    )

    log_info(f"2DGS Reconstruction Complete. Saved to: {output_dir}")
    log_info(f"Total Time: {total_time:.2f}s")
    log_progress(1.0, "Phase 4: Geometry complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True, help="Path to project manifest.json")
    parser.add_argument("--force", action="store_true", help="Overwrite existing geometry data")
    parser.add_argument("--train_iterations", type=int, default=15000)
    parser.add_argument("--densify_until_iter", type=int, default=7500)
    parser.add_argument("--opacity_reset_interval", type=int, default=3000)
    parser.add_argument("--ipc", action="store_true")

    args = parser.parse_args()

    try:
        run_surface_reconstruction(
            args.manifest,
            train_iterations=args.train_iterations,
            densify_until_iter=args.densify_until_iter,
            opacity_reset_interval=args.opacity_reset_interval,
            force=args.force,
            ipc_mode=args.ipc
        )
    except (RuntimeError, ValueError, OSError) as error:
        log_error(str(error))
        sys.exit(1)
