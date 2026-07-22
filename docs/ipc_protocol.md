# IPC Protocol

This document is the authoritative communication contract between the AnitoScan editor and backend.

## Transport

The processes exchange newline-delimited UTF-8 JSON over the backend process's standard streams:

- The editor writes commands to backend standard input.
- The backend writes events to standard output.
- Each line contains exactly one complete JSON object.
- Writers flush each message immediately.
- Message order is preserved in each direction.

Backend standard output is reserved for protocol messages. Non-protocol diagnostics use standard error.

Every message contains a string `type` field. Unless a field is marked optional, it is required.

Receivers ignore unknown fields for forward compatibility. An unknown message type is reported through local diagnostics without crashing the receiver.

## Protocol version

The backend announces the protocol version in `backend_ready`. The editor sends no commands if that version is unsupported.

The version changes only when compatibility is broken, such as removing a field or changing its meaning. Adding an optional field does not require a new version.

Current target version:

```text
1
```

## Pipeline phases

| Value | Phase |
|---:|---|
| `0` | None |
| `1` | Capture |
| `2` | Masking |
| `3` | Spatial |
| `4` | Geometry |
| `5` | Export |

A numeric `phase` field is authoritative. Receivers do not offset it or derive phase state from labels or logs.

## Editor-to-backend messages

### `run_pipeline`

Requests a new pipeline run.

```json
{
  "type": "run_pipeline",
  "run_name": "example_run",
  "input": "data/input/example.mp4",
  "minimum_frames": 45,
  "quality": "fast"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | `run_pipeline` |
| `run_name` | string | Requested run name. |
| `input` | string | Input video or image collection path. |
| `minimum_frames` | integer | Minimum requested capture frame count. |
| `quality` | string | Pipeline quality preset. |

Additional pipeline settings may be added as fields defined by the serialized `PipelineConfig`. The backend validates and normalizes the complete request before accepting it.

Only one run may be active in a backend process.

### `selection`

Responds to a pending interactive action.

```json
{
  "type": "selection",
  "request_id": "mask-frame-001",
  "choice": 0
}
```

To skip:

```json
{
  "type": "selection",
  "request_id": "mask-frame-001",
  "choice": "skip"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | `selection` |
| `request_id` | string | ID from the corresponding `action_required`. |
| `choice` | integer or string | Zero-based candidate index or `skip`. |

An unknown request ID or invalid choice produces a command-scoped `error` and leaves the action pending.

### `cancel_pipeline`

Requests graceful cancellation of the active run.

```json
{
  "type": "cancel_pipeline",
  "run_name": "example_run"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | `cancel_pipeline` |
| `run_name` | string | Active run to cancel. |

Cancellation is asynchronous. It completes only when the backend sends `cancelled` or a terminal `error`.

## Backend-to-editor messages

### `backend_ready`

Sent once after backend initialization and before commands are accepted.

```json
{
  "type": "backend_ready",
  "protocol_version": 1
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | `backend_ready` |
| `protocol_version` | integer | Implemented protocol version. |

### `log`

Reports display-only diagnostic information.

```json
{
  "type": "log",
  "text": "Preparing capture phase"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | `log` |
| `text` | string | Human-readable entry. |

Logs may occur anywhere and never control lifecycle state.

### `workspace_ready`

Reports that the accepted run's workspace is available.

```json
{
  "type": "workspace_ready",
  "run_name": "example_run",
  "workspace": "data/runs/example_run"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | `workspace_ready` |
| `run_name` | string | Accepted run name. |
| `workspace` | string | Exact workspace path. |

### `phase_started`

Reports the start of a phase.

```json
{
  "type": "phase_started",
  "phase": 1,
  "label": "Capture"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | `phase_started` |
| `phase` | integer | Canonical phase value. |
| `label` | string, optional | Display-only phase label. |

### `progress`

Reports phase and overall pipeline progress.

```json
{
  "type": "progress",
  "phase": 1,
  "value": 0.5,
  "overall_value": 0.1,
  "label": "Extracting frames"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | `progress` |
| `phase` | integer | Canonical phase value. |
| `value` | number | Phase progress in `[0.0, 1.0]`. |
| `overall_value` | number | Overall progress in `[0.0, 1.0]`. |
| `label` | string, optional | Display-only status text. |

The backend owns both progress values. The editor does not calculate overall progress from phase count or weights.

### `action_required`

Pauses pipeline execution until the editor responds to an interactive request.

```json
{
  "type": "action_required",
  "request_id": "mask-frame-001",
  "action": "mask_selection",
  "phase": 2,
  "frame": "frame_001.png",
  "preview": "data/runs/example_run/02_masking/preview_001.png",
  "count": 3
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | `action_required` |
| `request_id` | string | Unique ID for the pending action. |
| `action` | string | Requested action kind. |
| `phase` | integer | Phase requesting input. |
| `frame` | string | Associated frame. |
| `preview` | string | Exact preview artifact path. |
| `count` | integer | Number of candidate choices. |

Only one interactive action may be pending. It remains pending until the backend accepts a matching response, the run advances, or the run terminates.

### `phase_completed`

Reports successful completion of a phase.

```json
{
  "type": "phase_completed",
  "phase": 1
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | `phase_completed` |
| `phase` | integer | Canonical phase value. |

Progress reaching `1.0` does not complete a phase by itself.

### `done`

Reports successful pipeline completion.

```json
{
  "type": "done",
  "run_name": "example_run",
  "workspace": "data/runs/example_run",
  "output": "data/output/example_run/example_run_fast.obj"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | `done` |
| `run_name` | string | Completed run name. |
| `workspace` | string | Exact workspace path. |
| `output` | string | Exact primary output path. |

### `cancelled`

Confirms graceful cancellation.

```json
{
  "type": "cancelled",
  "run_name": "example_run"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | `cancelled` |
| `run_name` | string | Cancelled run name. |

Partial workspace artifacts may remain available.

### `error`

Reports a command, run, or backend failure.

```json
{
  "type": "error",
  "scope": "run",
  "code": "input_not_found",
  "text": "Input source not found",
  "run_name": "example_run",
  "phase": 1
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | `error` |
| `scope` | string | `command`, `run`, or `backend`. |
| `code` | string | Stable machine-readable code. |
| `text` | string | Human-readable description. |
| `run_name` | string, optional | Related run. |
| `phase` | integer, optional | Related phase. |
| `request_id` | string, optional | Related interactive request. |

Error scope determines its lifecycle effect:

| Scope | Effect |
|---|---|
| `command` | Rejects one command without terminating an accepted run. |
| `run` | Terminates the active run as failed. |
| `backend` | Marks the backend unusable and terminates any active run. |

## Lifecycle sequencing

Successful run:

```text
backend_ready
  -> run_pipeline
  -> workspace_ready
  -> phase_started -> progress... -> phase_completed
  -> repeated for each phase
  -> done
```

Interactive action:

```text
action_required
  -> selection
  -> progress, phase_completed, another action_required, or error
```

Cancellation:

```text
cancel_pipeline
  -> cancelled or terminal error
```

Each accepted run emits exactly one terminal event:

- `done`
- `cancelled`
- a run- or backend-scoped `error`

## Protocol invariants

1. Lifecycle state changes only through explicit protocol events.
2. Labels and logs are display-only.
3. Numeric phase values require no conversion.
4. Backend-provided paths are opaque to the editor.
5. Interactive responses correlate through `request_id`.
6. The production and dummy backends implement the same protocol.
