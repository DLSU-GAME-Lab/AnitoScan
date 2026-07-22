"""Centralized pipeline configuration, validation, quality presets, and manifest serialization."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

RUN_NAME_REGEX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

QUALITY_PRESETS: Dict[str, Dict[str, int]] = {
    "fast": {
        "train_iterations": 7000,
        "densify_until_iter": 5000,
        "opacity_reset_interval": 1000,
    },
    "medium": {
        "train_iterations": 15000,
        "densify_until_iter": 7500,
        "opacity_reset_interval": 3000,
    },
    "detailed": {
        "train_iterations": 30000,
        "densify_until_iter": 15000,
        "opacity_reset_interval": 3000,
    },
}


class ConfigValidationError(ValueError):
    """Raised when configuration parameters fail validation rules."""


@dataclass
class CaptureConfig:
    minimum_frames: int = 45
    blur_threshold: float = 200.0
    proxy_width: int = 640
    jpg_quality: int = 85
    max_search: int = 3

    def validate(self) -> None:
        if self.minimum_frames <= 0:
            raise ConfigValidationError(f"minimum_frames must be > 0, got {self.minimum_frames}")
        if not (1 <= self.jpg_quality <= 100):
            raise ConfigValidationError(f"jpg_quality must be between 1 and 100, got {self.jpg_quality}")
        if self.proxy_width <= 0:
            raise ConfigValidationError(f"proxy_width must be > 0, got {self.proxy_width}")


@dataclass
class MaskingConfig:
    iou_threshold: float = 0.50
    drift_limit: int = 200
    yoloe_model_size: str = "s"  # "n", "s", "m", "l", "x"

    def validate(self) -> None:
        if not (0.0 <= self.iou_threshold <= 1.0):
            raise ConfigValidationError(f"iou_threshold must be in [0.0, 1.0], got {self.iou_threshold}")
        if self.yoloe_model_size not in {"n", "s", "m", "l", "x"}:
            raise ConfigValidationError(f"Invalid yoloe_model_size: {self.yoloe_model_size}")


@dataclass
class SpatialConfig:
    force: bool = False


@dataclass
class GeometryConfig:
    train_iterations: int = 7000
    densify_until_iter: int = 5000
    opacity_reset_interval: int = 1000

    def validate(self) -> None:
        if self.train_iterations <= 0:
            raise ConfigValidationError(f"train_iterations must be > 0, got {self.train_iterations}")
        if self.densify_until_iter > self.train_iterations:
            raise ConfigValidationError("densify_until_iter cannot exceed train_iterations")


@dataclass
class ExportConfig:
    force: bool = False


@dataclass
class PipelineConfig:
    run_name: str
    input_path: Path
    quality: str = "fast"
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    masking: MaskingConfig = field(default_factory=MaskingConfig)
    spatial: SpatialConfig = field(default_factory=SpatialConfig)
    geometry: GeometryConfig = field(default_factory=GeometryConfig)
    export: ExportConfig = field(default_factory=ExportConfig)

    def __post_init__(self) -> None:
        if isinstance(self.input_path, str):
            self.input_path = Path(self.input_path)

        # Expand quality presets onto geometry config if applicable
        if self.quality in QUALITY_PRESETS:
            preset_vals = QUALITY_PRESETS[self.quality]
            for key, val in preset_vals.items():
                if hasattr(self.geometry, key):
                    setattr(self.geometry, key, val)

    def validate(self, check_path_exists: bool = True) -> None:
        """Runs all platform safety, formatting, and numeric boundary validations."""
        self._validate_run_name(self.run_name)
        if self.quality not in QUALITY_PRESETS:
            raise ConfigValidationError(
                f"Invalid quality preset '{self.quality}'. Must be one of {list(QUALITY_PRESETS.keys())}"
            )

        if check_path_exists and not self.input_path.exists():
            raise ConfigValidationError(f"Input path does not exist: {self.input_path}")

        self.capture.validate()
        self.masking.validate()
        self.geometry.validate()

    @staticmethod
    def _validate_run_name(name: str) -> None:
        if not name:
            raise ConfigValidationError("run_name cannot be empty")
        if name.endswith(".") or name.endswith(" "):
            raise ConfigValidationError(f"run_name cannot end with a dot or space: '{name}'")
        if not RUN_NAME_REGEX.match(name):
            raise ConfigValidationError(
                f"run_name '{name}' does not match required pattern ^[A-Za-z0-9][A-Za-z0-9._-]{{0,127}}$"
            )
        if name.upper() in WINDOWS_RESERVED_NAMES:
            raise ConfigValidationError(f"run_name '{name}' is a Windows reserved device name")

    def to_dict(self) -> Dict[str, Any]:
        """Serializes pipeline configuration to a JSON-compatible dictionary."""
        data = asdict(self)
        data["input_path"] = str(self.input_path)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineConfig":
        """Constructs a PipelineConfig instance from a flat or nested dictionary."""
        data_copy = data.copy()

        run_name = data_copy.pop("run_name", "") or data_copy.pop("name", "")
        raw_input = data_copy.pop("input_path", None) or data_copy.pop("input", "")
        input_path = Path(raw_input) if raw_input else Path()
        quality = data_copy.pop("quality", "fast")

        # Extract nested configs or fallback to top-level key mappings
        capture_data = data_copy.pop("capture", {}) if isinstance(data_copy.get("capture"), dict) else {}
        for k in ("minimum_frames", "blur_threshold", "proxy_width", "jpg_quality", "max_search"):
            if k in data_copy and k not in capture_data:
                capture_data[k] = data_copy.pop(k)

        masking_data = data_copy.pop("masking", {}) if isinstance(data_copy.get("masking"), dict) else {}
        for k in ("iou_threshold", "drift_limit", "yoloe_model_size"):
            if k in data_copy and k not in masking_data:
                masking_data[k] = data_copy.pop(k)

        spatial_data = data_copy.pop("spatial", {}) if isinstance(data_copy.get("spatial"), dict) else {}
        if "force" in data_copy and "force" not in spatial_data:
            spatial_data["force"] = data_copy.get("force")

        geometry_data = data_copy.pop("geometry", {}) if isinstance(data_copy.get("geometry"), dict) else {}
        for k in ("train_iterations", "densify_until_iter", "opacity_reset_interval"):
            if k in data_copy and k not in geometry_data:
                geometry_data[k] = data_copy.pop(k)

        export_data = data_copy.pop("export", {}) if isinstance(data_copy.get("export"), dict) else {}
        if "force" in data_copy and "force" not in export_data:
            export_data["force"] = data_copy.get("force")

        return cls(
            run_name=str(run_name),
            input_path=input_path,
            quality=str(quality),
            capture=CaptureConfig(**capture_data),
            masking=MaskingConfig(**masking_data),
            spatial=SpatialConfig(**spatial_data),
            geometry=GeometryConfig(**geometry_data),
            export=ExportConfig(**export_data),
        )

    def save_manifest(self, output_file: Path) -> None:
        """Writes the configuration manifest to disk."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
