"""End-to-end protocol and artifact tests for the standard-library dummy backend."""

from __future__ import annotations

import binascii
import importlib.util
import json
import queue
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
import zlib
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DUMMY_BACKEND = PROJECT_ROOT / "src" / "pipeline" / "core" / "dummy.py"
TERMINAL_TYPES = {"done", "cancelled"}
LIFECYCLE_TYPES = {
    "workspace_ready",
    "phase_started",
    "progress",
    "action_required",
    "phase_completed",
    "done",
    "cancelled",
}
_EOF = object()


def load_dummy_module() -> Any:
    module_name = f"anitoscan_dummy_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, DUMMY_BACKEND)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load dummy backend from {DUMMY_BACKEND}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class BackendProcess:
    def __init__(self, project_root: Path) -> None:
        self.messages: queue.Queue[object] = queue.Queue()
        self.history: list[dict[str, Any]] = []
        self.stderr_lines: list[str] = []
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                str(DUMMY_BACKEND),
                "--ipc",
                "--project-root",
                str(project_root),
                "--step-delay",
                "0.01",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        assert self.process.stdout is not None
        assert self.process.stderr is not None
        self.stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self.stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self.stdout_thread.start()
        self.stderr_thread.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exception:
                self.messages.put(
                    AssertionError(f"Backend stdout was not JSON: {line!r}: {exception}")
                )
                continue
            if not isinstance(message, dict):
                self.messages.put(
                    AssertionError(f"Backend stdout was not a JSON object: {line!r}")
                )
                continue
            self.messages.put(message)
        self.messages.put(_EOF)

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        for line in self.process.stderr:
            self.stderr_lines.append(line.rstrip())

    def send(self, message: dict[str, Any]) -> None:
        self.send_raw(json.dumps(message))

    def send_raw(self, line: str) -> None:
        if self.process.stdin is None:
            raise AssertionError("Backend stdin is unavailable")
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def receive(self, timeout: float = 5.0) -> dict[str, Any]:
        try:
            item = self.messages.get(timeout=timeout)
        except queue.Empty as exception:
            raise AssertionError(
                "Timed out waiting for backend output; "
                f"exit={self.process.poll()}, stderr={self.stderr_lines}"
            ) from exception
        if item is _EOF:
            raise AssertionError(
                "Backend stdout closed unexpectedly; "
                f"exit={self.process.poll()}, stderr={self.stderr_lines}"
            )
        if isinstance(item, BaseException):
            raise item
        assert isinstance(item, dict)
        self.history.append(item)
        return item

    def receive_optional(self, timeout: float) -> dict[str, Any] | None:
        try:
            item = self.messages.get(timeout=timeout)
        except queue.Empty:
            return None
        if item is _EOF:
            return None
        if isinstance(item, BaseException):
            raise item
        assert isinstance(item, dict)
        self.history.append(item)
        return item

    def wait_for(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.receive(max(0.01, deadline - time.monotonic()))
            if predicate(message):
                return message
        raise AssertionError("Timed out waiting for matching backend message")

    def wait_for_type(self, message_type: str, timeout: float = 5.0) -> dict[str, Any]:
        return self.wait_for(lambda message: message.get("type") == message_type, timeout)

    def close(self) -> None:
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5.0)
        self.stdout_thread.join(timeout=1.0)
        self.stderr_thread.join(timeout=1.0)
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.process.stderr is not None:
            self.process.stderr.close()


def is_terminal(message: dict[str, Any]) -> bool:
    if message.get("type") in TERMINAL_TYPES:
        return True
    return message.get("type") == "error" and message.get("scope") in {
        "run",
        "backend",
    }


