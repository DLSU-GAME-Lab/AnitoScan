"""Build the BM-5 paper table from explicitly selected, complete evaluation reports."""

import argparse
import csv
import json
import math
from pathlib import Path


COLUMNS = ("Figurine", "Frames (train/test)", "PSNR (dB)", "SSIM", "Quality Preset")


def read_result(path: Path) -> tuple[dict, str]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("benchmark") != "BM-5" or report.get("status") != "completed" or report.get("mock", False):
        raise ValueError(f"{path}: only completed, measured BM-5 reports can enter the paper table")
    if report.get("errors"):
        raise ValueError(f"{path}: report contains evaluation errors")
    train, test = report.get("train_frames"), report.get("test_frames")
    if type(train) is not int or type(test) is not int or min(train, test) <= 0:
        raise ValueError(f"{path}: missing actual train/test counts")
    if test != report.get("requested_test_frames"):
        raise ValueError(f"{path}: not every requested test frame was evaluated")
    name, quality = report.get("run_name"), report.get("quality")
    if not isinstance(name, str) or not name or quality not in {"fast", "medium", "detailed"}:
        raise ValueError(f"{path}: missing run name or quality preset")
    psnr, ssim = report.get("psnr_db"), report.get("ssim")
    details = report.get("details", {})
    if psnr is None and details.get("psnr_positive_infinity_frames") and details.get("psnr_null_reason"):
        psnr_text = "inf"
    elif isinstance(psnr, (int, float)) and not isinstance(psnr, bool) and math.isfinite(psnr):
        psnr_text = f"{psnr:.2f}"
    else:
        raise ValueError(f"{path}: missing/invalid PSNR")
    if not isinstance(ssim, (int, float)) or isinstance(ssim, bool) or not math.isfinite(ssim):
        raise ValueError(f"{path}: missing/invalid SSIM")
    settings = report["settings"]
    protocol = {key: settings[key] for key in (
        "test_fraction", "reference_protocol", "render_protocol", "background", "aggregation", "ssim",
    )}
    return {
        "Figurine": name,
        "Frames (train/test)": f"{train} / {test}",
        "PSNR (dB)": psnr_text,
        "SSIM": f"{ssim:.4f}",
        "Quality Preset": quality.title(),
    }, json.dumps(protocol, sort_keys=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summaries", nargs="+", type=Path, help="Explicit evaluation/summary.json files; mocked/incomplete runs are rejected")
    parser.add_argument("--output", required=True, type=Path, help="CSV table destination")
    args = parser.parse_args()
    if args.output.suffix.lower() != ".csv":
        parser.error("--output must be a .csv file")
    try:
        rows, identities, protocols = [], set(), set()
        for path in args.summaries:
            row, protocol = read_result(path)
            identity = (row["Figurine"], row["Quality Preset"])
            if identity in identities:
                raise ValueError(f"Duplicate figurine/preset: {identity}. Select only one report per result.")
            identities.add(identity)
            protocols.add(protocol)
            rows.append(row)
        if len(protocols) != 1:
            raise ValueError("Reports use different split/metric protocols; do not combine them in one comparison table")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(".csv.tmp")
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(args.output)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    print(f"Wrote {len(rows)} measured BM-5 results to {args.output}")
    if len({row["Figurine"] for row in rows}) < 5:
        print("BM-5 paper protocol recommends at least five distinct figurines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
