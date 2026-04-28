# AnitoScan
**A 6-Phase Automated 3D Reconstruction Pipeline**

AnitoScan is a hybrid 3D reconstruction system designed for the DLSU GAME Lab.

## Getting Started
1. Run `src/pipeline/setup_debug_python_venv.sh` to initialize the environment.
2. Place video input in `data/input/`.
3. Execute the pipeline via:
   `./src/pipeline/.venv/bin/python src/pipeline/core/pipeline.py --name <run_name> --input <file> --fps 10`