def validate_png(test: unittest.TestCase, path: Path) -> None:
    data = path.read_bytes()
    test.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"), path)
    position = 8
    width = height = None
    compressed = bytearray()
    saw_end = False

    while position < len(data):
        test.assertGreaterEqual(len(data) - position, 12, path)
        length = struct.unpack(">I", data[position : position + 4])[0]
        kind = data[position + 4 : position + 8]
        payload_start = position + 8
        payload_end = payload_start + length
        payload = data[payload_start:payload_end]
        checksum = struct.unpack(">I", data[payload_end : payload_end + 4])[0]
        test.assertEqual(checksum, binascii.crc32(kind + payload) & 0xFFFFFFFF)
        position = payload_end + 4

        if kind == b"IHDR":
            width, height, bit_depth, color_type, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", payload)
            )
            test.assertEqual(bit_depth, 8)
            test.assertEqual(color_type, 2)
            test.assertEqual((compression, filtering, interlace), (0, 0, 0))
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            saw_end = True
            break

    test.assertTrue(saw_end, path)
    test.assertIsNotNone(width)
    test.assertIsNotNone(height)
    assert width is not None and height is not None
    test.assertGreater(width, 0)
    test.assertGreater(height, 0)
    raw = zlib.decompress(bytes(compressed))
    stride = 1 + width * 3
    test.assertEqual(len(raw), height * stride)
    test.assertTrue(all(raw[row * stride] == 0 for row in range(height)))


