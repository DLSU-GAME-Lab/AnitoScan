"""Standard-library dummy backend for editor development and integration tests."""

from __future__ import annotations

import argparse
import binascii
import json
import re
import struct
import sys
import threading
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


PROTOCOL_VERSION = 1
QUALITY_PRESETS = {"fast", "medium", "detailed"}
SAFE_RUN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
WINDOWS_RESERVED_RUN_NAME = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.IGNORECASE
)
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class RunCancelled(Exception):
    """Raised in the run worker when cancellation has been requested."""


@dataclass(frozen=True)
class RunConfig:
    run_name: str
    input_source: str
    minimum_frames: int
    quality: str
    legacy_mode: bool


@dataclass
class PendingAction:
    request_id: str
    count: int
    allow_legacy_response: bool
    event: threading.Event
    choice: int | str | None = None


class DummyBackend:
    def __init__(self, project_root: Path, step_delay: float) -> None:
        self.project_root = project_root.resolve()
        self.step_delay = max(step_delay, 0.0)
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._active_config: RunConfig | None = None
        self._cancel_event: threading.Event | None = None
        self._pending_action: PendingAction | None = None
        self._worker: threading.Thread | None = None
        self._stdout_available = True

    def send(self, message: dict[str, Any]) -> None:
        with self._send_lock:
            if not self._stdout_available:
                return
            try:
                print(json.dumps(message, separators=(",", ":")), flush=True)
            except (BrokenPipeError, OSError):
                self._stdout_available = False

    def send_log(self, text: str) -> None:
        self.send({"type": "log", "text": text})

    def send_command_error(
        self,
        code: str,
        text: str,
        *,
        run_name: str | None = None,
        request_id: str | None = None,
    ) -> None:
        message: dict[str, Any] = {
            "type": "error",
            "scope": "command",
            "code": code,
            "text": text,
        }
        if run_name is not None:
            message["run_name"] = run_name
        if request_id is not None:
            message["request_id"] = request_id
        self.send(message)

    def run_command_loop(self) -> None:
        self.send({"type": "backend_ready", "protocol_version": PROTOCOL_VERSION})

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
            # TODO(protocol-cleanup): remove support for legacy editor action fields.
            message_type = command.get("action")

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
        legacy_mode = command.get("type") != "run_pipeline"
        config, error = self._parse_run_config(command, legacy_mode)
        if config is None:
            self.send_command_error("invalid_run_request", error)
            return

        workspace = self.project_root / "data" / "runs" / config.run_name
        output_directory = self.project_root / "data" / "output" / config.run_name

        with self._state_lock:
            if self._active_config is not None:
                active_name = self._active_config.run_name
                self.send_command_error(
                    "run_in_progress",
                    f"Run {active_name!r} is already active",
                    run_name=config.run_name,
                )
                return
            if workspace.exists() or output_directory.exists():
                self.send_command_error(
                    "run_already_exists",
                    f"Run {config.run_name!r} already has workspace or output artifacts",
                    run_name=config.run_name,
                )
                return

            cancel_event = threading.Event()
            self._active_config = config
            self._cancel_event = cancel_event
            worker = threading.Thread(
                target=self._run_worker,
                args=(config, cancel_event),
                name=f"dummy-run-{config.run_name}",
                daemon=False,
            )
            self._worker = worker
            worker.start()

    def _parse_run_config(
        self, command: dict[str, Any], legacy_mode: bool
    ) -> tuple[RunConfig | None, str]:
        run_name_field = "name" if legacy_mode else "run_name"
        required_fields = (run_name_field, "input", "minimum_frames", "quality")
        missing_fields = [field for field in required_fields if field not in command]
        if missing_fields:
            return None, f"missing required field: {missing_fields[0]}"

        run_name = command.get(run_name_field)
        if not isinstance(run_name, str) or not SAFE_RUN_NAME.fullmatch(run_name):
            return None, "run_name must be a safe, non-empty directory name"
        if run_name.endswith((".", " ")):
            return None, "run_name must not end with a period or space"
        if WINDOWS_RESERVED_RUN_NAME.fullmatch(run_name):
            return None, "run_name must not be a reserved Windows device name"

        input_source = command.get("input")
        if not isinstance(input_source, str) or not input_source.strip():
            return None, "input must be a non-empty string"
        input_path = Path(input_source)
        if not input_path.is_absolute():
            input_path = self.project_root / input_path
        if not input_path.exists():
            return None, "input path does not exist"

        minimum_frames = command.get("minimum_frames")
        if (
            isinstance(minimum_frames, bool)
            or not isinstance(minimum_frames, int)
            or minimum_frames <= 0
        ):
            return None, "minimum_frames must be a positive integer"

        quality = command.get("quality")
        if not isinstance(quality, str) or quality not in QUALITY_PRESETS:
            return None, "quality must be fast, medium, or detailed"

        return (
            RunConfig(
                run_name=run_name,
                input_source=input_source,
                minimum_frames=minimum_frames,
                quality=quality,
                legacy_mode=legacy_mode,
            ),
            "",
        )

    def _accept_selection(self, command: dict[str, Any]) -> None:
        with self._state_lock:
            pending = self._pending_action
            active = self._active_config

        if pending is None:
            self.send_command_error(
                "no_pending_action",
                "No interactive action is awaiting a selection",
                run_name=active.run_name if active is not None else None,
            )
            return

        request_id = command.get("request_id")
        if request_id is None and not pending.allow_legacy_response:
            self.send_command_error(
                "missing_request_id",
                "Target selection commands require request_id",
                run_name=active.run_name if active is not None else None,
                request_id=pending.request_id,
            )
            return
        if request_id is not None and request_id != pending.request_id:
            self.send_command_error(
                "unknown_request_id",
                "Selection does not match the pending interactive action",
                run_name=active.run_name if active is not None else None,
                request_id=str(request_id),
            )
            return

        choice = command.get("choice")
        if isinstance(choice, bool):
            normalized_choice: int | str | None = None
        elif isinstance(choice, int):
            normalized_choice = choice
        elif choice == "skip":
            normalized_choice = "skip"
        elif (
            pending.allow_legacy_response
            and isinstance(choice, str)
            and choice.isdecimal()
        ):
            # TODO(protocol-cleanup): remove numeric string compatibility.
            normalized_choice = int(choice)
        else:
            normalized_choice = None

        if normalized_choice is None or (
            isinstance(normalized_choice, int)
            and not 0 <= normalized_choice < pending.count
        ):
            self.send_command_error(
                "invalid_choice",
                f"choice must be an index from 0 to {pending.count - 1}, or 'skip'",
                run_name=active.run_name if active is not None else None,
                request_id=pending.request_id,
            )
            return

        with self._state_lock:
            if (
                self._active_config is not active
                or self._pending_action is not pending
            ):
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
                    run_name=active.run_name if active is not None else None,
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
            pending.choice = normalized_choice
            pending.event.set()

    def _accept_cancellation(self, command: dict[str, Any]) -> None:
        run_name = command.get("run_name")
        with self._state_lock:
            active = self._active_config
            cancel_event = self._cancel_event
            if active is None or cancel_event is None:
                self.send_command_error("no_active_run", "No pipeline run is active")
                return
            if not isinstance(run_name, str) or run_name != active.run_name:
                self.send_command_error(
                    "run_mismatch",
                    "cancel_pipeline must identify the active run",
                    run_name=str(run_name) if run_name is not None else None,
                )
                return

            cancel_event.set()

    def _run_worker(self, config: RunConfig, cancel_event: threading.Event) -> None:
        workspace = self.project_root / "data" / "runs" / config.run_name
        output_directory = self.project_root / "data" / "output" / config.run_name
        manifest_path = workspace / "manifest.json"

        output_path: Path | None = None
        failure: Exception | None = None
        try:
            output_path = self._execute_run(
                config,
                cancel_event,
                workspace,
                output_directory,
                manifest_path,
            )
        except RunCancelled:
            pass
        except Exception as exception:
            failure = exception

        self._commit_terminal(
            config,
            cancel_event,
            workspace,
            manifest_path,
            output_path,
            failure,
        )

    def _commit_terminal(
        self,
        config: RunConfig,
        cancel_event: threading.Event,
        workspace: Path,
        manifest_path: Path,
        output_path: Path | None,
        failure: Exception | None,
    ) -> None:
        with self._state_lock:
            if cancel_event.is_set():
                manifest_state = "cancelled"
                terminal: dict[str, Any] = {
                    "type": "cancelled",
                    "run_name": config.run_name,
                }
                manifest_error = None
            elif failure is not None:
                manifest_state = "failed"
                terminal = {
                    "type": "error",
                    "scope": "run",
                    "code": "dummy_run_failed",
                    "text": str(failure),
                    "run_name": config.run_name,
                }
                manifest_error = str(failure)
            else:
                assert output_path is not None
                manifest_state = "completed"
                terminal = {
                    "type": "done",
                    "run_name": config.run_name,
                    "workspace": str(workspace),
                    "output": str(output_path),
                }
                # TODO(protocol-cleanup): remove nested data once App consumes flat fields.
                terminal["data"] = {
                    "run_name": config.run_name,
                    "workspace": str(workspace),
                    "output": str(output_path),
                }
                manifest_error = None

            try:
                self._update_terminal_manifest(
                    manifest_path,
                    manifest_state,
                    output=output_path if manifest_state == "completed" else None,
                    error=manifest_error,
                )
            except Exception as exception:
                terminal = {
                    "type": "error",
                    "scope": "run",
                    "code": "dummy_manifest_finalization_failed",
                    "text": f"Unable to finalize dummy manifest: {exception}",
                    "run_name": config.run_name,
                }

            self._pending_action = None
            self._active_config = None
            self._cancel_event = None
            self._worker = None
            self.send(terminal)

    def _execute_run(
        self,
        config: RunConfig,
        cancel_event: threading.Event,
        workspace: Path,
        output_directory: Path,
        manifest_path: Path,
    ) -> Path:
        capture_directory = workspace / "01_capture"
        masking_directory = workspace / "02_masking"
        spatial_directory = workspace / "03_spatial"
        geometry_directory = workspace / "04_geometry"
        for directory in (
            capture_directory,
            masking_directory,
            spatial_directory,
            geometry_directory,
            output_directory,
        ):
            directory.mkdir(parents=True, exist_ok=False)

        manifest: dict[str, Any] = {
            "run_name": config.run_name,
            "input_source": config.input_source,
            "configuration": {
                "minimum_frames": config.minimum_frames,
                "quality": config.quality,
                "backend": "dummy",
            },
            "status": {"state": "running", "phase": 0, "completed": []},
            "paths": {
                "run_root": str(workspace),
                "capture": str(capture_directory),
                "masking": str(masking_directory),
                "spatial": str(spatial_directory),
                "geometry": str(geometry_directory),
                "output": str(output_directory),
            },
            "artifacts": {},
        }
        self._write_json(manifest_path, manifest)

        self.send(
            {
                "type": "workspace_ready",
                "run_name": config.run_name,
                "workspace": str(workspace),
                # TODO(protocol-cleanup): remove the legacy path alias.
                "path": str(workspace),
            }
        )

        self._run_standard_phase(
            cancel_event,
            manifest,
            manifest_path,
            1,
            "Capture",
            lambda: self._create_capture_artifacts(
                capture_directory, config.minimum_frames
            ),
        )
        self._run_masking_phase(
            config,
            cancel_event,
            manifest,
            manifest_path,
            capture_directory,
            masking_directory,
        )
        self._run_standard_phase(
            cancel_event,
            manifest,
            manifest_path,
            3,
            "Spatial",
            lambda: self._create_spatial_artifacts(
                spatial_directory, config.minimum_frames
            ),
        )
        self._run_standard_phase(
            cancel_event,
            manifest,
            manifest_path,
            4,
            "Geometry",
            lambda: self._create_geometry_artifacts(geometry_directory),
        )

        output_path = output_directory / f"{config.run_name}_{config.quality}.obj"
        self._run_standard_phase(
            cancel_event,
            manifest,
            manifest_path,
            5,
            "Export",
            lambda: self._create_export_artifacts(output_path),
        )
        manifest["artifacts"]["primary_output"] = str(output_path)
        self._write_json(manifest_path, manifest)
        return output_path

    def _run_standard_phase(
        self,
        cancel_event: threading.Event,
        manifest: dict[str, Any],
        manifest_path: Path,
        phase: int,
        label: str,
        create_artifacts: Callable[[], dict[str, Any]],
    ) -> None:
        self._start_phase(manifest, manifest_path, phase, label)
        self._send_progress(phase, 0.0, f"Starting {label}")
        for value in (0.25, 0.5):
            self._wait_step(cancel_event)
            self._send_progress(phase, value, f"Simulating {label}")

        self._raise_if_cancelled(cancel_event)
        manifest["artifacts"].update(create_artifacts())
        self._write_json(manifest_path, manifest)

        for value in (0.75, 1.0):
            self._wait_step(cancel_event)
            self._send_progress(phase, value, f"Simulating {label}")
        self._complete_phase(manifest, manifest_path, phase)

    def _run_masking_phase(
        self,
        config: RunConfig,
        cancel_event: threading.Event,
        manifest: dict[str, Any],
        manifest_path: Path,
        capture_directory: Path,
        masking_directory: Path,
    ) -> None:
        phase = 2
        self._start_phase(manifest, manifest_path, phase, "Masking")
        self._send_progress(phase, 0.0, "Starting Masking")
        self._wait_step(cancel_event)
        self._send_progress(phase, 0.25, "Preparing mask candidates")

        artifacts = self._create_masking_artifacts(masking_directory)
        manifest["artifacts"].update(artifacts)
        self._write_json(manifest_path, manifest)
        self._send_progress(phase, 0.5, "Waiting for mask selection")

        request_id = f"{config.run_name}-mask-frame-001"
        pending = PendingAction(
            request_id=request_id,
            count=3,
            allow_legacy_response=config.legacy_mode,
            event=threading.Event(),
        )
        frame_path = capture_directory / "frame_001.png"
        preview_path = masking_directory / "preview_001.png"
        with self._state_lock:
            self._raise_if_cancelled(cancel_event)
            self._pending_action = pending
            self.send(
                {
                    "type": "action_required",
                    "request_id": request_id,
                    "action": "mask_selection",
                    "phase": phase,
                    "frame": frame_path.name,
                    "preview": str(preview_path),
                    "count": pending.count,
                }
            )

        while not pending.event.wait(timeout=0.05):
            self._raise_if_cancelled(cancel_event)
        self._raise_if_cancelled(cancel_event)

        with self._state_lock:
            if self._pending_action is pending:
                self._pending_action = None
        manifest["artifacts"]["mask_selection"] = pending.choice
        self._write_json(manifest_path, manifest)
        if pending.choice == "skip":
            self.send_log("Mask selection skipped")
        else:
            self.send_log(f"Selected mask candidate {pending.choice}")

        for value in (0.75, 1.0):
            self._wait_step(cancel_event)
            self._send_progress(phase, value, "Applying mask selection")
        self._complete_phase(manifest, manifest_path, phase)

    def _start_phase(
        self,
        manifest: dict[str, Any],
        manifest_path: Path,
        phase: int,
        label: str,
    ) -> None:
        manifest["status"]["phase"] = phase
        self._write_json(manifest_path, manifest)
        self.send({"type": "phase_started", "phase": phase, "label": label})

    def _complete_phase(
        self, manifest: dict[str, Any], manifest_path: Path, phase: int
    ) -> None:
        manifest["status"]["completed"].append(phase)
        self._write_json(manifest_path, manifest)
        self.send({"type": "phase_completed", "phase": phase})

    def _send_progress(self, phase: int, value: float, label: str) -> None:
        self.send(
            {
                "type": "progress",
                "phase": phase,
                "value": value,
                "overall_value": ((phase - 1) + value) / 5.0,
                "label": label,
            }
        )

    def _wait_step(self, cancel_event: threading.Event) -> None:
        if cancel_event.wait(timeout=self.step_delay):
            raise RunCancelled

    @staticmethod
    def _raise_if_cancelled(cancel_event: threading.Event) -> None:
        if cancel_event.is_set():
            raise RunCancelled

    def _create_capture_artifacts(
        self, directory: Path, minimum_frames: int
    ) -> dict[str, Any]:
        paths: list[str] = []
        palettes = ((40, 100, 210), (35, 170, 110), (205, 95, 55))
        for index in range(1, minimum_frames + 1):
            base = palettes[(index - 1) % len(palettes)]
            path = directory / f"frame_{index:03d}.png"
            self._write_png(
                path,
                96,
                54,
                lambda x, y, base=base: (
                    min(255, base[0] + x // 2),
                    min(255, base[1] + y),
                    min(255, base[2] + (x + y) // 4),
                ),
            )
            paths.append(str(path))
        return {"capture_images": paths}

    def _create_masking_artifacts(self, directory: Path) -> dict[str, Any]:
        preview_path = directory / "preview_001.png"
        mask_path = directory / "mask_001.png"
        candidate_colors = ((220, 70, 70), (65, 190, 105), (70, 115, 225))
        self._write_png(
            preview_path,
            600,
            240,
            lambda x, y: (
                candidate_colors[min(x // 200, 2)][0],
                min(255, candidate_colors[min(x // 200, 2)][1] + y // 8),
                candidate_colors[min(x // 200, 2)][2],
            ),
        )
        self._write_png(
            mask_path,
            320,
            180,
            lambda x, y: (255, 255, 255)
            if ((x - 160) ** 2) / 110**2 + ((y - 90) ** 2) / 75**2 <= 1
            else (0, 0, 0),
        )
        return {
            "masking_preview": str(preview_path),
            "mask_images": [str(mask_path)],
        }

    def _create_spatial_artifacts(
        self, directory: Path, minimum_frames: int
    ) -> dict[str, Any]:
        path = directory / "camera_poses.json"
        positions = (
            [2.0, 1.0, 2.0],
            [-2.0, 1.0, 2.0],
            [0.0, 1.5, -2.5],
        )
        cameras = [
            {
                "frame": f"frame_{index:03d}.png",
                "position": positions[(index - 1) % len(positions)],
            }
            for index in range(1, minimum_frames + 1)
        ]
        self._write_json(
            path,
            {
                "coordinate_system": "dummy-right-handed",
                "cameras": cameras,
            },
        )
        return {"camera_poses": str(path)}

    def _create_geometry_artifacts(self, directory: Path) -> dict[str, Any]:
        path = directory / "placeholder_geometry.obj"
        self._write_obj(path)
        return {"geometry_model": str(path)}

    def _create_export_artifacts(self, output_path: Path) -> dict[str, Any]:
        self._write_obj(output_path)
        return {"export_model": str(output_path)}

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_name(f".{path.name}.{threading.get_ident()}.tmp")
        with temporary_path.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, indent=2)
            output.write("\n")
        temporary_path.replace(path)

    def _update_terminal_manifest(
        self,
        manifest_path: Path,
        state: str,
        *,
        output: Path | None = None,
        error: str | None = None,
    ) -> None:
        if not manifest_path.exists():
            return
        with manifest_path.open("r", encoding="utf-8") as source:
            manifest = json.load(source)
        manifest["status"]["state"] = state
        if output is not None:
            manifest["artifacts"]["primary_output"] = str(output)
        if error is not None:
            manifest["error"] = error
        self._write_json(manifest_path, manifest)

    @staticmethod
    def _write_png(
        path: Path,
        width: int,
        height: int,
        pixel: Callable[[int, int], tuple[int, int, int]],
    ) -> None:
        def chunk(kind: bytes, payload: bytes) -> bytes:
            checksum = binascii.crc32(kind + payload) & 0xFFFFFFFF
            return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

        rows = bytearray()
        for y in range(height):
            rows.append(0)
            for x in range(width):
                rows.extend(pixel(x, y))
        header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(rows), level=6))
            + chunk(b"IEND", b"")
        )
        path.write_bytes(png)

    @staticmethod
    def _write_obj(path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as output:
            output.write(
                """# AnitoScan dummy placeholder model
o DummyCube
v -1.0 -1.0 -1.0
v  1.0 -1.0 -1.0
v  1.0  1.0 -1.0
v -1.0  1.0 -1.0
v -1.0 -1.0  1.0
v  1.0 -1.0  1.0
v  1.0  1.0  1.0
v -1.0  1.0  1.0
vn  0.0  0.0 -1.0
vn  0.0  0.0  1.0
vn -1.0  0.0  0.0
vn  1.0  0.0  0.0
vn  0.0 -1.0  0.0
vn  0.0  1.0  0.0
f 1//1 3//1 2//1
f 1//1 4//1 3//1
f 5//2 6//2 7//2
f 5//2 7//2 8//2
f 1//3 5//3 8//3
f 1//3 8//3 4//3
f 2//4 3//4 7//4
f 2//4 7//4 6//4
f 1//5 2//5 6//5
f 1//5 6//5 5//5
f 4//6 8//6 7//6
f 4//6 7//6 3//6
"""
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AnitoScan dummy IPC backend")
    parser.add_argument("--ipc", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--step-delay", type=float, default=0.2, help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    DummyBackend(args.project_root, args.step_delay).run_command_loop()


if __name__ == "__main__":
    main()
