"""Production IPC entrypoint for AnitoScan backend."""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure repository root is in sys.path
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(DEFAULT_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_PROJECT_ROOT))

# Redirect sys.stdout to stderr for process-wide diagnostics containment.
_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr

import argparse
import json
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from src.pipeline.core.config import ConfigValidationError, PipelineConfig, RunCancelled
from src.pipeline.core.protocol import (
    CancelPipelineCommand,
    Phase,
    RunPipelineCommand,
    SelectionCommand,
    make_action_required,
    make_backend_ready,
    make_cancelled,
    make_done,
    make_error,
    make_log,
    make_phase_completed,
    make_phase_started,
    make_progress,
    make_workspace_ready,
)

_PROTOCOL_SEND_LOCK = threading.Lock()


def send(message: dict[str, Any]) -> None:
    """Write one protocol event to the original stdout stream."""
    with _PROTOCOL_SEND_LOCK:
        print(
            json.dumps(message, separators=(",", ":")),
            file=_REAL_STDOUT,
            flush=True,
        )


@dataclass
class PendingAction:
    request_id: str
    count: int
    event: threading.Event
    choice: int | str | None = None


class ProductionBackend:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._state_lock = threading.Lock()
        self._active_run_name: str | None = None
        self._cancel_event: threading.Event | None = None
        self._pending_action: PendingAction | None = None
        self._worker: threading.Thread | None = None

    def send_log(self, text: str) -> None:
        send(make_log(text))

    def send_command_error(
        self,
        code: str,
        text: str,
        *,
        run_name: str | None = None,
        request_id: str | None = None,
    ) -> None:
        send(
            make_error(
                "command",
                code,
                text,
                run_name=run_name,
                request_id=request_id,
            )
        )

    def run_command_loop(self) -> None:
        send(make_backend_ready())

        for raw_line in sys.stdin:
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            try:
                command = json.loads(raw_line)
            except json.JSONDecodeError:
                self.send_command_error("invalid_json", "Command is not valid JSON")
                continue

            if not isinstance(command, dict):
                self.send_command_error("invalid_command", "Command must be a JSON object")
                continue

            self._dispatch(command)

        with self._state_lock:
            cancel_event = self._cancel_event
            worker = self._worker
        if cancel_event is not None:
            cancel_event.set()
        if worker is not None:
            worker.join(timeout=5.0)
        self.send_log("Backend exiting")

    def _dispatch(self, command: dict[str, Any]) -> None:
        message_type = command.get("type")
        if not isinstance(message_type, str):
            self.send_command_error("unknown_command", "Command missing required 'type' string field")
            return

        if message_type == "run_pipeline":
            self._accept_run(command)
        elif message_type == "selection":
            self._accept_selection(command)
        elif message_type == "cancel_pipeline":
            self._accept_cancellation(command)
        elif message_type == "ping":
            self.send_log("pong")
        else:
            self.send_command_error(
                "unknown_command",
                f"Unknown command type: {message_type!r}",
            )

    def _accept_run(self, command: dict[str, Any]) -> None:
        try:
            parsed = RunPipelineCommand.from_dict(command)
            input_path = Path(parsed.input)
            if not input_path.is_absolute():
                input_path = self.project_root / input_path

            config = PipelineConfig.from_dict({
                "run_name": parsed.run_name,
                "input_path": input_path,
                "minimum_frames": parsed.minimum_frames,
                "quality": parsed.quality,
            })
            config.validate(check_path_exists=True)
        except (ValueError, ConfigValidationError) as err:
            self.send_command_error("invalid_run_request", str(err))
            return

        workspace = self.project_root / "data" / "runs" / parsed.run_name
        output_directory = self.project_root / "data" / "output" / parsed.run_name

        with self._state_lock:
            if self._active_run_name is not None:
                self.send_command_error(
                    "run_in_progress",
                    f"Run {self._active_run_name!r} is already active",
                    run_name=parsed.run_name,
                )
                return
            if workspace.exists() or output_directory.exists():
                self.send_command_error(
                    "run_already_exists",
                    f"Run {parsed.run_name!r} already has workspace or output artifacts",
                    run_name=parsed.run_name,
                )
                return

            cancel_event = threading.Event()
            self._active_run_name = parsed.run_name
            self._cancel_event = cancel_event

            worker = threading.Thread(
                target=self._run_worker,
                args=(parsed, cancel_event),
                name=f"prod-run-{parsed.run_name}",
                daemon=False,
            )
            self._worker = worker
            worker.start()

    def _accept_selection(self, command: dict[str, Any]) -> None:
        with self._state_lock:
            pending = self._pending_action
            active = self._active_run_name

        if pending is None:
            self.send_command_error(
                "no_pending_action",
                "No interactive action is awaiting a selection",
                run_name=active,
            )
            return

        try:
            parsed = SelectionCommand.from_dict(command)
        except ValueError as err:
            code = "missing_request_id" if "require request_id" in str(err) else "invalid_choice"
            self.send_command_error(
                code,
                str(err),
                run_name=active,
                request_id=pending.request_id,
            )
            return

        if parsed.request_id != pending.request_id:
            self.send_command_error(
                "unknown_request_id",
                "Selection does not match the pending interactive action",
                run_name=active,
                request_id=parsed.request_id,
            )
            return

        choice = parsed.choice
        if isinstance(choice, int) and not 0 <= choice < pending.count:
            self.send_command_error(
                "invalid_choice",
                f"choice must be an index from 0 to {pending.count - 1}, or 'skip'",
                run_name=active,
                request_id=pending.request_id,
            )
            return

        with self._state_lock:
            if self._active_run_name != active or self._pending_action is not pending:
                self.send_command_error(
                    "no_pending_action",
                    "The interactive action is no longer pending",
                    request_id=pending.request_id,
                )
                return
            cancel_event = self._cancel_event
            if cancel_event is None or cancel_event.is_set():
                self.send_command_error(
                    "run_cancelling",
                    "The active run is being cancelled",
                    run_name=active,
                    request_id=pending.request_id,
                )
                return
            if pending.choice is not None:
                self.send_command_error(
                    "action_already_resolved",
                    "The interactive action is no longer pending",
                    request_id=pending.request_id,
                )
                return
            pending.choice = choice
            pending.event.set()

    def _accept_cancellation(self, command: dict[str, Any]) -> None:
        try:
            parsed = CancelPipelineCommand.from_dict(command)
        except ValueError as err:
            self.send_command_error("run_mismatch", str(err))
            return

        with self._state_lock:
            active = self._active_run_name
            cancel_event = self._cancel_event
            if active is None or cancel_event is None:
                self.send_command_error("no_active_run", "No pipeline run is active")
                return
            if parsed.run_name != active:
                self.send_command_error(
                    "run_mismatch",
                    "cancel_pipeline must identify the active run",
                    run_name=parsed.run_name,
                )
                return

            cancel_event.set()

    def _run_worker(
        self, parsed_cmd: RunPipelineCommand, cancel_event: threading.Event
    ) -> None:
        from src.pipeline.core.pipeline import run_pipeline_with_args

        output_path: str | None = None
        failure: Exception | None = None
        workspace_path = self.project_root / "data" / "runs" / parsed_cmd.run_name
        input_path = Path(parsed_cmd.input)
        if not input_path.is_absolute():
            input_path = (self.project_root / input_path).resolve()

        def on_workspace_ready(run_name: str, workspace: str) -> None:
            send(make_workspace_ready(run_name, workspace))

        def on_phase_started(phase: Phase | int, label: str) -> None:
            send(make_phase_started(phase, label))

        def on_progress(
            phase: Phase | int, value: float, label: str | None = None
        ) -> None:
            bounded_value = max(0.0, min(1.0, float(value)))
            overall_value = ((int(phase) - 1) + bounded_value) / 5.0
            send(make_progress(phase, bounded_value, overall_value, label))

        def on_phase_completed(phase: Phase | int) -> None:
            send(make_phase_completed(phase))

        def request_action(preview: str, count: int, frame: str) -> int | str | None:
            if count <= 0:
                return "skip"
            pending = PendingAction(
                request_id=f"{parsed_cmd.run_name}-{uuid.uuid4().hex}",
                count=count,
                event=threading.Event(),
            )
            with self._state_lock:
                if cancel_event.is_set():
                    raise RunCancelled("Pipeline cancelled while requesting an action")
                if self._pending_action is not None:
                    raise RuntimeError("Another interactive action is already pending")
                self._pending_action = pending

            send(
                make_action_required(
                    request_id=pending.request_id,
                    action="mask_selection",
                    phase=Phase.MASKING,
                    frame=frame,
                    preview=preview,
                    count=count,
                )
            )
            try:
                while not pending.event.wait(timeout=0.05):
                    if cancel_event.is_set():
                        raise RunCancelled(
                            "Pipeline cancelled while awaiting an interactive action"
                        )
                if cancel_event.is_set():
                    raise RunCancelled(
                        "Pipeline cancelled while awaiting an interactive action"
                    )
                return pending.choice
            finally:
                with self._state_lock:
                    if self._pending_action is pending:
                        self._pending_action = None

        try:
            res = run_pipeline_with_args(
                args={
                    "run_name": parsed_cmd.run_name,
                    "input": str(input_path),
                    "minimum_frames": parsed_cmd.minimum_frames,
                    "quality": parsed_cmd.quality,
                    **parsed_cmd.extra_fields,
                },
                progress_cb=on_progress,
                log_cb=self.send_log,
                action_cb=request_action,
                is_cancelled=cancel_event.is_set,
                phase_started_cb=on_phase_started,
                phase_completed_cb=on_phase_completed,
                workspace_ready_cb=on_workspace_ready,
                project_root=self.project_root,
            )
            output_path = res["output"]
        except RunCancelled:
            pass
        except Exception as exc:
            failure = exc

        with self._state_lock:
            if cancel_event.is_set():
                terminal = make_cancelled(parsed_cmd.run_name)
            elif failure is not None:
                terminal = make_error(
                    "run",
                    "pipeline_execution_failed",
                    str(failure),
                    run_name=parsed_cmd.run_name,
                )
            else:
                terminal = make_done(
                    parsed_cmd.run_name,
                    str(workspace_path),
                    str(output_path),
                )

            self._pending_action = None
            self._active_run_name = None
            self._cancel_event = None
            self._worker = None
            send(terminal)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AnitoScan production IPC backend")
    parser.add_argument("--ipc", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT, help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ProductionBackend(args.project_root).run_command_loop()


if __name__ == "__main__":
    main()
