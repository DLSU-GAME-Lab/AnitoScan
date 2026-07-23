"""Unit tests for ProductionBackend IPC entrypoint."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.pipeline.core.backend import ProductionBackend


class TestProductionBackend(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmp_dir.name)
        self.backend = ProductionBackend(self.project_root)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    @patch("src.pipeline.core.backend.send")
    def test_ping_command(self, mock_send: MagicMock) -> None:
        self.backend._dispatch({"type": "ping"})
        mock_send.assert_called_once()
        sent_msg = mock_send.call_args[0][0]
        self.assertEqual(sent_msg, {"type": "log", "text": "pong"})

    def test_process_stdout_contains_protocol_json_only(self) -> None:
        backend_path = Path(__file__).resolve().parents[1] / "core" / "backend.py"
        process = subprocess.run(
            [
                sys.executable,
                "-u",
                str(backend_path),
                "--ipc",
                "--project-root",
                str(self.project_root),
            ],
            input='{"type":"ping"}\n',
            text=True,
            capture_output=True,
            timeout=5.0,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        messages = [json.loads(line) for line in process.stdout.splitlines() if line]
        self.assertEqual(
            [message["type"] for message in messages],
            ["backend_ready", "log", "log"],
        )
        self.assertEqual(messages[1], {"type": "log", "text": "pong"})

    @patch("src.pipeline.core.backend.send")
    def test_unknown_command_handling(self, mock_send: MagicMock) -> None:
        self.backend._dispatch({"type": "non_existent_command"})
        mock_send.assert_called_once()
        sent_msg = mock_send.call_args[0][0]
        self.assertEqual(sent_msg["type"], "error")
        self.assertEqual(sent_msg["scope"], "command")
        self.assertEqual(sent_msg["code"], "unknown_command")

    @patch("src.pipeline.core.backend.send")
    def test_run_pipeline_missing_input(self, mock_send: MagicMock) -> None:
        cmd = {
            "type": "run_pipeline",
            "run_name": "run1",
            "input": "non_existent.mp4",
            "minimum_frames": 45,
            "quality": "fast",
        }
        self.backend._dispatch(cmd)
        mock_send.assert_called_once()
        sent_msg = mock_send.call_args[0][0]
        self.assertEqual(sent_msg["type"], "error")
        self.assertEqual(sent_msg["code"], "invalid_run_request")

    @patch("src.pipeline.core.backend.send")
    def test_run_pipeline_already_exists(self, mock_send: MagicMock) -> None:
        input_file = self.project_root / "input.mp4"
        input_file.touch()

        workspace = self.project_root / "data" / "runs" / "existing_run"
        workspace.mkdir(parents=True)

        cmd = {
            "type": "run_pipeline",
            "run_name": "existing_run",
            "input": str(input_file),
            "minimum_frames": 45,
            "quality": "fast",
        }
        self.backend._dispatch(cmd)
        mock_send.assert_called_once()
        sent_msg = mock_send.call_args[0][0]
        self.assertEqual(sent_msg["type"], "error")
        self.assertEqual(sent_msg["code"], "run_already_exists")

    @patch("src.pipeline.core.backend.send")
    def test_selection_without_pending_action(self, mock_send: MagicMock) -> None:
        cmd = {"type": "selection", "request_id": "req-123", "choice": 0}
        self.backend._dispatch(cmd)
        mock_send.assert_called_once()
        sent_msg = mock_send.call_args[0][0]
        self.assertEqual(sent_msg["type"], "error")
        self.assertEqual(sent_msg["code"], "no_pending_action")

    @patch("src.pipeline.core.backend.send")
    def test_cancellation_without_active_run(self, mock_send: MagicMock) -> None:
        cmd = {"type": "cancel_pipeline", "run_name": "run1"}
        self.backend._dispatch(cmd)
        mock_send.assert_called_once()
        sent_msg = mock_send.call_args[0][0]
        self.assertEqual(sent_msg["type"], "error")
        self.assertEqual(sent_msg["code"], "no_active_run")

    @patch("src.pipeline.core.backend.send")
    @patch("src.pipeline.core.pipeline.run_pipeline_with_args")
    def test_worker_lifecycle_progress_and_correlated_action(
        self, mock_pipeline: MagicMock, mock_send: MagicMock
    ) -> None:
        input_file = self.project_root / "input.mp4"
        input_file.touch()

        def fake_pipeline(**kwargs):
            callbacks = kwargs
            callbacks["workspace_ready_cb"]("worker-run", str(self.project_root / "workspace"))
            for phase in range(1, 6):
                callbacks["phase_started_cb"](phase, f"Phase {phase}")
                callbacks["progress_cb"](phase, 0.5, "halfway")
                if phase == 2:
                    choice = callbacks["action_cb"]("preview.png", 3, "frame.png")
                    self.assertEqual(choice, 1)
                callbacks["phase_completed_cb"](phase)
            return {"output": str(self.project_root / "result.obj")}

        mock_pipeline.side_effect = fake_pipeline
        self.backend._dispatch(
            {
                "type": "run_pipeline",
                "run_name": "worker-run",
                "input": str(input_file),
                "minimum_frames": 3,
                "quality": "medium",
            }
        )
        worker = self.backend._worker
        self.assertIsNotNone(worker)

        deadline = time.monotonic() + 2.0
        while self.backend._pending_action is None and time.monotonic() < deadline:
            time.sleep(0.01)
        pending = self.backend._pending_action
        self.assertIsNotNone(pending)
        assert pending is not None
        self.backend._dispatch(
            {"type": "selection", "request_id": pending.request_id, "choice": 1}
        )
        assert worker is not None
        worker.join(timeout=2.0)
        self.assertFalse(worker.is_alive())

        messages = [call.args[0] for call in mock_send.call_args_list]
        self.assertEqual([m["phase"] for m in messages if m["type"] == "phase_started"], [1, 2, 3, 4, 5])
        self.assertEqual([m["phase"] for m in messages if m["type"] == "phase_completed"], [1, 2, 3, 4, 5])
        progress = [m for m in messages if m["type"] == "progress"]
        self.assertEqual([m["phase"] for m in progress], [1, 2, 3, 4, 5])
        self.assertEqual([m["overall_value"] for m in progress], [0.1, 0.3, 0.5, 0.7, 0.9])
        actions = [m for m in messages if m["type"] == "action_required"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["request_id"], pending.request_id)
        terminals = [
            m for m in messages
            if m["type"] in {"done", "cancelled"}
            or (m["type"] == "error" and m.get("scope") in {"run", "backend"})
        ]
        self.assertEqual(len(terminals), 1)
        self.assertEqual(terminals[0]["type"], "done")

    @patch("src.pipeline.core.backend.send")
    @patch("src.pipeline.core.pipeline.run_pipeline_with_args")
    def test_pending_action_cancellation_is_responsive_and_has_one_terminal(
        self, mock_pipeline: MagicMock, mock_send: MagicMock
    ) -> None:
        input_file = self.project_root / "input.mp4"
        input_file.touch()

        def fake_pipeline(**kwargs):
            kwargs["workspace_ready_cb"]("cancel-run", str(self.project_root / "workspace"))
            kwargs["phase_started_cb"](2, "Masking")
            kwargs["action_cb"]("preview.png", 2, "frame.png")
            self.fail("cancelled action unexpectedly returned")

        mock_pipeline.side_effect = fake_pipeline
        self.backend._dispatch(
            {
                "type": "run_pipeline",
                "run_name": "cancel-run",
                "input": str(input_file),
                "minimum_frames": 3,
                "quality": "fast",
            }
        )
        worker = self.backend._worker
        self.assertIsNotNone(worker)

        deadline = time.monotonic() + 2.0
        while self.backend._pending_action is None and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNotNone(self.backend._pending_action)
        self.backend._dispatch({"type": "cancel_pipeline", "run_name": "cancel-run"})
        assert worker is not None
        worker.join(timeout=2.0)
        self.assertFalse(worker.is_alive())

        messages = [call.args[0] for call in mock_send.call_args_list]
        terminals = [
            m for m in messages
            if m["type"] in {"done", "cancelled"}
            or (m["type"] == "error" and m.get("scope") in {"run", "backend"})
        ]
        self.assertEqual(terminals, [{"type": "cancelled", "run_name": "cancel-run"}])


if __name__ == "__main__":
    unittest.main()
