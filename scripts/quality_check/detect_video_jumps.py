import argparse
import json
import os
from pathlib import Path
from typing import Iterable, List, Tuple

from robocoin_dataset.quality_check.jump_frame_detector import (
    detect_max_jump_after_stable,
)


def iter_video_files(root: Path, exts: Tuple[str, ...]) -> Iterable[Path]:
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if name.lower().endswith(exts):
                yield Path(dirpath) / name


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recursively scan videos and report paths with large frame jumps."
    )
    parser.add_argument(
        "path",
        type=str,
        help="Root directory or a single video file to scan.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="outputs/jump_frame_report.json",
        help="Path to write JSON report. Default: outputs/jump_frame_report.json",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=10,
        help="Max jump distance threshold to consider a video problematic. Default: 10",
    )
    parser.add_argument(
        "--hash-size",
        type=int,
        default=16,
        help="Perceptual hash size. Larger is slower but more precise. Default: 16",
    )
    parser.add_argument(
        "--stable-threshold",
        type=int,
        default=2,
        help="Distance threshold to treat adjacent keyframes as stable. Default: 2",
    )
    parser.add_argument(
        "--min-stable-frames",
        type=int,
        default=10,
        help="Minimum count of consecutive stable distances before a jump. Default: 10",
    )
    parser.add_argument(
        "--exts",
        type=str,
        default=".mp4,.mov,.avi,.mkv",
        help="Comma-separated video extensions to scan. Default: .mp4,.mov,.avi,.mkv",
    )

    args = parser.parse_args()
    root_path = Path(args.path)
    exts: Tuple[str, ...] = tuple(e.strip().lower() for e in args.exts.split(",") if e.strip())

    if not root_path.exists():
        raise SystemExit(f"Path not found: {root_path}")

    # Collect files
    if root_path.is_file() and root_path.suffix.lower() in exts:
        video_files: List[Path] = [root_path]
    elif root_path.is_dir():
        video_files = list(iter_video_files(root_path, exts))
    else:
        raise SystemExit("Input must be a directory or a supported video file.")

    problematic: List[str] = []
    results = {}

    for vf in video_files:
        try:
            max_jump = detect_max_jump_after_stable(
                str(vf),
                hash_size=args.hash_size,
                stable_distance_threshold=args.stable_threshold,
                min_stable_frames=args.min_stable_frames,
            )
            results[str(vf)] = max_jump
            if max_jump >= args.threshold:
                problematic.append(str(vf))
        except Exception as e:
            # Mark unreadable videos as problematic with error info
            results[str(vf)] = {"error": str(e)}
            problematic.append(str(vf))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "root": str(root_path),
        "threshold": args.threshold,
        "problematic_videos": problematic,
        "results": results,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Wrote report to: {out_path}")
    print(f"Problematic videos: {len(problematic)}")


if __name__ == "__main__":
    main()


