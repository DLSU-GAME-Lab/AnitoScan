import argparse
import sys
from pathlib import Path


def resolve_geometry_presets(quality: str) -> tuple[int, int, int]:
    """Translates high-level quality flags to 2DGS iteration counts."""
    if quality == "fast":
        return 7000, 5000, 1000
    elif quality == "medium":
        return 15000, 7500, 3000
    else:
        return 30000, 15000, 3000


def build_phase_cmd(phase_num: int, parent_module_path: Path, manifest_path: Path, args: dict, ipc_mode: bool = False) -> list:
    """Builds the subprocess command array for CLI execution of a phase module."""
    module_names = {
        1: "capture.py",
        2: "remove_background.py",
        3: "spatial.py",
        4: "geometry.py",
        5: "export.py",
    }

    module_path = parent_module_path / module_names[phase_num]
    cmd = [sys.executable, str(module_path), "--manifest", str(manifest_path)]

    if phase_num == 1:
        if args.get("force"): cmd.append("--force")
        if args.get("image"): cmd.append("--image")
        if args.get("video"): cmd.append("--video")

    elif phase_num == 2:
        cmd.extend([
            "--iou_threshold", str(args.get("iou_threshold", 0.50)),
            "--drift_limit", str(args.get("drift_limit", 200)),
            "--yoloe_model_size", str(args.get("yoloe_model_size", "s")),
        ])
        if args.get("force"): cmd.append("--force")

    elif phase_num == 3:
        if args.get("force"): cmd.append("--force")

    elif phase_num == 4:
        quality = args.get("quality", "fast")
        train_iters, densify, opacity = resolve_geometry_presets(quality)
        cmd.extend([
            "--train_iterations", str(train_iters),
            "--densify_until_iter", str(densify),
            "--opacity_reset_interval", str(opacity),
        ])
        if args.get("force"): cmd.append("--force")

    elif phase_num == 5:
        if args.get("force"): cmd.append("--force")

    if ipc_mode:
        cmd.append("--ipc")

    return cmd


def parse_cli_args():
    """Parses standard command line arguments."""
    parser = argparse.ArgumentParser(description="3D Reconstruction Pipeline Entry Point")
    parser.add_argument("--name", type=str, required=True, help="Unique name for this reconstruction run")
    parser.add_argument("--input", type=str, required=True, help="Path to folder or a specific media file")
    parser.add_argument("--minimum_frames", type=int, default=45, help="Minimum target frame count required across the video duration for stable COLMAP parsing")
    parser.add_argument("--mode", type=str, choices=["disk", "pipe"], default="disk")
    parser.add_argument("-f", "--force", action="store_true")
    parser.add_argument("--image", action="store_true", help="Force image directory mode")
    parser.add_argument("--video", action="store_true", help="Force video file mode")
    parser.add_argument("--iou_threshold", type=float, default=0.50)
    parser.add_argument("--drift_limit", type=int, default=200)
    parser.add_argument("--yoloe_model_size", type=str, choices=["n", "s", "m", "l", "x"], default="s")
    parser.add_argument("--quality", type=str, choices=["fast", "medium", "detailed"], default="fast", help="Quality preset for 2DGS generation")

    return parser.parse_args()
