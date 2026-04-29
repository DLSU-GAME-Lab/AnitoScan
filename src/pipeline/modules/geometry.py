import argparse
import json
import shutil
import sys
import time
from pathlib import Path
import numpy as np
import cv2

from transforms import run_transform_generation
from surface import run_surface_reconstruction

# =====================================================================
# DIRECTORY RESOLUTION
# =====================================================================
MODULE_PATH = Path(__file__).resolve()  # /src/pipeline/modules/geometry.py
PROJECT_ROOT = MODULE_PATH.parent.parent.parent.parent

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True, help="Path to project manifest.json")
    parser.add_argument("--force", action="store_true", help="Overwrite existing geometry data")
    
    args = parser.parse_args()
    run_transform_generation(args.manifest, force=args.force)
    run_surface_reconstruction(args.manifest, force=args.force)