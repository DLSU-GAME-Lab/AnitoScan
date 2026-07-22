"""Protocol v1 constants, command schemas, event constructors, and strict validators."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Literal

PROTOCOL_VERSION = 1

QUALITY_PRESETS = {"fast", "medium", "detailed"}
SAFE_RUN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
WINDOWS_RESERVED_RUN_NAME = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.IGNORECASE
)


class Phase(IntEnum):
    NONE = 0
    CAPTURE = 1
    MASKING = 2
    SPATIAL = 3
    GEOMETRY = 4
    EXPORT = 5


ErrorScope = Literal["command", "run", "backend"]


@dataclass(frozen=True)
class RunPipelineCommand:
    run_name: str
    input: str
    minimum_frames: int
    quality: str
    extra_fields: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunPipelineCommand:
        if data.get("type") != "run_pipeline":
            raise ValueError("Command type must be 'run_pipeline'")

        required = ("run_name", "input", "minimum_frames", "quality")
        missing = [f for f in required if f not in data]
        if missing:
            raise ValueError(f"missing required field: {missing[0]}")

        run_name = data["run_name"]
        if not isinstance(run_name, str) or not SAFE_RUN_NAME.fullmatch(run_name):
            raise ValueError("run_name must be a safe, non-empty directory name")
        if run_name.endswith((".", " ")):
            raise ValueError("run_name must not end with a period or space")
        if WINDOWS_RESERVED_RUN_NAME.fullmatch(run_name):
            raise ValueError("run_name must not be a reserved Windows device name")

        input_path = data["input"]
        if not isinstance(input_path, str) or not input_path.strip():
            raise ValueError("input must be a non-empty string")

        min_frames = data["minimum_frames"]
        if isinstance(min_frames, bool) or not isinstance(min_frames, int) or min_frames <= 0:
            raise ValueError("minimum_frames must be a positive integer")

        quality = data["quality"]
        if not isinstance(quality, str) or quality not in QUALITY_PRESETS:
            raise ValueError("quality must be fast, medium, or detailed")

        extras = {
            k: v
            for k, v in data.items()
            if k not in ("type", "run_name", "input", "minimum_frames", "quality")
        }
        return cls(
            run_name=run_name,
            input=input_path,
            minimum_frames=min_frames,
            quality=quality,
            extra_fields=extras,
        )


@dataclass(frozen=True)
class SelectionCommand:
    request_id: str
    choice: int | Literal["skip"]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SelectionCommand:
        if data.get("type") != "selection":
            raise ValueError("Command type must be 'selection'")

        if "request_id" not in data:
            raise ValueError("Target selection commands require request_id")

        request_id = data["request_id"]
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("request_id must be a non-empty string")

        choice = data.get("choice")
        if isinstance(choice, bool):
            raise ValueError("choice must be an index or 'skip'")

        if isinstance(choice, int):
            if choice < 0:
                raise ValueError("choice index cannot be negative")
            normalized_choice: int | Literal["skip"] = choice
        elif choice == "skip":
            normalized_choice = "skip"
        else:
            raise ValueError("choice must be an index or 'skip'")

        return cls(request_id=request_id, choice=normalized_choice)


@dataclass(frozen=True)
class CancelPipelineCommand:
    run_name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CancelPipelineCommand:
        if data.get("type") != "cancel_pipeline":
            raise ValueError("Command type must be 'cancel_pipeline'")

        run_name = data.get("run_name")
        if not isinstance(run_name, str) or not run_name:
            raise ValueError("cancel_pipeline must identify the active run")

        return cls(run_name=run_name)


# Event Constructors
def make_backend_ready() -> dict[str, Any]:
    return {"type": "backend_ready", "protocol_version": PROTOCOL_VERSION}


def make_log(text: str) -> dict[str, Any]:
    return {"type": "log", "text": text}


def make_workspace_ready(run_name: str, workspace: str) -> dict[str, Any]:
    return {"type": "workspace_ready", "run_name": run_name, "workspace": workspace}


def make_phase_started(phase: int | Phase, label: str | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"type": "phase_started", "phase": int(phase)}
    if label is not None:
        msg["label"] = label
    return msg


def make_progress(
    phase: int | Phase,
    value: float,
    overall_value: float,
    label: str | None = None,
) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "type": "progress",
        "phase": int(phase),
        "value": round(float(value), 4),
        "overall_value": round(float(overall_value), 4),
    }
    if label is not None:
        msg["label"] = label
    return msg


def make_action_required(
    request_id: str,
    action: str,
    phase: int | Phase,
    frame: str,
    preview: str,
    count: int,
) -> dict[str, Any]:
    return {
        "type": "action_required",
        "request_id": request_id,
        "action": action,
        "phase": int(phase),
        "frame": frame,
        "preview": preview,
        "count": count,
    }


def make_phase_completed(phase: int | Phase) -> dict[str, Any]:
    return {"type": "phase_completed", "phase": int(phase)}


def make_done(run_name: str, workspace: str, output: str) -> dict[str, Any]:
    return {
        "type": "done",
        "run_name": run_name,
        "workspace": workspace,
        "output": output,
    }


def make_cancelled(run_name: str) -> dict[str, Any]:
    return {"type": "cancelled", "run_name": run_name}


def make_error(
    scope: ErrorScope,
    code: str,
    text: str,
    *,
    run_name: str | None = None,
    phase: int | Phase | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "type": "error",
        "scope": scope,
        "code": code,
        "text": text,
    }
    if run_name is not None:
        msg["run_name"] = run_name
    if phase is not None:
        msg["phase"] = int(phase)
    if request_id is not None:
        msg["request_id"] = request_id
    return msg
