# AnitoScan
**An Automated 3D Reconstruction Pipeline**

AnitoScan is a hybrid 3D reconstruction system designed for the DLSU GAME Lab.

## Prerequisites

Before setting up the environment, ensure the following tools are installed on your system:

1. **Operating System**: Windows 10 / 11 (64-bit).
2. **NVIDIA CUDA Toolkit**: CUDA 12.4 installed and present in your system `PATH`
3. **Visual Studio**
   - Installed with the **Desktop development with C++** workload.
   - Requires the **x64 Native Tools Command Prompt for VS

3. **`uv` Package Manager**
   - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
4. C++ Build Tools:
   - CMake

## Getting Started

> [!IMPORTANT]  
> Because local C++/CUDA extensions are built from source via PyTorch and `setuptools`, you **must** perform installation steps inside the **x64 Native Tools Command Prompt for VS** (not standard PowerShell or CMD) to prevent 32-bit compilation mismatches and SDK environment re-activation errors.


### Step 1: Clone the Repository
Clone the project along with its submodules (e.g., `vendor/2d-gaussian-splatting/submodules/simple-knn`):

```cmd
git clone --recursive [https://github.com/your-org/AnitoScan.git](https://github.com/your-org/AnitoScan.git)
cd AnitoScan/ 
```


### Step 2: Open the 64-bit Developer Shell
1. Press the Windows Key.

2. Search for x64 Native Tools Command Prompt for VS.

3. Open it and navigate to your project directory:

```
cd <project_directory>\AnitoScan
```

### Step 3: Configure Environment & Install Dependencies
`uv` will automatically detect the `.python-version` file, download the correct Python interpreter, and sync all dependencies into a local virtual environment. This handles Python library packages as well as the 2D Gaussian Splatting (2DGS) backend engine requirements.

Run the following set of commands to configure the build environment, pin 64-bit Python, clear stale build caches, and compile all dependencies:

:: 1. Prevent PyTorch from attempting multiple MSVC environment activations
```
set DISTUTILS_USE_SDK=1
```

:: 2. Force uv to download and use a 64-bit Python 3.12 target
```
uv python pin 3.12-x86_64
```

:: 3. Resolve dependencies and compile submodules (simple-knn, CUDA extensions)
```
uv sync
```

**Update: pycolmap is now used in favor of MASt3R** -->

## Running the tool
### Through `UV`
Once the initial C++/CUDA compilation via uv sync is complete, you can run the pipeline command above from standard PowerShell, CMD, or VS Code terminals.


1. Place video input or image folders inside `data/input/`.
   If it does not exists, create the folders in the project root.
2. Execute the pipeline:

```powershell
uv run src\pipeline\core\pipeline.py --name <run_name> --input <file_or_dir> --minimum_frames <target_count>

```

Example Command:
```
uv run src\pipeline\core\pipeline.py --name test_scan --input data\input\sample_video.mp4 --minimum_frames 100
```

## Running the editor
### Through Visual Studio
1. Open the project folder in Visual Studio.
2. Build Tab -> `Build All`
3. After building, the `.exe` file should be in `out > build > debug > bin`.

## 🛠 Maintenance & Development
*   **Adding Dependencies**: `uv add <package_name>`
*   **Updating Environment**: If the `uv.lock` or `pyproject.toml` changes (e.g., after a `git pull`), simply run `uv sync` to align your local environment.
*   **Python Version**: The project is pinned to **Python 3.12**. To change this, use `uv python pin <version>`.
