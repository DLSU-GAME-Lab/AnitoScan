# Filesystem Layout

This document is the authoritative filesystem contract shared by the AnitoScan editor, backend, and pipeline modules.

Protocol path fields are defined in [`ipc_protocol.md`](ipc_protocol.md).

## Data root

```text
data/
  input/
  runs/
  output/
```

| Directory | Purpose |
|---|---|
| `data/input/` | Input videos and image collections. |
| `data/runs/` | Per-run workspaces and intermediate artifacts. |
| `data/output/` | Final models and supporting files. |

These are logical project-relative paths. The backend may report resolved absolute paths through IPC.

## Run names

A run name identifies one workspace and one output directory. It must:

- be non-empty;
- be safe as a single directory component;
- contain no path separators or traversal components;
- remain unchanged for the lifetime of the run.

For `example_run`:

```text
data/runs/example_run/
data/output/example_run/
```

The pipeline configuration validator enforces these rules before workspace creation.

## Run workspace

Each accepted run has this workspace:

```text
data/runs/<run_name>/
  manifest.json
  01_capture/
  02_masking/
  03_spatial/
  04_geometry/
```

The pipeline orchestrator creates the workspace and owns the manifest. After creation, the backend reports the workspace through IPC.

### Artifact ownership

| Path | Owner | Contents |
|---|---|---|
| `manifest.json` | Pipeline orchestrator | Run configuration, lifecycle state, and artifact records. |
| `01_capture/` | Capture module | Extracted and selected source frames. |
| `02_masking/` | Masking module | Masks, previews, and related artifacts. |
| `03_spatial/` | Spatial module | Camera, pose, and scene-initialization outputs. |
| `04_geometry/` | Geometry module | Reconstruction and geometry outputs. |

A phase may read declared outputs from earlier phases but writes only to its assigned location. The export phase writes final artifacts to `data/output/`; no `05_export/` workspace directory is required.

## Manifest

`manifest.json` records enough information to inspect and resume or diagnose a run:

- run identity and input;
- normalized pipeline configuration;
- phase and terminal state;
- generated artifact references;
- final output references when available.

`config.py` serializes the normalized configuration portion. The pipeline orchestrator creates and updates the complete manifest at defined lifecycle boundaries.

The full manifest schema is intentionally outside this filesystem contract.

## Final output

Each run writes final artifacts under:

```text
data/output/<run_name>/
```

The primary OBJ path is:

```text
data/output/<run_name>/<run_name>_<quality>.obj
```

Example:

```text
data/output/example_run/example_run_fast.obj
```

Supporting material, texture, metadata, or additional format files may reside beside the primary model. The backend reports the exact primary output path in `done`.

## Editor consumers

| Consumer | Artifact source |
|---|---|
| Capture screen | `01_capture/` |
| Masking screen | `02_masking/` |
| Interactive masking preview | Exact path from `action_required` |
| Results viewport | Exact path from `done` |

The editor reads pipeline artifacts but does not create, rename, move, or reorganize them. File existence alone does not determine pipeline lifecycle state.

## Path handling

Editor and backend code use platform-aware path APIs.

Paths sent through IPC:

- identify an exact backend-selected artifact;
- are opaque to the receiver;
- are not rebuilt with manual separator concatenation;
- may be absolute after backend resolution.

The logical layout is identical across platforms even when path separators and absolute path formats differ.

## Dummy backend

The dummy backend creates the same required layout as production and supplies representative artifacts needed by the editor:

- a valid manifest;
- readable capture and masking images;
- every preview referenced by an interactive request;
- a loadable primary OBJ and its required supporting files.

Dummy artifacts follow the same ownership and naming rules.

## Filesystem invariants

1. Every accepted run has one workspace and one output directory identified by run name.
2. Workspace artifacts and final outputs remain separate.
3. The pipeline orchestrator owns workspace and manifest lifecycle.
4. Each phase writes only to its assigned location.
5. IPC-provided artifact
 paths are authoritative to consumers.
6. Production and dummy backends satisfy the same filesystem contract.
