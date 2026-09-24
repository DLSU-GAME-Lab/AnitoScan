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
   If it does not exist, create the folder in the project root.
2. Execute the pipeline. Values passed to `--input` are relative to `data/input/`:

```powershell
uv run src\pipeline\core\pipeline.py --name <run_name> --input <file_or_dir> --minimum_frames <target_count>
```

Example Command:
```
uv run src\pipeline\core\pipeline.py --name test_scan --input sample_video.mp4 --minimum_frames 100
```

## Running the editor
### Through Visual Studio
1. Open the project folder in Visual Studio.
2. Build Tab -> `Build All`
3. After building, the `.exe` file should be in `out > build > debug > bin`.

The editor uses the dummy backend by default. Launch it from the project root with one of these commands:

```powershell
# Default (dummy backend)
.\out\build\debug\bin\AnitoScan.exe

# Explicit dummy backend
.\out\build\debug\bin\AnitoScan.exe --backend dummy

# Real pipeline backend using IPC
.\out\build\debug\bin\AnitoScan.exe --backend pipeline
```

### Mask selection

When masking needs input, choose a numbered candidate, click **Draw custom box** and drag around the subject, or click **Skip**. After drawing, click **Use custom box** to submit; drag again to replace the box, **Clear** to remove it, or **Exit drawing mode** to return to the normal preview. The hover magnifier is disabled while drawing.

Manual selection is also available when no candidates are detected. Those frames now wait for a custom box or Skip instead of being skipped automatically. Skip keeps the existing behavior: a transparent output frame, followed by a fresh selection on the next readable frame.

Boxes are sent as `[x1, y1, x2, y2]` in original-image pixels, with the origin at the top-left. The editor accounts for preview scaling and padding; no coordinate conversion is required from the user. A custom box prompts SAM using the same 8% padding and subsequent tracking as an automatic candidate—it is not a rectangular final mask.

The editor and backend must use the same selection protocol: requests include source dimensions and a selection ID, and responses echo the run/selection IDs with an integer candidate, `null` for Skip, or `{"bbox": [x1, y1, x2, y2]}`. Rejected selections leave the prompt available for retry. The dummy backend exercises selection delivery without running segmentation; use `--backend pipeline` to validate actual masks. The standalone OpenCV CLI still supports candidate/Skip input, not mouse-drawn boxes.

### Exporting a prepared model

During a new run, **Phase 5** prepares the mesh and then waits at the **Export asset** panel. Choose OBJ or GLB, enter an absolute destination folder and an asset name, then click **Export**. OBJ is selected by default, but nothing is delivered until you explicitly click Export. The run opens the post-export viewer only after export succeeds; failures stay in Phase 5 for retry. Cancelling before export leaves the run incomplete.

The post-export screen and reopened completed runs are viewer-only: they show the selected output's **OBJ/GLB format**, with no export controls. Existing model-variant buttons select already saved outputs, not a new export format. Phase history never exposes the export panel.

- **OBJ is the default.** The exporter copies the selected OBJ together with its referenced MTL files and textures, preserving their internal filenames and relative references.
- **GLB** converts the prepared OBJ into a single `.glb` with embedded textures using `trimesh`. The export uses non-metallic, fully rough defaults for converted OBJ materials; it does not reconstruct additional PBR maps.
- **FBX is planned to be implemented.**

Each export creates a new `destination/asset_name/` folder. Missing destination parents are created. Existing asset folders are never overwritten: choose another name or destination to retry. Files are staged before delivery, and failed exports clean up their temporary output. An export error does not remove the prepared assets or advance the run to completion.

The viewer loads exported OBJs directly. For GLB, the backend reads the exported GLB and builds a cached OBJ/MTL/texture preview in the run workspace for the existing renderer; the format label and saved output path still identify the actual GLB. Exporting does not rerun reconstruction, UV generation, or texture baking.

Successful exports are recorded in the run manifest with their actual format, output path, and preview path, so run history can restore OBJ and GLB even when delivered outside the project. New runs with only a prepared internal OBJ are not treated as completed exports. Legacy directory discovery recognizes both extensions; a legacy GLB without a recorded preview cache is listed but displays “Preview unavailable” rather than loading it as OBJ. Geometry is not automatically centered, reoriented, or calibrated to a real-world scale; validate orientation, units, UVs, normals, and appearance in the engine importer.

Export formats are advertised by the backend. The lightweight dummy launcher uses `uv run --no-project` and supports both OBJ and GLB without third-party dependencies. Its GLB exporter writes a valid, untextured cube fixture and matching cached preview; it exercises the same validation, staging, error handling, completion, and history recording as the real exporter. It does not convert real scans or validate textured GLB conversion. The real pipeline backend still requires `trimesh` for GLB export. Restart the editor after changing backend capabilities so the format list is refreshed. Phase 5 shows export progress or a recoverable error. Cancellation and phase navigation are disabled while an export is running. Successful export automatically advances to the viewer.

## BM-5: Held-out reconstruction quality (PSNR/SSIM)

BM-5 is opt-in. In the GUI's **Advanced settings**, enable **Evaluate reconstruction quality (BM-5)** and choose **Held-out frames (%)** (default 20%, allowed 10–50%). Use the same 20% split and quality preset across the paper's figurines. No export-screen controls or separate results screen are required; progress and summary paths appear in the Phase 3/4 logs.

The CLI uses the same manifest settings and phase implementations:

