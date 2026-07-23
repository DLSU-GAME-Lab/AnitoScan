"""Unit tests for reorganized 3D reconstruction pipeline modules.

Verifies:
1. Module API return structures (CaptureResult, MaskingResult, SpatialResult, GeometryResult, ExportResult).
2. Injected callback execution (progress_cb, log_cb, action_cb, is_cancelled/check_cancelled).
3. Zero direct IPC imports in phase modules.
4. Clean cancellation behavior (RunCancelled).
5. Safe platform execution (mocking GPU/heavy dependencies).
"""

import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Configure robust mock modules prior to importing pipeline packages
mock_numpy = MagicMock()
mock_numpy.zeros.return_value = MagicMock()
mock_numpy.eye.return_value.tolist.return_value = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]

mock_cv2 = MagicMock()
mock_cv2_img = MagicMock()
mock_cv2_img.shape = (100, 100, 3)
mock_cv2_img.ndim = 3
mock_cv2.imread.return_value = mock_cv2_img
mock_cv2.imwrite.return_value = True

MOCK_MODULES = {
    "cv2": mock_cv2,
    "numpy": mock_numpy,
    "torch": MagicMock(),
    "ultralytics": MagicMock(),
    "ultralytics.models": MagicMock(),
    "ultralytics.models.yolo": MagicMock(),
    "ultralytics.models.sam": MagicMock(),
    "pymeshlab": MagicMock(),
    "pycolmap": MagicMock(),
    "trimesh": MagicMock(),
}

for mod_name, mock_obj in MOCK_MODULES.items():
    try:
        __import__(mod_name)
    except ImportError:
        sys.modules[mod_name] = mock_obj

# Ensure pipeline modules directory is in Python path
TESTS_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = TESTS_DIR.parent
MODULES_DIR = PIPELINE_DIR / "modules"

if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

# Import module dataclasses and cancel exceptions
from capture import CaptureResult, RunCancelled as CaptureCancelled, run_capture
from export import ExportResult, RunCancelled as ExportCancelled, run_export_and_baking
from geometry import GeometryResult, RunCancelled as GeometryCancelled, run_surface_reconstruction
from remove_background import MaskingResult, RunCancelled as MaskingCancelled, run_remove_background
from spatial import SpatialResult, RunCancelled as SpatialCancelled, run_spatial_reconstruction


class TestModuleInvariants(unittest.TestCase):
    """Verifies architectural rules across all phase modules."""

    def setUp(self):
        self.module_files = [
            MODULES_DIR / "capture.py",
            MODULES_DIR / "remove_background.py",
            MODULES_DIR / "spatial.py",
            MODULES_DIR / "geometry.py",
            MODULES_DIR / "export.py",
        ]

    def test_zero_ipc_imports(self):
        """Ensure no phase module imports from 'ipc'."""
        for filepath in self.module_files:
            if not filepath.exists():
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(filepath))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotEqual(
                            alias.name, "ipc", f"{filepath.name} directly imports 'ipc'"
                        )
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(
                        node.module, "ipc", f"{filepath.name} imports from 'ipc'"
                    )

    def test_no_direct_manifest_writes(self):
        """Ensure phase modules do not directly write manifest.json."""
        for filepath in self.module_files:
            if not filepath.exists():
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertNotIn(
                "manifest.json",
                content,
                f"{filepath.name} directly references manifest.json (ownership belongs to pipeline.py)",
            )


