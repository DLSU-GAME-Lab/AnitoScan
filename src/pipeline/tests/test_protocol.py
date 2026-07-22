"""Unit tests for Protocol v1 Python schemas, constructors, and validation."""

from __future__ import annotations

import unittest
from src.pipeline.core.protocol import (
    PROTOCOL_VERSION,
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


class TestProtocolSchemas(unittest.TestCase):
    def test_phase_enum_values(self) -> None:
        self.assertEqual(Phase.NONE, 0)
        self.assertEqual(Phase.CAPTURE, 1)
        self.assertEqual(Phase.MASKING, 2)
        self.assertEqual(Phase.SPATIAL, 3)
        self.assertEqual(Phase.GEOMETRY, 4)
        self.assertEqual(Phase.EXPORT, 5)

    def test_run_pipeline_command_validation(self) -> None:
        valid_data = {
            "type": "run_pipeline",
            "run_name": "test_run",
            "input": "data/input/test.mp4",
            "minimum_frames": 45,
            "quality": "fast",
            "extra_setting": True,
        }
        cmd = RunPipelineCommand.from_dict(valid_data)
        self.assertEqual(cmd.run_name, "test_run")
        self.assertEqual(cmd.input, "data/input/test.mp4")
        self.assertEqual(cmd.minimum_frames, 45)
        self.assertEqual(cmd.quality, "fast")
        self.assertEqual(cmd.extra_fields, {"extra_setting": True})

        # Test invalid type
        invalid_type = dict(valid_data, type="wrong")
        with self.assertRaises(ValueError):
            RunPipelineCommand.from_dict(invalid_type)

        # Test missing field
        missing = dict(valid_data)
        del missing["run_name"]
        with self.assertRaises(ValueError):
            RunPipelineCommand.from_dict(missing)

        # Test unsafe run name
        unsafe = dict(valid_data, run_name="../bad_name")
        with self.assertRaises(ValueError):
            RunPipelineCommand.from_dict(unsafe)

    def test_selection_command_validation(self) -> None:
        valid_int = {"type": "selection", "request_id": "req-1", "choice": 2}
        cmd_int = SelectionCommand.from_dict(valid_int)
        self.assertEqual(cmd_int.request_id, "req-1")
        self.assertEqual(cmd_int.choice, 2)

        valid_skip = {"type": "selection", "request_id": "req-1", "choice": "skip"}
        cmd_skip = SelectionCommand.from_dict(valid_skip)
        self.assertEqual(cmd_skip.choice, "skip")

        # Reject missing request_id
        no_req = {"type": "selection", "choice": 0}
        with self.assertRaises(ValueError):
            SelectionCommand.from_dict(no_req)

        # Reject numeric strings
        str_choice = {"type": "selection", "request_id": "req-1", "choice": "2"}
        with self.assertRaises(ValueError):
            SelectionCommand.from_dict(str_choice)

    def test_cancel_pipeline_command_validation(self) -> None:
        valid = {"type": "cancel_pipeline", "run_name": "run_123"}
        cmd = CancelPipelineCommand.from_dict(valid)
        self.assertEqual(cmd.run_name, "run_123")

        invalid = {"type": "cancel_pipeline"}
        with self.assertRaises(ValueError):
            CancelPipelineCommand.from_dict(invalid)

    def test_event_constructors(self) -> None:
        self.assertEqual(
            make_backend_ready(),
            {"type": "backend_ready", "protocol_version": PROTOCOL_VERSION},
        )
        self.assertEqual(make_log("hello"), {"type": "log", "text": "hello"})
        self.assertEqual(
            make_workspace_ready("run1", "data/runs/run1"),
            {
                "type": "workspace_ready",
                "run_name": "run1",
                "workspace": "data/runs/run1",
            },
        )
        self.assertEqual(
            make_phase_started(Phase.CAPTURE, "Capture"),
            {"type": "phase_started", "phase": 1, "label": "Capture"},
        )
        self.assertEqual(
            make_progress(Phase.CAPTURE, 0.5, 0.1, "Extracting"),
            {
                "type": "progress",
                "phase": 1,
                "value": 0.5,
                "overall_value": 0.1,
                "label": "Extracting",
            },
        )
        self.assertEqual(
            make_action_required("req1", "mask", Phase.MASKING, "f1.png", "p1.png", 3),
            {
                "type": "action_required",
                "request_id": "req1",
                "action": "mask",
                "phase": 2,
                "frame": "f1.png",
                "preview": "p1.png",
                "count": 3,
            },
        )
        self.assertEqual(
            make_phase_completed(Phase.CAPTURE),
            {"type": "phase_completed", "phase": 1},
        )
        self.assertEqual(
            make_done("run1", "ws", "out.obj"),
            {"type": "done", "run_name": "run1", "workspace": "ws", "output": "out.obj"},
        )
        self.assertEqual(
            make_cancelled("run1"), {"type": "cancelled", "run_name": "run1"}
        )
        self.assertEqual(
            make_error("command", "invalid", "bad cmd", run_name="run1"),
            {
                "type": "error",
                "scope": "command",
                "code": "invalid",
                "text": "bad cmd",
                "run_name": "run1",
            },
        )


if __name__ == "__main__":
    unittest.main()
