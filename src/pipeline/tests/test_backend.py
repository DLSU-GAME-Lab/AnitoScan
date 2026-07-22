"""Unit tests for ProductionBackend IPC entrypoint."""

from __future__ import annotations

import tempfile
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


if __name__ == "__main__":
    unittest.main()
