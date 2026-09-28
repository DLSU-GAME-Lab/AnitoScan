"""Deterministic BM5 membership and content identity, independent of mask success."""

import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from cancellation import check_cancelled
from config import normalize_evaluation_settings

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SPLIT_ALGORITHM = "evenly_spaced_linspace_v1"
PREPARATION_VERSION = "bgra8_white_gaussian3x3_v1"


def write_evaluation_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically publish a split, cache identity, or partial localization result."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary_path.replace(path)


def content_digest(path: Path, cancel_event=None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            check_cancelled(cancel_event)
            digest.update(chunk)
    return digest.hexdigest()


def build_evaluation_split(
    raw_frames_dir: Path,
    masked_frames_dir: Path,
    test_fraction: float = 0.2,
    cancel_event=None,
) -> dict[str, Any]:
    """Return the split.json schema without modifying any files.

    Sort raw filenames, map each stem to .png, then choose floor(N*f) indices
    using linspace(0, N-1, count, dtype=int), including endpoints when count > 1.
    Eligibility never changes membership. Coverage is the fraction of nonzero
    alpha pixels; unavailable/invalid masks have coverage 0 and an exclusion.
    The fingerprint covers raw and masked bytes, membership, eligibility, and
    the preparation version, not timestamps or absolute workspace paths.
    """
    check_cancelled(cancel_event)
    test_fraction = normalize_evaluation_settings({"evaluate_quality": True, "test_fraction": test_fraction})["test_fraction"]
    raw_frames = sorted(
        path for path in raw_frames_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not raw_frames:
        raise ValueError("BM5 requires raw frames before creating an evaluation split.")

    frames = [f"{path.stem}.png" for path in raw_frames]
    if len(set(frames)) != len(frames):
        raise ValueError("BM5 raw frame stems must map to unique masked PNG filenames.")
    test_count = math.floor(len(frames) * Decimal(str(test_fraction)))
    test_indices = set(
        np.linspace(0, len(frames) - 1, test_count, dtype=int).tolist()
    )
    split: dict[str, Any] = {
        "train": [frame for i, frame in enumerate(frames) if i not in test_indices],
        "test": [frame for i, frame in enumerate(frames) if i in test_indices],
        "usable_train": [],
        "usable_test": [],
        "excluded": [],
        "foreground_coverage": {},
        "test_fraction": test_fraction,
        "algorithm": SPLIT_ALGORITHM,
    }
    input_contents = []
    for i, (raw_path, frame) in enumerate(zip(raw_frames, frames)):
        check_cancelled(cancel_event)
        membership = "test" if i in test_indices else "train"
        raw_digest = None
        mask_digest = None
        reason = None
        coverage = 0.0
        try:
            raw_digest = content_digest(raw_path, cancel_event)
        except OSError:
            reason = "unreadable_raw_frame"

        mask_path = masked_frames_dir / frame
        try:
            mask_bytes = mask_path.read_bytes()
        except FileNotFoundError:
            reason = reason or "missing_mask"
        except OSError:
            reason = reason or "unreadable_mask"
        else:
            mask_digest = hashlib.sha256(mask_bytes).hexdigest()
            try:
                image = (
                    cv2.imdecode(np.frombuffer(mask_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                    if mask_bytes else None
                )
            except cv2.error:
                image = None
            if image is None:
                reason = reason or "unreadable_mask"
            elif image.ndim != 3 or image.shape[2] != 4 or image.dtype != np.uint8:
                reason = reason or "invalid_mask_format"
            else:
                alpha = image[:, :, 3]
                coverage = float(np.count_nonzero(alpha) / alpha.size)
                if coverage == 0:
                    reason = reason or "all_transparent"

        split["foreground_coverage"][frame] = coverage
        if reason is None:
            split[f"usable_{membership}"].append(frame)
        else:
            split["excluded"].append({"frame": frame, "split": membership, "reason": reason})
        input_contents.append({
            "raw_frame": raw_path.name,
            "frame": frame,
            "raw_sha256": raw_digest,
            "masked_sha256": mask_digest,
        })

    identity = {
        "preparation_version": PREPARATION_VERSION,
        "inputs": input_contents,
        "split": split,
    }
    split["fingerprint"] = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    return split
