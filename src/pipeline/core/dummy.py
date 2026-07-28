import sys
from pathlib import Path

core_path = str(Path(__file__).resolve().parent.parent / "core")
sys.path.insert(0, core_path)

from ipc_handlers import listen_for_ipc_commands
from log import log_info


def mock_pipeline_runner(args: dict, ipc_mode: bool = False):
    """A mock pipeline runner that mimics the signature of pipeline.py's run_pipeline_with_args."""
    run_name = args.get("name", "unnamed")
    log_info(f"Mock pipeline starting for: {run_name}")

    # Simulate work
    import time
    for i in range(1, 6):
        time.sleep(2)
        log_info(f"Mock completed Phase {i}")

    log_info(f"Mock pipeline complete for {run_name}")

if __name__ == "__main__":
    listen_for_ipc_commands(mock_pipeline_runner)