```sh
uv run src/pipeline/core/pipeline.py --name Groot --input groot.mp4 --quality medium --evaluate_quality --test_fraction 0.20
```

Omit `--evaluate_quality` for the existing all-frame reconstruction behavior. Settings are preserved in `manifest.json`; older manifests default to evaluation disabled and a test fraction of 0.20.

### Protocol

1. Phase 3 chooses `floor(N * test_fraction)` evenly spaced test indices over sorted extracted-frame filenames (`linspace` including endpoints when there is more than one test frame). For 321 frames at 20%, this is 257 training / 64 test. The exact filenames are saved before eligibility filtering. Missing/invalid/fully transparent masks are recorded as exclusions; membership is never reshuffled to replace difficult test frames.
2. Only eligible training images enter COLMAP reconstruction and Gaussian training. Both train and test images use the same existing masked-to-white-background preparation.
3. Test views are localized using SIFT matches and robust 2D–3D absolute pose estimation against the frozen training map. Their intrinsics stay fixed to the shared training PINHOLE camera. Test views never enter bundle adjustment, triangulation, Gaussian initialization, or training losses.
4. Phase 4 renders the actual final saved 2DGS checkpoint at held-out poses, without gradients. It uses the vendor camera loader's training-resolution convention, not the exported OBJ/GLB mesh. The vendor's automatic train/test split and scheduled training-time evaluations are disabled for BM-5.
5. RGB PSNR uses NumPy MSE on values in `[0,1]`. SSIM uses scikit-image with `data_range=1`, RGB channel axis, Gaussian weights, `sigma=1.5`, and population covariance. Reported values are arithmetic means of per-image scores, not PSNR derived from a pooled MSE.

These are **full-image, masked white-background** metrics. White background coverage can inflate scores; foreground coverage and representative render/reference pairs are saved for inspection. Scores are not directly comparable with literature that uses different backgrounds, resolution, splits, or camera-pose protocols. The adapter currently supports centered PINHOLE/SIMPLE_PINHOLE projection; unsupported off-center cameras are rejected rather than silently misprojected.

### Outputs and incomplete runs

Each real evaluation writes under `data/runs/<run>/evaluation/`:

- `split.json`: membership, exclusions, foreground coverage, and input fingerprint.
- `test_poses.json`: localized test cameras and per-frame localization failures.
- `summary.json`: measured means, requested/actual counts, quality, iteration, checkpoint/vendor identity, settings, and status.
- `per_frame.csv`: individual metrics and failure reasons.
- `previews/`: rendered/reference pairs for every successfully evaluated test frame, with no preview limit (metrics are computed before PNG quantization).

Phase 4 also appends the summary metrics and paths to `logs/benchmark.jsonl`. All requested test frames must be evaluated for a complete result. Partial evaluations retain their diagnostics but stop Phase 4 instead of silently dropping failed views. An exact image match has infinite PSNR: per-frame CSV uses `inf`, and strict JSON stores a null mean with an explicit explanation. No arbitrary PSNR cap is applied.

BM-5 refuses all-frame/unmarked or mismatched spatial/checkpoint caches. Changing evaluation settings, quality, inputs, or relevant training/vendor data requires a new run or an explicit `--force` rebuild. Old scores are invalidated before a new attempt; a failed rerun is not reported using previous scores.

To rerun only evaluation on a validated BM-5 checkpoint, without retraining:

```sh
uv run src/pipeline/modules/evaluate_quality.py --manifest data/runs/Groot/manifest.json
```

The final recorded checkpoint is selected by default; `--iteration` can select another recorded checkpoint. Keep the final checkpoint convention consistent for the paper.

Build Table 4 from explicitly selected summaries:

```sh
uv run --no-project python src/pipeline/core/summarize_quality.py data/runs/Groot/evaluation/summary.json data/runs/Bowser/evaluation/summary.json data/runs/Yoshi/evaluation/summary.json data/runs/DK/evaluation/summary.json data/runs/Link/evaluation/summary.json --output data/bm5_table.csv
```

The CSV columns are `Figurine`, `Frames (train/test)`, `PSNR (dB)`, `SSIM`, and `Quality Preset`. The figurine label uses the run name. Counts are actual registered training/evaluated test frames; requested counts remain in each summary. The summarizer rejects mocked, failed, incomplete, duplicate figurine/preset results, and incompatible metric protocols instead of mixing them into a paper table.

### Requirements and dummy mode

Real BM-5 requires a populated standard `vendor/2d-gaussian-splatting` checkout, its CUDA extensions, CUDA-capable PyTorch, and PyCOLMAP 4.0.4-or-newer frozen-map APIs. NumPy and scikit-image are already project dependencies. Phase 4 performs a vendor/API preflight before training and reports missing/incompatible code explicitly. The vendor directory was empty in the development checkout, so real end-to-end rendering has not been validated there; verify against the team's installed vendor revision and GPU environment. CPU/MPS substitution and alternate rendering backends are not provided.

The dummy backend accepts the same settings and simulates the evaluation stage. Its summary is explicitly `status: mocked`, with null PSNR/SSIM and no real evaluated-frame counts. It can exercise the GUI flow, but its results are never eligible for the paper table.

## 🛠 Maintenance & Development
*   **Adding Dependencies**: `uv add <package_name>`
*   **Updating Environment**: If the `uv.lock` or `pyproject.toml` changes (e.g., after a `git pull`), simply run `uv sync` to align your local environment.
*   **Python Version**: The project is pinned to **Python 3.12**. To change this, use `uv python pin <version>`.
