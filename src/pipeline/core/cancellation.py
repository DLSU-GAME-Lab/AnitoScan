class PipelineCancelled(Exception):
    """Raised when a pipeline run observes a cancellation request."""


def check_cancelled(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise PipelineCancelled("Pipeline cancelled")
