import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BENCHMARK_INVOCATION_ENV = "ANITOSCAN_BENCHMARK_INVOCATION_ID"

PHASE_NAMES = {
    1: "capture",
    2: "masking",
    3: "spatial",
    4: "geometry",
    5: "export",
}


def create_invocation_id() -> str:
    """Creates a filesystem/log friendly timestamp ID for one pipeline invocation."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")


def get_invocation_id() -> str:
    """Returns the current benchmark invocation ID, creating one for direct phase runs."""
    invocation_id = os.environ.get(BENCHMARK_INVOCATION_ENV)
    if invocation_id:
        return invocation_id

    invocation_id = create_invocation_id()
    os.environ[BENCHMARK_INVOCATION_ENV] = invocation_id
    return invocation_id


def append_failed_phase_benchmark(
    manifest: dict[str, Any],
    phase: int,
    *,
    start_time: float,
    settings: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    paths: dict[str, Any] | None = None,
    error: BaseException,
) -> None:
    append_phase_benchmark(
        manifest,
        phase,
        status="failed",
        skipped=False,
        duration_seconds=_elapsed_since(start_time),
        settings=settings,
        metrics=metrics,
        paths=paths,
        error=f"{type(error).__name__}: {error}",
    )


def append_phase_benchmark(
    manifest: dict[str, Any],
    phase: int,
    *,
    status: str,
    skipped: bool,
    duration_seconds: float,
    settings: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    paths: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Appends one phase benchmark record to data/runs/<run>/logs/benchmark.jsonl.

    Benchmarking should never make the pipeline fail, so write errors are reported only.
    """
    try:
        run_root = Path(manifest["paths"]["run_root"])
        log_dir = run_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        record = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "invocation_id": get_invocation_id(),
            "run_name": manifest.get("run_name"),
            "phase": phase,
            "phase_name": PHASE_NAMES.get(phase, f"phase_{phase}"),
            "status": status,
            "skipped": skipped,
            "duration_seconds": round(duration_seconds, 3),
            "settings": _sanitize(settings or {}),
            "metrics": _sanitize(metrics or {}),
            "paths": _sanitize(paths or {}),
        }

        if error:
            record["error"] = error

        benchmark_path = log_dir / "benchmark.jsonl"
        with benchmark_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, sort_keys=True) + "\n")
    except (KeyError, OSError, TypeError, ValueError) as benchmark_error:
        print(
            f"[benchmark] Failed to append phase benchmark: {benchmark_error}",
            file=sys.stderr,
        )


def _elapsed_since(start_time: float) -> float:
    try:
        import time

        return time.perf_counter() - start_time
    except (TypeError, ValueError):
        return 0.0


def _sanitize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_sanitize(item) for item in value]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except (TypeError, ValueError):
            return str(value)

    return str(value)
