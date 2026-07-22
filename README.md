# AnitoScan
**An Automated 3D Reconstruction Pipeline**

AnitoScan is a hybrid 3D reconstruction system designed for the DLSU GAME Lab.

## Prerequisites

AnitoScan uses `uv` to provision Python and CMake to build the C++ editor.

1. Install uv:
   - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Install CMake and a C++ toolchain.

A separate Python installation is not required. `uv` provisions the version pinned in `.python-version`.

## Platform support

- Windows supports the editor, dummy backend, and production reconstruction backend.
- macOS supports the editor and dummy backend only.
- Production reconstruction and 2DGS are Windows-only.

See [`docs/pipeline_architecture.md`](docs/pipeline_architecture.md#platform-support) for the authoritative support matrix.

## Editor and dummy backend

The dummy backend uses only the Python standard library. The editor launches it through an isolated uv environment that does not discover `pyproject.toml`, synchronize `.venv`, or install production dependencies.

No `uv sync` is required for editor and dummy-backend development.

### Backend selection

The editor accepts:

```text
--backend=production
--backend=dummy
```

Windows defaults to `production`; macOS defaults to `dummy`. Production mode is rejected outside Windows.

```powershell
# Explicit dummy mode on any supported editor platform
AnitoScan --backend=dummy
```

The dummy backend is launched through uv with project discovery disabled, so it does not synchronize or import production dependencies.

## Production reconstruction on Windows

Initialize the production environment from a Windows development shell:

```powershell
uv sync
```

This synchronizes the full reconstruction environment, including CUDA-bound 2DGS dependencies.

### Build C++ Extensions (CUROPE)

Navigate to the `mast3r` vendor directory to compile the hardware-accelerated extensions.

**From an x64 Visual Studio Command Prompt:**

```DOS
cd "vendor\mast3r\dust3r\croco\models\curope"

set CUDA_HOME=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4
set DISTUTILS_USE_SDK=1
$env:PLATFORM = "x64"

uv run python setup.py build_ext --inplace
cd ../../../../../..

```

**Update: pycolmap is now used in favor of MASt3R**

## Running the production pipeline

The production pipeline is supported on Windows only.

1. Place video input or image folders inside `data/input/`.
2. Execute the pipeline:

```powershell
uv run src\pipeline\core\pipeline.py --name <run_name> --input <file_or_dir> --minimum_frames <target_count>

```

## 🛠 Maintenance & Development
*   **Adding Dependencies**: `uv add <package_name>`
*   **Updating Environment**: Run `uv sync` only for the Windows production environment when `uv.lock` or `pyproject.toml` changes. Editor and dummy-backend-only development does not require project synchronization.
*   **Python Version**: The project is pinned to **Python 3.12**. To change this, use `uv python pin <version>`.