def validate_obj(test: unittest.TestCase, path: Path) -> None:
    vertices = []
    faces: list[list[int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            components = line.split()
            test.assertEqual(len(components), 4)
            vertices.append(tuple(float(value) for value in components[1:]))
        elif line.startswith("f "):
            indices = [int(token.split("/", 1)[0]) for token in line.split()[1:]]
            faces.append(indices)

    test.assertGreaterEqual(len(vertices), 4)
    test.assertGreaterEqual(len(faces), 4)
    for face in faces:
        test.assertEqual(len(face), 3)
        test.assertTrue(all(1 <= index <= len(vertices) for index in face))


class DummyBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="anitoscan-dummy-test-"
        )
        self.test_root = Path(self.temporary_directory.name)
        self.relative_input = Path("data/input/example.mp4")
        self.absolute_input = self.test_root / "absolute-input.mp4"
        (self.test_root / self.relative_input).parent.mkdir(parents=True)
        (self.test_root / self.relative_input).write_bytes(b"dummy input")
        self.absolute_input.write_bytes(b"dummy absolute input")
        self.backend = BackendProcess(self.test_root)
        ready = self.backend.wait_for_type("backend_ready")
        self.assertEqual(ready.get("protocol_version"), 1)
        self.run_names: list[str] = []

    def tearDown(self) -> None:
        self.backend.close()
        self.assertEqual(
            self.backend.process.returncode,
            0,
            f"stderr: {self.backend.stderr_lines}",
        )
        self.temporary_directory.cleanup()

    def new_run_name(self, suffix: str) -> str:
        run_name = f"dummy-{suffix}-{uuid.uuid4().hex[:8]}"
        self.run_names.append(run_name)
        return run_name

    def run_to_terminal(
        self,
        command: dict[str, Any],
        action_handler: Callable[[dict[str, Any]], None],
    ) -> list[dict[str, Any]]:
        start = len(self.backend.history)
        self.backend.send(command)
        return self.collect_to_terminal(start, action_handler)

    def collect_to_terminal(
        self,
        start: int,
        action_handler: Callable[[dict[str, Any]], None],
    ) -> list[dict[str, Any]]:
        while True:
            message = self.backend.receive()
            if message.get("type") == "action_required":
                action_handler(message)
            if is_terminal(message):
                events = self.backend.history[start:]
                self.assertEqual(sum(is_terminal(event) for event in events), 1)
                return events

    def assert_successful_lifecycle(
        self, events: list[dict[str, Any]], run_name: str
    ) -> dict[str, Any]:
        terminals = [event for event in events if is_terminal(event)]
        self.assertEqual(len(terminals), 1)
        done = terminals[0]
        self.assertEqual(done.get("type"), "done", done)

        lifecycle = [event for event in events if event.get("type") in LIFECYCLE_TYPES]
        expected: list[tuple[str, int | float | None]] = [
            ("workspace_ready", None)
        ]
        for phase in range(1, 6):
            expected.append(("phase_started", phase))
            expected.extend(("progress", value) for value in (0.0, 0.25, 0.5))
            if phase == 2:
                expected.append(("action_required", phase))
            expected.extend(("progress", value) for value in (0.75, 1.0))
            expected.append(("phase_completed", phase))
        expected.append(("done", None))
        actual = [
            (
                event["type"],
                event.get("value")
                if event.get("type") == "progress"
                else event.get("phase"),
            )
            for event in lifecycle
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(lifecycle[0].get("run_name"), run_name)
        self.assertEqual(lifecycle[-1].get("type"), "done")
        terminal_index = events.index(lifecycle[-1])
        self.assertFalse(
            any(
                event.get("type") in LIFECYCLE_TYPES
                for event in events[terminal_index + 1 :]
            )
        )

        progress = [event for event in events if event.get("type") == "progress"]
        self.assertTrue(progress)
        overall_values = [event["overall_value"] for event in progress]
        self.assertEqual(overall_values, sorted(overall_values))
        for phase in range(1, 6):
            values = [
                event["value"] for event in progress if event.get("phase") == phase
            ]
            self.assertTrue(values, phase)
            self.assertEqual(values, sorted(values))
            self.assertEqual(values[0], 0.0)
            self.assertEqual(values[-1], 1.0)
            self.assertTrue(all(0.0 <= value <= 1.0 for value in values))
        self.assertTrue(all(0.0 <= value <= 1.0 for value in overall_values))

        self.assertEqual(done.get("run_name"), run_name)
        self.assertEqual(done.get("data", {}).get("run_name"), run_name)
        return done

    def assert_artifacts(
        self,
        run_name: str,
        quality: str,
        expected_choice: int | str,
        minimum_frames: int,
    ) -> None:
        workspace = self.test_root / "data" / "runs" / run_name
        output_directory = self.test_root / "data" / "output" / run_name
        self.assertTrue(workspace.is_dir())
        for directory in (
            "01_capture",
            "02_masking",
            "03_spatial",
            "04_geometry",
        ):
            self.assertTrue((workspace / directory).is_dir(), directory)

        capture_images = sorted((workspace / "01_capture").glob("*.png"))
        masking_images = sorted((workspace / "02_masking").glob("*.png"))
        self.assertEqual(len(capture_images), minimum_frames)
        self.assertGreaterEqual(len(masking_images), 2)
        for image in capture_images + masking_images:
            validate_png(self, image)

        manifest_path = workspace / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["run_name"], run_name)
        self.assertEqual(manifest["configuration"]["backend"], "dummy")
        self.assertEqual(manifest["configuration"]["quality"], quality)
        self.assertEqual(manifest["configuration"]["minimum_frames"], minimum_frames)
        self.assertEqual(len(manifest["artifacts"]["capture_images"]), minimum_frames)
        self.assertEqual(manifest["status"]["state"], "completed")
        self.assertEqual(manifest["status"]["completed"], [1, 2, 3, 4, 5])
        self.assertEqual(manifest["artifacts"]["mask_selection"], expected_choice)

        camera_poses = json.loads(
            (workspace / "03_spatial" / "camera_poses.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            [camera["frame"] for camera in camera_poses["cameras"]],
            [image.name for image in capture_images],
        )

        output_path = output_directory / f"{run_name}_{quality}.obj"
        self.assertEqual(manifest["artifacts"]["primary_output"], str(output_path))
        validate_obj(self, output_path)
        validate_obj(self, workspace / "04_geometry" / "placeholder_geometry.obj")

    def test_protocol_lifecycle_artifacts_errors_and_cancellation(self) -> None:
        self.backend.send_raw("{")
        invalid_json = self.backend.wait_for_type("error")
        self.assertEqual(invalid_json.get("scope"), "command")
        self.assertEqual(invalid_json.get("code"), "invalid_json")

        self.backend.send({"type": "not_a_command"})
        unknown = self.backend.wait_for_type("error")
        self.assertEqual(unknown.get("code"), "unknown_command")

        self.backend.send(
            {
                "type": "run_pipeline",
                "run_name": "../unsafe",
                "input": str(self.relative_input),
                "minimum_frames": 3,
                "quality": "fast",
            }
        )
        invalid_run = self.backend.wait_for_type("error")
        self.assertEqual(invalid_run.get("code"), "invalid_run_request")

        for reserved_name in ("CON", "prn.txt", "COM1.log", "Lpt9"):
            self.backend.send(
                {
                    "type": "run_pipeline",
                    "run_name": reserved_name,
                    "input": str(self.relative_input),
                    "minimum_frames": 3,
                    "quality": "fast",
                }
            )
            reserved = self.backend.wait_for_type("error")
            self.assertEqual(reserved.get("code"), "invalid_run_request")

        complete_request = {
            "type": "run_pipeline",
            "run_name": self.new_run_name("missing-field"),
            "input": str(self.relative_input),
            "minimum_frames": 3,
            "quality": "fast",
        }
        for field in ("run_name", "input", "minimum_frames", "quality"):
            request = dict(complete_request)
            del request[field]
            self.backend.send(request)
            missing = self.backend.wait_for_type("error")
            self.assertEqual(missing.get("code"), "invalid_run_request")
            self.assertIn(field, missing.get("text", ""))

        missing_input_request = dict(complete_request)
        missing_input_request["run_name"] = self.new_run_name("missing-input")
        missing_input_request["input"] = "does/not/exist.mp4"
        self.backend.send(missing_input_request)
        missing_input = self.backend.wait_for_type("error")
        self.assertEqual(missing_input.get("code"), "invalid_run_request")

        target_name = self.new_run_name("target")

        def target_selection(action: dict[str, Any]) -> None:
            preview = Path(action["preview"])
            self.assertTrue(preview.is_file())
            validate_png(self, preview)
            self.assertEqual(action.get("phase"), 2)
            self.assertEqual(action.get("action"), "mask_selection")
            self.assertEqual(action.get("count"), 3)
            request_id = action["request_id"]

            self.backend.send({"type": "selection", "choice": 1})
            missing_id = self.backend.wait_for_type("error")
            self.assertEqual(missing_id.get("code"), "missing_request_id")

            self.backend.send(
                {"type": "selection", "request_id": "wrong-request", "choice": 1}
            )
            wrong_id = self.backend.wait_for_type("error")
            self.assertEqual(wrong_id.get("code"), "unknown_request_id")

            competing_name = self.new_run_name("competing")
            self.backend.send(
                {
                    "type": "run_pipeline",
                    "run_name": competing_name,
                    "input": str(self.relative_input),
                    "minimum_frames": 3,
                    "quality": "fast",
                }
            )
            in_progress = self.backend.wait_for_type("error")
            self.assertEqual(in_progress.get("code"), "run_in_progress")

            self.backend.send(
                {"type": "selection", "request_id": request_id, "choice": 9}
            )
            invalid_choice = self.backend.wait_for_type("error")
            self.assertEqual(invalid_choice.get("code"), "invalid_choice")

            self.backend.send(
                {"type": "selection", "request_id": request_id, "choice": 1}
            )

        target_events = self.run_to_terminal(
            {
                "type": "run_pipeline",
                "run_name": target_name,
                "input": str(self.absolute_input),
                "minimum_frames": 12,
                "quality": "fast",
            },
            target_selection,
        )
        legacy_name = self.new_run_name("legacy")
        legacy_start = len(self.backend.history)
        self.backend.send(
            {
                "action": "run_pipeline",
                "name": legacy_name,
                "input": str(self.relative_input),
                "minimum_frames": 4,
                "quality": "medium",
            }
        )

        target_done = self.assert_successful_lifecycle(target_events, target_name)
        self.assertEqual(
            target_done["output"],
            str(self.test_root / "data" / "output" / target_name / f"{target_name}_fast.obj"),
        )
        self.assert_artifacts(target_name, "fast", 1, 12)

        def legacy_selection(action: dict[str, Any]) -> None:
            self.backend.send({"type": "selection", "choice": "2"})

        legacy_events = self.collect_to_terminal(legacy_start, legacy_selection)
        self.assert_successful_lifecycle(legacy_events, legacy_name)
        self.assert_artifacts(legacy_name, "medium", 2, 4)

        skip_name = self.new_run_name("skip")

        def skip_selection(action: dict[str, Any]) -> None:
            self.backend.send(
                {
                    "type": "selection",
                    "request_id": action["request_id"],
                    "choice": "skip",
                }
            )

        skip_events = self.run_to_terminal(
            {
                "type": "run_pipeline",
                "run_name": skip_name,
                "input": str(self.relative_input),
                "minimum_frames": 1,
                "quality": "detailed",
            },
            skip_selection,
        )
        self.assert_successful_lifecycle(skip_events, skip_name)
        self.assert_artifacts(skip_name, "detailed", "skip", 1)

        cancel_name = self.new_run_name("cancel")

        def cancel_at_action(action: dict[str, Any]) -> None:
            self.backend.send(
                {"type": "cancel_pipeline", "run_name": "not-the-active-run"}
            )
            mismatch = self.backend.wait_for_type("error")
            self.assertEqual(mismatch.get("code"), "run_mismatch")
            self.backend.send(
                {"type": "cancel_pipeline", "run_name": cancel_name}
            )

        cancel_events = self.run_to_terminal(
            {
                "type": "run_pipeline",
                "run_name": cancel_name,
                "input": str(self.relative_input),
                "minimum_frames": 5,
                "quality": "fast",
            },
            cancel_at_action,
        )
        self.backend.send({"type": "cancel_pipeline", "run_name": cancel_name})
        terminals = [event for event in cancel_events if is_terminal(event)]
        self.assertEqual(terminals, [{"type": "cancelled", "run_name": cancel_name}])
        no_active = self.backend.wait_for_type("error")
        self.assertEqual(no_active.get("code"), "no_active_run")
        cancel_manifest = json.loads(
            (self.test_root / "data" / "runs" / cancel_name / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(cancel_manifest["status"]["state"], "cancelled")

        for run_name in (target_name, legacy_name, skip_name, cancel_name):
            matching_terminals = [
                message
                for message in self.backend.history
                if is_terminal(message) and message.get("run_name") == run_name
            ]
            self.assertEqual(len(matching_terminals), 1, run_name)

    def test_selection_after_accepted_cancellation_is_rejected(self) -> None:
        dummy = load_dummy_module()
        backend = dummy.DummyBackend(self.test_root, step_delay=0.0)
        messages: list[dict[str, Any]] = []
        backend.send = messages.append
        config = dummy.RunConfig("selection-race", "input.mp4", 1, "fast", False)
        cancel_event = threading.Event()
        pending = dummy.PendingAction(
            request_id="selection-race-mask-frame-001",
            count=3,
            allow_legacy_response=False,
            event=threading.Event(),
        )
        backend._active_config = config
        backend._cancel_event = cancel_event
        backend._pending_action = pending

        backend._accept_cancellation(
            {"type": "cancel_pipeline", "run_name": config.run_name}
        )
        backend._accept_selection(
            {
                "type": "selection",
                "request_id": pending.request_id,
                "choice": 1,
            }
        )

        self.assertTrue(cancel_event.is_set())
        self.assertIsNone(pending.choice)
        self.assertFalse(pending.event.is_set())
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].get("scope"), "command")
        self.assertEqual(messages[0].get("code"), "run_cancelling")

    def test_cancellation_accepted_before_completion_commit_wins(self) -> None:
        dummy = load_dummy_module()
        direct_root = self.test_root / "direct-cancellation"
        direct_root.mkdir()
        input_path = direct_root / "input.mp4"
        input_path.write_bytes(b"dummy input")
        backend = dummy.DummyBackend(direct_root, step_delay=0.0)
        messages: list[dict[str, Any]] = []
        action_ready = threading.Event()
        phase_five_completed = threading.Event()
        release_completion = threading.Event()

        def capture_send(message: dict[str, Any]) -> None:
            messages.append(message)
            if message.get("type") == "action_required":
                action_ready.set()
            if (
                message.get("type") == "phase_completed"
                and message.get("phase") == 5
            ):
                phase_five_completed.set()
                if not release_completion.wait(timeout=5.0):
                    raise AssertionError("Test did not release completion commitment")

        backend.send = capture_send
        run_name = self.new_run_name("near-completion")
        backend._accept_run(
            {
                "type": "run_pipeline",
                "run_name": run_name,
                "input": str(input_path),
                "minimum_frames": 3,
                "quality": "fast",
            }
        )
        self.assertTrue(action_ready.wait(timeout=5.0))
        action = next(
            message for message in messages if message.get("type") == "action_required"
        )
        backend._accept_selection(
            {
                "type": "selection",
                "request_id": action["request_id"],
                "choice": 0,
            }
        )
        self.assertTrue(phase_five_completed.wait(timeout=5.0))
        with backend._state_lock:
            worker = backend._worker
        self.assertIsNotNone(worker)
        backend._accept_cancellation(
            {"type": "cancel_pipeline", "run_name": run_name}
        )
        release_completion.set()
        assert worker is not None
        worker.join(timeout=5.0)
        self.assertFalse(worker.is_alive())

        terminals = [message for message in messages if is_terminal(message)]
        self.assertEqual(terminals, [{"type": "cancelled", "run_name": run_name}])
        terminal_index = messages.index(terminals[0])
        self.assertFalse(
            any(
                message.get("type") in LIFECYCLE_TYPES
                for message in messages[terminal_index + 1 :]
            )
        )
        backend._accept_cancellation(
            {"type": "cancel_pipeline", "run_name": run_name}
        )
        self.assertEqual(messages[-1].get("code"), "no_active_run")

    def test_terminal_manifest_failure_emits_one_run_error(self) -> None:
        dummy = load_dummy_module()
        backend = dummy.DummyBackend(self.test_root, step_delay=0.0)
        messages: list[dict[str, Any]] = []
        backend.send = messages.append
        config = dummy.RunConfig("manifest-failure", "input.mp4", 3, "fast", False)
        cancel_event = threading.Event()
        backend._active_config = config
        backend._cancel_event = cancel_event

        def fail_manifest_update(*args: Any, **kwargs: Any) -> None:
            raise OSError("deterministic manifest failure")

        backend._update_terminal_manifest = fail_manifest_update
        backend._commit_terminal(
            config,
            cancel_event,
            self.test_root / "workspace",
            self.test_root / "workspace" / "manifest.json",
            self.test_root / "output.obj",
            None,
        )

        terminals = [message for message in messages if is_terminal(message)]
        self.assertEqual(len(terminals), 1)
        self.assertEqual(terminals[0].get("type"), "error")
        self.assertEqual(
            terminals[0].get("code"), "dummy_manifest_finalization_failed"
        )
        self.assertIn("deterministic manifest failure", terminals[0].get("text", ""))
        self.assertIsNone(backend._active_config)


if __name__ == "__main__":
    unittest.main()
