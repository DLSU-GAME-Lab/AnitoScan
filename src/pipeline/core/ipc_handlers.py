import json
import sys
import threading
import time
from typing import Optional, Tuple

import ipc
from log import get_run_id, log_error, log_event, log_info, set_ipc_mode, set_run_id


class PipelineCancelled(Exception):
    """Raised when the editor cancels the active pipeline run."""


_STATE_LOCK = threading.Lock()
_ACTIVE_SESSION = None


class _Session:
    def __init__(self, run_id):
        self.run_id = run_id
        self.cancel_event = threading.Event()
        self.selection_event = threading.Event()
        self.selection: Optional[int] = None
        self.awaiting_selection = False
        self.worker: Optional[threading.Thread] = None


def _diagnostic(message):
    print(f"[ipc] {message}", file=sys.stderr, flush=True)


def _active_session():
    with _STATE_LOCK:
        return _ACTIVE_SESSION



def await_ipc_selection(request: dict) -> Tuple[Optional[int], float]:
    """Request an editor selection and wait without reading protocol stdin."""
    session = _active_session()
    if session is None or get_run_id() != session.run_id:
        raise RuntimeError("selection requested without an active IPC run")

    try:
        frame = request["frame_name"]
        preview_path = request["preview_path"]
        candidate_count = request["total_candidates"]
    except KeyError as error:
        raise ValueError(f"selection request missing {error.args[0]}") from error

    with _STATE_LOCK:
        if session.awaiting_selection:
            raise RuntimeError("a selection request is already pending")
        session.selection = None
        session.selection_event.clear()
        session.awaiting_selection = True

    started = time.perf_counter()
    log_event("selection_required", {
        "frame": frame,
        "preview_path": preview_path,
        "candidate_count": candidate_count,
    })
    log_info(f"Opened {frame} preview: {preview_path}")

    try:
        while not session.selection_event.wait(0.1):
            if session.cancel_event.is_set():
                raise PipelineCancelled("pipeline run cancelled")
        if session.cancel_event.is_set():
            raise PipelineCancelled("pipeline run cancelled")
        return session.selection, time.perf_counter() - started
    finally:
        with _STATE_LOCK:
            session.awaiting_selection = False
            session.selection_event.clear()


def _run_worker(session, callback, args):
    global _ACTIVE_SESSION
    set_run_id(session.run_id)
    try:
        output_path = callback(
            args,
            ipc_mode=True,
            cancel_event=session.cancel_event,
        )
        if session.cancel_event.is_set():
            raise PipelineCancelled("pipeline run cancelled")
        ipc.send({
            "type": "run_completed",
            "run_id": session.run_id,
            "output_model_path": str(output_path),
        })
    except PipelineCancelled:
        ipc.send({"type": "run_cancelled", "run_id": session.run_id})
    except Exception as error:
        ipc.send({
            "type": "run_failed",
            "run_id": session.run_id,
            "message": str(error),
        })
        log_error(f"run {session.run_id} failed: {error}")
    finally:
        set_run_id(None)
        with _STATE_LOCK:
            if _ACTIVE_SESSION is session:
                _ACTIVE_SESSION = None


def _start_run(cmd, callback):
    global _ACTIVE_SESSION
    run_id = cmd.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        _diagnostic("start_run requires a non-empty string run_id")
        return
    if not isinstance(cmd.get("name"), str) or not cmd["name"].strip():
        _diagnostic("start_run requires a non-empty name")
        return
    args = dict(cmd)
    args.pop("action", None)

    with _STATE_LOCK:
        if _ACTIVE_SESSION is not None:
            _diagnostic("start_run rejected: a run is already active")
            return
        session = _Session(run_id)
        _ACTIVE_SESSION = session
        session.worker = threading.Thread(
            target=_run_worker,
            args=(session, callback, args),
            name=f"pipeline-{run_id}",
            daemon=False,
        )
        session.worker.start()


def _submit_selection(cmd):
    session = _active_session()
    if session is None:
        _diagnostic("submit_selection received without an active run")
        return
    if cmd.get("run_id") != session.run_id:
        _diagnostic("submit_selection run_id does not match the active run")
        return
    with _STATE_LOCK:
        if not session.awaiting_selection:
            _diagnostic("submit_selection received with no pending selection")
            return
        choice = cmd.get("choice")
        if choice is not None and (not isinstance(choice, int) or isinstance(choice, bool)):
            _diagnostic("submit_selection choice must be an integer or null")
            return
        session.selection = choice
        session.selection_event.set()



def _cancel_run(cmd):
    session = _active_session()
    if session is None:
        _diagnostic("cancel_run received without an active run")
        return
    if cmd.get("run_id") != session.run_id:
        _diagnostic("cancel_run run_id does not match the active run")
        return
    session.cancel_event.set()
    session.selection_event.set()


def listen_for_ipc_commands(run_pipeline_callback):
    """Process editor commands while at most one pipeline worker runs."""
    set_ipc_mode(True)
    ipc.send({"type": "backend_ready"})

    try:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                cmd = json.loads(line)
            except json.JSONDecodeError as error:
                _diagnostic(f"malformed JSON: {error}")
                continue
            if not isinstance(cmd, dict) or not isinstance(cmd.get("action"), str):
                _diagnostic("command must be an object with a string action")
                continue

            action = cmd["action"]
            if action == "start_run":
                _start_run(cmd, run_pipeline_callback)
            elif action == "submit_selection":
                _submit_selection(cmd)
            elif action == "cancel_run":
                _cancel_run(cmd)
            else:
                _diagnostic(f"unknown command action: {action}")
    finally:
        session = _active_session()
        if session is not None:
            session.cancel_event.set()
            session.selection_event.set()
            if session.worker is not None:
                session.worker.join()
