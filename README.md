# AnitoScan
**A 6-Phase Automated 3D Reconstruction Pipeline**

AnitoScan is a hybrid 3D reconstruction system designed for the DLSU GAME Lab.

## Getting Started
1. Run `src/pipeline/setup_debug_python_venv.sh` to initialize the environment.
2. Go to `"vendor\mast3r\dust3r\croco\models\curope"`

## If in windows visual studio 2026 workspace mode open x64 visual studio command prompt
2.1. Run `$env:DISTUTILS_USE_SDK=1`
2.2. Run `python setup.py build_ext --inplace`

3. Go to `vendor\NeuS2`

## If in windows
4.1. Run `cmake -B build -DCMAKE_POLICY_VERSION_MINIMUM="3.5.0"`
4.2. Run `cmake --build build --config RelWithDebInfo -j`

## Running the tool
1. Place video input in `data/input/`.
2. Execute the pipeline via:
   `./src/pipeline/.venv/bin/python src/pipeline/core/pipeline.py --name <run_name> --input <file> --fps 10`
