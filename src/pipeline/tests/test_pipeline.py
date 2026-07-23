"""Dependency-free tests for the production pipeline orchestrator."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.pipeline.core.config import RunCancelled
from src.pipeline.core.pipeline import run_pipeline_with_args


class TestPipelineOrchestration(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        self.input_path = self.root / "input.mp4"
        self.input_path.write_bytes(b"test input")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _args(self, run_name: str = "test-run") -> dict[str, object]:
        return {
            "run_name": run_name,
            "input": str(self.input_path),
            "minimum_frames": 3,
            "quality": "detailed",
        }

    def test_structured_results_lifecycle_quality_and_manifest(self) -> None:
        lifecycle: list[tuple[object, ...]] = []
        calls: dict[str, dict[str, object]] = {}
        action_callback = object()
        declared_capture = self.root / "declared-capture"
        declared_masking = self.root / "declared-masking"
        declared_2dgs = self.root / "declared-2dgs"
        declared_mesh = self.root / "declared-mesh.ply"
        declared_output = self.root / "declared-output.obj"

        def record(name: str, kwargs: dict[str, object]) -> None:
            calls[name] = kwargs
            kwargs["progress_cb"](0.5, f"{name} halfway")  # type: ignore[operator]

        def capture(**kwargs):
            record("capture", kwargs)
            return SimpleNamespace(
                output_dir=declared_capture,
                extracted_frames=[declared_capture / "frame.png"],
                frame_count=1,
                source_type="video",
            )

        def masking(**kwargs):
            record("masking", kwargs)
            self.assertEqual(kwargs["raw_frames_dir"], declared_capture)
            self.assertIs(kwargs["action_cb"], action_callback)
            return SimpleNamespace(
                output_dir=declared_masking,
                mask_paths=[declared_masking / "mask.png"],
                mask_count=1,
            )

        def spatial(**kwargs):
            record("spatial", kwargs)
            self.assertEqual(kwargs["masked_frames_dir"], declared_masking)
            return SimpleNamespace(
                spatial_dir=self.root / "declared-spatial",
                input_2dgs_dir=declared_2dgs,
                transforms_json_path=self.root / "transforms.json",
                init_points_ply_path=self.root / "points.ply",
                registered_cameras_count=1,
            )

        def geometry(**kwargs):
            record("geometry", kwargs)
            self.assertEqual(kwargs["input_2dgs_dir"], declared_2dgs)
            return SimpleNamespace(
                geometry_dir=self.root / "declared-geometry",
                fused_mesh_path=declared_mesh,
            )

        def export(**kwargs):
            record("export", kwargs)
            self.assertEqual(kwargs["fused_mesh_path"], declared_mesh)
            self.assertEqual(kwargs["quality_preset"], "detailed")
            return SimpleNamespace(
                export_dir=self.root / "declared-export",
                primary_obj_path=declared_output,
                texture_path=None,
            )

        result = run_pipeline_with_args(
            self._args(),
            project_root=self.root,
            phase_functions={
                "capture": capture,
                "masking": masking,
                "spatial": spatial,
                "geometry": geometry,
                "export": export,
            },
            action_cb=action_callback,
            workspace_ready_cb=lambda run, path: lifecycle.append(
                ("workspace_ready", run, path)
            ),
            phase_started_cb=lambda phase, label: lifecycle.append(
                ("started", phase, label)
            ),
            progress_cb=lambda phase, value, label: lifecycle.append(
                ("progress", phase, value, label)
            ),
            phase_completed_cb=lambda phase: lifecycle.append(("completed", phase)),
        )

        self.assertEqual(result["output"], str(declared_output))
        self.assertEqual(set(calls), {"capture", "masking", "spatial", "geometry", "export"})
        self.assertEqual(lifecycle[0][0], "workspace_ready")
        for phase in range(1, 6):
            started = next(i for i, event in enumerate(lifecycle) if event[:2] == ("started", phase))
            progress = next(i for i, event in enumerate(lifecycle) if event[:2] == ("progress", phase))
            completed = next(i for i, event in enumerate(lifecycle) if event == ("completed", phase))
            self.assertLess(started, progress)
            self.assertLess(progress, completed)

        manifest_path = self.root / "data" / "runs" / "test-run" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["configuration"]["quality"], "detailed")
        self.assertEqual(manifest["configuration"]["input_path"], str(self.input_path))
        self.assertEqual(manifest["status"]["state"], "completed")
        self.assertEqual(manifest["status"]["current_phase"], None)
        self.assertEqual(manifest["status"]["completed_phases"], [1, 2, 3, 4, 5])
        self.assertEqual(manifest["artifacts"]["capture"]["output_dir"], str(declared_capture))
        self.assertEqual(manifest["artifacts"]["primary_output"], str(declared_output))
        self.assertEqual(manifest["output"], str(declared_output))

    def test_progress_does_not_complete_a_failed_phase(self) -> None:
        events: list[tuple[str, int]] = []

        def failing_capture(**kwargs):
            kwargs["progress_cb"](1.0, "module reported full progress")
            raise RuntimeError("capture failed after progress")

        with self.assertRaisesRegex(RuntimeError, "capture failed"):
            run_pipeline_with_args(
                self._args("failed-run"),
                project_root=self.root,
                phase_functions={"capture": failing_capture},
                phase_started_cb=lambda phase, label: events.append(("started", phase)),
                phase_completed_cb=lambda phase: events.append(("completed", phase)),
            )

        self.assertEqual(events, [("started", 1)])
        manifest = json.loads(
            (self.root / "data" / "runs" / "failed-run" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["status"]["state"], "failed")
        self.assertEqual(manifest["status"]["completed_phases"], [])
        self.assertIn("capture failed", manifest["status"]["error"])

    def test_cancellation_writes_terminal_manifest_state(self) -> None:
        with self.assertRaises(RunCancelled):
            run_pipeline_with_args(
                self._args("cancelled-run"),
                project_root=self.root,
                phase_functions={},
                is_cancelled=lambda: True,
            )

        manifest = json.loads(
            (self.root / "data" / "runs" / "cancelled-run" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["status"]["state"], "cancelled")
        self.assertEqual(manifest["status"]["completed_phases"], [])
        self.assertIsNone(manifest["output"])

    def test_validation_happens_before_workspace_creation(self) -> None:
        args = self._args("invalid-run")
        args["input"] = str(self.root / "missing.mp4")
        with self.assertRaises(Exception):
            run_pipeline_with_args(args, project_root=self.root, phase_functions={})
        self.assertFalse((self.root / "data" / "runs" / "invalid-run").exists())


if __name__ == "__main__":
    unittest.main()
