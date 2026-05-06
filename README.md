# AnitoScan
**A 6-Phase Automated 3D Reconstruction Pipeline**

AnitoScan is a hybrid 3D reconstruction system designed for the DLSU GAME Lab.

## Prerequisites

Instead of manually managing Python versions, this project uses `uv` for reproducible toolchain management.

1. Install uv:
   - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. C++ Build Tools:
   - CMake

## Getting Started

### 1. Initialize the environment

`uv` will automatically detect the `.python-version` file, download the correct Python interpreter, and sync all dependencies into a local virtual environment.

```DOS
uv sync
```

### 2. Build C++ Extensions (CUROPE)
Navigate to the `mast3r` vendor directory to compile the hardware-accelerated extensions.

**If on Windows (x64 Visual Studio Command Prompt):**
```DOS
cd "vendor\mast3r\dust3r\croco\models\curope"

:: Replace the path below with your actual CUDA installation path
set CUDA_HOME=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1
set DISTUTILS_USE_SDK=1

uv run python setup.py build_ext --inplace
cd ../../../../../..
```

### 3. Build NeuS2 Engine
The neural surface reconstruction stage requires a C++ build via CMake.
```DOS
cd vendor\NeuS2
cmake -B build -DCMAKE_POLICY_VERSION_MINIMUM="3.5.0"
cmake --build build --config RelWithDebInfo -j
```

## Running the tool
1. Place video input in `data/input/`.
2. Execute the pipeline:
```powershell
uv run src\pipeline\core\pipeline.py --name <run_name> --input <file> --fps <target_fps>
```

## 🛠 Maintenance & Development
*   **Adding Dependencies**: `uv add <package_name>`
*   **Updating Environment**: If the `uv.lock` or `pyproject.toml` changes (e.g., after a `git pull`), simply run `uv sync` to align your local environment.
*   **Python Version**: The project is pinned to **Python 3.13**. To change this, use `uv python pin <version>`.
