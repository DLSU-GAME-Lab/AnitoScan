"""Unit tests for pipeline configuration validation, presets, and serialization."""

import json
import tempfile
import unittest
from pathlib import Path

from src.pipeline.core.config import (
    ConfigValidationError,
    PipelineConfig,
    QUALITY_PRESETS,
)


class TestPipelineConfig(unittest.TestCase):

    def test_quality_preset_expansion(self) -> None:
        cfg_fast = PipelineConfig(run_name="test_run", input_path=Path("."), quality="fast")
        self.assertEqual(cfg_fast.geometry.train_iterations, QUALITY_PRESETS["fast"]["train_iterations"])

        cfg_detailed = PipelineConfig(run_name="test_run", input_path=Path("."), quality="detailed")
        self.assertEqual(cfg_detailed.geometry.train_iterations, QUALITY_PRESETS["detailed"]["train_iterations"])

    def test_invalid_run_names(self) -> None:
        invalid_names = ["CON", "PRN", "AUX", "COM1", "LPT9", "run.", "run ", ".hidden", "bad/path"]
        for name in invalid_names:
            cfg = PipelineConfig(run_name=name, input_path=Path("."), quality="fast")
            with self.assertRaises(ConfigValidationError, msg=f"Failed to reject invalid run_name: {name}"):
                cfg.validate(check_path_exists=False)

    def test_valid_run_names(self) -> None:
        valid_names = ["valid_run", "run-123", "Run.Name_01"]
        for name in valid_names:
            cfg = PipelineConfig(run_name=name, input_path=Path("."), quality="fast")
            try:
                cfg.validate(check_path_exists=False)
            except ConfigValidationError:
                self.fail(f"Valid run name was unexpectedly rejected: {name}")

    def test_numeric_bounds(self) -> None:
        cfg = PipelineConfig(run_name="valid_run", input_path=Path("."), quality="fast")

        cfg.capture.minimum_frames = 0
        with self.assertRaises(ConfigValidationError):
            cfg.validate(check_path_exists=False)
        cfg.capture.minimum_frames = 45

        cfg.capture.jpg_quality = 105
        with self.assertRaises(ConfigValidationError):
            cfg.validate(check_path_exists=False)

    def test_serialization_and_manifest(self) -> None:
        cfg = PipelineConfig(run_name="serialization_test", input_path=Path("data/input/test.mp4"), quality="medium")
        data = cfg.to_dict()

        reconstructed = PipelineConfig.from_dict(data)
        self.assertEqual(reconstructed.run_name, cfg.run_name)
        self.assertEqual(reconstructed.geometry.train_iterations, QUALITY_PRESETS["medium"]["train_iterations"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest_file = Path(tmp_dir) / "manifest.json"
            cfg.save_manifest(manifest_file)
            self.assertTrue(manifest_file.exists())

            with open(manifest_file, "r", encoding="utf-8") as f:
                loaded_manifest = json.load(f)
            self.assertEqual(loaded_manifest["run_name"], "serialization_test")


if __name__ == "__main__":
    unittest.main()