class TestCaptureModule(unittest.TestCase):
    """Tests Phase 1: Capture module."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        self.input_dir = self.root / "input_frames"
        self.output_dir = self.root / "01_capture"
        self.input_dir.mkdir(parents=True, exist_ok=True)

        (self.input_dir / "frame_0001.png").touch()
        (self.input_dir / "frame_0002.png").touch()

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("shutil.copy2")
    def test_run_capture_success(self, mock_copy):
        progress_logs = []
        text_logs = []

        def progress_cb(val, label):
            progress_logs.append((val, label))

        def log_cb(text):
            text_logs.append(text)

        result = run_capture(
            input_source=self.input_dir,
            output_dir=self.output_dir,
            minimum_frames=2,
            is_image_mode=True,
            progress_cb=progress_cb,
            log_cb=log_cb,
        )

        self.assertIsInstance(result, CaptureResult)
        self.assertEqual(result.frame_count, 2)
        self.assertEqual(len(result.extracted_frames), 2)
        self.assertTrue(len(progress_logs) > 0)

    def test_run_capture_cancellation(self):
        def is_cancelled():
            return True

        with self.assertRaises(CaptureCancelled):
            run_capture(
                input_source=self.input_dir,
                output_dir=self.output_dir,
                minimum_frames=2,
                is_image_mode=True,
                is_cancelled=is_cancelled,
            )


class TestRemoveBackgroundModule(unittest.TestCase):
    """Tests Phase 2: Background removal module."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        self.input_dir = self.root / "01_capture"
        self.output_dir = self.root / "02_masking"
        self.input_dir.mkdir(parents=True, exist_ok=True)

        (self.input_dir / "frame_0000.png").touch()

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("ultralytics.models.yolo.YOLOE")
    @patch("ultralytics.models.sam.SAM")
    def test_run_remove_background_success(self, mock_sam, mock_yolo):
        mock_yolo_inst = MagicMock()
        mock_yolo.return_value = mock_yolo_inst

        # Mock bounding box with .tolist() support
        mock_coords = MagicMock()
        mock_coords.__getitem__.side_effect = lambda idx: [10, 10, 50, 50][idx]
        mock_coords.tolist.return_value = [10, 10, 50, 50]

        mock_box = MagicMock()
        mock_box.xyxy = [MagicMock(cpu=lambda: MagicMock(numpy=lambda: mock_coords))]
        mock_det_res = MagicMock()
        mock_det_res.boxes = [mock_box]
        mock_yolo_inst.predict.return_value = [mock_det_res]

        mock_sam_inst = MagicMock()
        mock_sam.return_value = mock_sam_inst

        # Configure mask object with magic methods for NumPy array operations
        mock_mask_np = MagicMock()
        mock_mask_np.__gt__.return_value = mock_mask_np
        mock_mask_np.astype.return_value = mock_mask_np
        mock_mask_np.__mul__.return_value = mock_mask_np

        mock_mask_data = MagicMock()
        mock_mask_data.cpu.return_value.numpy.return_value = mock_mask_np
        mock_sam_res = MagicMock()
        mock_sam_res.masks.data = [mock_mask_data]
        mock_sam_inst.predict.return_value = [mock_sam_res]

        progress_logs = []

        def progress_cb(val, label):
            progress_logs.append((val, label))

        def action_cb(preview_path, box_count, frame_name):
            return 0

        result = run_remove_background(
            raw_frames_dir=self.input_dir,
            output_dir=self.output_dir,
            action_cb=action_cb,
            progress_cb=progress_cb,
        )

        self.assertIsInstance(result, MaskingResult)
        self.assertEqual(result.mask_count, 1)
        self.assertEqual(len(result.mask_paths), 1)

    def test_run_remove_background_cancellation(self):
        def is_cancelled():
            return True

        with self.assertRaises(MaskingCancelled):
            run_remove_background(
                raw_frames_dir=self.input_dir,
                output_dir=self.output_dir,
                is_cancelled=is_cancelled,
            )


