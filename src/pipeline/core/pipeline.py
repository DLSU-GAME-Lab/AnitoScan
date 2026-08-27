import os
import subprocess
import sys
import time
from pathlib import Path

from benchmark import (
    BENCHMARK_INVOCATION_ENV,
    append_phase_benchmark,
    create_invocation_id,
)
from config import build_phase_cmd, parse_cli_args
from ipc_handlers import PipelineCancelled, await_ipc_selection, listen_for_ipc_commands
from log import log_done, log_error, log_event, log_info, set_ipc_mode
from manifest import load_manifest
from workspace import init_workspace

# DIRECTORY RESOLUTION
SCRIPT_PATH = Path(__file__).resolve()  # /src/pipeline/core/pipeline.py
PROJECT_ROOT = SCRIPT_PATH.parent.parent.parent.parent
WORKSPACE_DIR = PROJECT_ROOT / "data" / "runs"  # /data/runs/
MODULES_DIR = SCRIPT_PATH.parent.parent / "modules"  # /src/pipeline/modules/


def _append_failed_phase_benchmark(
    phase_num: int,
    manifest_path: Path,
    duration_seconds: float,
    message: str,
    metrics: dict,
) -> None:
    try:
        _, manifest = load_manifest(manifest_path)
        append_phase_benchmark(
            manifest,
            phase_num,
            status="failed",
            skipped=False,
            duration_seconds=duration_seconds,
            metrics=metrics,
            paths={"manifest": manifest_path},
            error=message,
        )
    except (OSError, ValueError, KeyError, TypeError) as benchmark_error:
        log_error(f"Failed to write failure benchmark: {benchmark_error}")


