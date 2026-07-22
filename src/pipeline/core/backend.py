"""Production IPC entrypoint for AnitoScan backend."""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure repository root is in sys.path
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(DEFAULT_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_PROJECT_ROOT))

# Redirect sys.stdout to stderr for process-wide diagnostics containment.
# Protocol IPC messages will strictly use REAL_STDOUT via ipc.send.
_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr

import argparse
import json
import threading
from dataclasses import dataclass
from typing import Any

from src.pipeline.core.ipc import send
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


class RunCancelled(Exception):
    """Raised when pipeline cancellation is requested."""


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
        except ValueError as err:
            self.send_command_error("invalid_run_request", str(err))
            return

        input_path = Path(parsed.input)
        if not input_path.is_absolute():
            input_path = self.project_root / input_path
        if not input_path.exists():
            self.send_command_error("invalid_run_request", "input path does not exist")
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
        from src.pipeline.core.pipeline import execute_pipeline

        output_path: str | None = None
        failure: Exception | None = None

        def on_workspace_ready(run_name: str, workspace: str) -> None:
            send(make_workspace_ready(run_name, workspace))

        def on_phase_started(phase: Phase, label: str | None) -> None:
            send(make_phase_started(phase, label))

        def on_progress(phase: Phase, val: float, overall: float, label: str | None) -> None:
            send(make_progress(phase, val, overall, label))

        def on_action_required(
            request_id: str, action: str, phase: Phase, frame: str, preview: str, count: int
        ) -> int | str | None:
            pending = PendingAction(
                request_id=request_id,
                count=count,
                event=threading.Event(),
            )
            with self._state_lock:
                if cancel_event.is_set():
                    raise RunCancelled
                self._pending_action = pending
                send(make_action_required(request_id, action, phase, frame, preview, count))

            while not pending.event.wait(timeout=0.05):
                if cancel_event.is_set():
                    raise RunCancelled

            with self._state_lock:
                if self._pending_action is pending:
                    self._pending_action = None
            return pending.choice

        def on_phase_completed(phase: Phase) -> None:
            send(make_phase_completed(phase))

        def on_log(text: str) -> None:
            send(make_log(text))

        try:
            output_path = execute_pipeline(
                config=parsed_cmd,
                project_root=self.project_root,
                cancel_event=cancel_event,
                on_workspace_ready=on_workspace_ready,
                on_phase_started=on_phase_started,
                on_progress=on_progress,
                on_action_required=on_action_required,
                on_phase_completed=on_phase_completed,
                on_log=on_log,
            )
        except RunCancelled:
            pass
        except Exception as exc:
            failure = err = exc

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
                workspace = str(self.project_root / "data" / "runs" / parsed_cmd.run_name)
                terminal = make_done(
                    parsed_cmd.run_name,
                    workspace,
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