class TestSpatialModule(unittest.TestCase):
    """Tests Phase 3: Spatial reconstruction module."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        self.input_dir = self.root / "02_masking"
        self.output_dir = self.root / "03_spatial"
        self.input_dir.mkdir(parents=True, exist_ok=True)

        (self.input_dir / "frame_0000.png").touch()

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("spatial.prepare_2dgs_images", return_value=1)
    def test_run_spatial_reconstruction_fallback(self, mock_prep):
        progress_logs = []

        def progress_cb(val, label):
            progress_logs.append((val, label))

        result = run_spatial_reconstruction(
            masked_frames_dir=self.input_dir,
            output_dir=self.output_dir,
            progress_cb=progress_cb,
        )

        self.assertIsInstance(result, SpatialResult)
        self.assertTrue(result.transforms_json_path.exists())
        self.assertTrue(result.init_points_ply_path.exists())
        self.assertTrue(result.input_2dgs_dir.exists())

    def test_run_spatial_cancellation(self):
        def is_cancelled():
            return True

        with self.assertRaises(SpatialCancelled):
            run_spatial_reconstruction(
                masked_frames_dir=self.input_dir,
                output_dir=self.output_dir,
                is_cancelled=is_cancelled,
            )


class TestGeometryModule(unittest.TestCase):
    """Tests Phase 4: Surface reconstruction module."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        self.input_2dgs_dir = self.root / "03_spatial" / "input_for_2dgs"
        self.output_dir = self.root / "04_geometry"

        sparse_dir = self.input_2dgs_dir / "sparse" / "0"
        sparse_dir.mkdir(parents=True, exist_ok=True)
        (sparse_dir / "points3D.txt").write_text("# mock points", encoding="utf-8")
        (sparse_dir / "cameras.txt").write_text("# mock cameras", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("subprocess.Popen")
    def test_run_surface_reconstruction_success(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.stdout = ["100/1000", "Render complete"]
        mock_proc.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        mesh_dir = self.output_dir / "vanilla_2dgs" / "train" / "ours_1000"
        mesh_dir.mkdir(parents=True, exist_ok=True)
        (mesh_dir / "fused_post.ply").write_text("ply\nformat ascii 1.0\nend_header\n", encoding="utf-8")

        result = run_surface_reconstruction(
            input_2dgs_dir=self.input_2dgs_dir,
            output_dir=self.output_dir,
            train_iterations=1000,
        )

        self.assertIsInstance(result, GeometryResult)
        self.assertEqual(result.fused_mesh_path.resolve(), (self.output_dir / "fused_mesh.ply").resolve())
        self.assertTrue(result.fused_mesh_path.exists())

    def test_run_geometry_cancellation(self):
        def is_cancelled():
            return True

        with self.assertRaises(GeometryCancelled):
            run_surface_reconstruction(
                input_2dgs_dir=self.input_2dgs_dir,
                output_dir=self.output_dir,
                is_cancelled=is_cancelled,
            )


class TestExportModule(unittest.TestCase):
    """Tests Phase 5: Export and baking module."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        self.fused_mesh = self.root / "fused_mesh.ply"
        self.output_dir = self.root / "05_export"

        self.fused_mesh.write_text("ply\nformat ascii 1.0\nend_header\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("pymeshlab.MeshSet")
    def test_run_export_and_baking_success(self, mock_meshset_cls):
        mock_ms = MagicMock()
        mock_meshset_cls.return_value = mock_ms

        def mock_save(path_str):
            Path(path_str).touch()

        mock_ms.save_current_mesh.side_effect = mock_save

        result = run_export_and_baking(
            fused_mesh_path=self.fused_mesh,
            output_dir=self.output_dir,
            run_name="test_run",
            quality_preset="fast",
        )

        self.assertIsInstance(result, ExportResult)
        self.assertEqual(result.primary_obj_path.resolve(), (self.output_dir / "test_run_fast.obj").resolve())
        self.assertTrue(result.primary_obj_path.exists())

    def test_run_export_cancellation(self):
        def is_cancelled():
            return True

        with self.assertRaises(ExportCancelled):
            run_export_and_baking(
                fused_mesh_path=self.fused_mesh,
                output_dir=self.output_dir,
                run_name="test_run",
                is_cancelled=is_cancelled,
            )


if __name__ == "__main__":
    unittest.main()