def _check_cancelled(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise PipelineCancelled("Pipeline cancelled")


def _run_phase(
    phase_num: int,
    phase_name: str,
    cmd: list,
    ipc_mode: bool,
    cancel_event=None,
):
    env = os.environ.copy()
    start_time = time.perf_counter()

    if cancel_event is None:
        result = subprocess.run(cmd, check=False, env=env)
        returncode = result.returncode
    else:
        _check_cancelled(cancel_event)
        process = subprocess.Popen(cmd, env=env)
        while process.poll() is None:
            if cancel_event.wait(0.1):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise PipelineCancelled(
                    f"Pipeline cancelled during Phase {phase_num} ({phase_name})"
                )
        returncode = process.returncode

    duration_seconds = time.perf_counter() - start_time
    if returncode != 0:
        msg = f"Pipeline failed at Phase {phase_num} ({phase_name}). Exit code: {returncode}"
        if "--manifest" in cmd:
            manifest_arg_index = cmd.index("--manifest") + 1
            if manifest_arg_index < len(cmd):
                _append_failed_phase_benchmark(
                    phase_num,
                    Path(cmd[manifest_arg_index]),
                    duration_seconds,
                    msg,
                    {"exit_code": returncode},
                )
        if ipc_mode:
            raise RuntimeError(msg)
        log_error(msg)
        sys.exit(returncode)


# PHASE 2: MASKING
def run_phase2(parent_module_path, manifest_path, args, ipc_mode=False, cancel_event=None):
    phase_start = time.perf_counter()
    if ipc_mode:
        try:
            _check_cancelled(cancel_event)
            sys.path.insert(0, str(MODULES_DIR))
            from remove_background import run_remove_background
            phase2_gen = run_remove_background(
                            manifest_path_string=str(manifest_path),
                            yoloe_model_size=args.get("yoloe_model_size", "s"),
                            iou_threshold=args.get("iou_threshold", 0.50),
                            drift_limit=args.get("drift_limit", 200),
                            force=args.get("force", False),
                            ipc_mode=True
                        )

            try:
                request = next(phase2_gen)
                while True:
                    if request.get("type") == "SELECTION_REQUIRED":
                        # Hand control over to the blocking IPC loop
                        choice, wait_time = await_ipc_selection(request)
                        _check_cancelled(cancel_event)
                        # Send answers back and resume computer vision loop
                        request = phase2_gen.send((choice, wait_time))
            except StopIteration:
                pass # Generator successfully finished
            _check_cancelled(cancel_event)
        except PipelineCancelled:
            raise
        except (RuntimeError, ValueError, OSError) as error:
            message = f"Pipeline failed at Phase 2 (Masking): {error}"
            _append_failed_phase_benchmark(
                2,
                Path(manifest_path),
                time.perf_counter() - phase_start,
                message,
                {
                    "force": args.get("force", False),
                    "yoloe_model_size": args.get("yoloe_model_size", "s"),
                    "iou_threshold": args.get("iou_threshold", 0.50),
                    "drift_limit": args.get("drift_limit", 200),
                },
            )
            raise RuntimeError(message) from error
    else:
        cmd = build_phase_cmd(2, parent_module_path, manifest_path, args, ipc_mode)
        _run_phase(2, "Masking", cmd, ipc_mode, cancel_event)


def run_real_phase(
    phase_num: int,
    manifest_path: Path,
    args: dict,
    ipc_mode: bool = False,
    cancel_event=None,
) -> None:
    """Execute one phase using the production pipeline modules."""
    phase_names = {
        1: "Capture",
        2: "Masking",
        3: "Spatial Initialization",
        4: "Geometry Generation",
        5: "Export and Baking",
    }
    if phase_num not in phase_names:
        raise ValueError(f"Unknown pipeline phase: {phase_num}")

    parent_module_path = MODULES_DIR
    log_info(f"Starting Phase {phase_num}: {phase_names[phase_num]}")
    if phase_num == 2:
        run_phase2(parent_module_path, manifest_path, args, ipc_mode, cancel_event)
        return

    cmd = build_phase_cmd(phase_num, parent_module_path, manifest_path, args, ipc_mode)
    _run_phase(phase_num, phase_names[phase_num], cmd, ipc_mode, cancel_event)


def run_pipeline_with_args(
    args: dict,
    ipc_mode: bool = False,
    cancel_event=None,
    phase_executor=None,
    validate_input: bool = True,
):
    set_ipc_mode(ipc_mode)
    os.environ[BENCHMARK_INVOCATION_ENV] = create_invocation_id()

    args = dict(args)
    if ipc_mode:
        capture_mode = args.get("capture_mode", "auto")
        if capture_mode not in {"auto", "image", "video"}:
            raise ValueError(f"Invalid capture_mode: {capture_mode}")
        args["image"] = capture_mode == "image"
        args["video"] = capture_mode == "video"

    _check_cancelled(cancel_event)
    base_dir, manifest_path = init_workspace(
        PROJECT_ROOT,
        WORKSPACE_DIR,
        args,
        validate_input=validate_input,
    )
    name = args.get("name") or "unnamed_run"
    log_event("workspace_ready", {"workspace_path": str(base_dir)})

    execute_phase = phase_executor or run_real_phase

    try:
        for phase_num in range(1, 6):
            _check_cancelled(cancel_event)
            execute_phase(
                phase_num,
                manifest_path,
                args,
                ipc_mode=ipc_mode,
                cancel_event=cancel_event,
            )
        _check_cancelled(cancel_event)

        _, manifest = load_manifest(manifest_path)
        final_obj_path = Path(manifest["paths"]["export"]) / f"{name}_{args.get('quality', 'fast')}.obj"
        if not final_obj_path.is_file():
            raise FileNotFoundError(f"Final OBJ was not created: {final_obj_path}")

        if not ipc_mode:
            log_done(name, str(final_obj_path))
        return final_obj_path
    except PipelineCancelled:
        raise


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--ipc":
        listen_for_ipc_commands(run_pipeline_with_args)
    else:
        args = parse_cli_args()
        run_pipeline_with_args(vars(args), ipc_mode=False)
