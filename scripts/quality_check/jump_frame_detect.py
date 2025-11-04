import json
from pathlib import Path

import tqdm

from robocoin_dataset.quality_check.jump_frame_detector import JumpFrameDetector
from robocoin_dataset.utils.logger import setup_logger

if __name__ == "__main__":
    root_paths = [
        "/mnt/nas/synnas/docker2/robocoin-datasets/",
        "/mnt/nas/synnas/docker/外部数据/蚂蚁外来数据",
    ]

    repo_dirs = []
    repo_dirs.extend(
        [
            repo_dir
            for repo_dir in Path("/mnt/nas/synnas/docker/外部数据/蚂蚁外来数据").glob("*/")
            if repo_dir.is_dir()
        ]
    )

    repo_dirs.extend(
        [
            repo_dir
            for repo_dir in Path("/mnt/nas/synnas/docker2/robocoin-datasets/").glob("*/")
            if repo_dir.is_dir() and "unitree" in str(repo_dir.name)
        ]
    )

    print(f"Found {len(repo_dirs)} dirs:")
    for repo_dir in repo_dirs:
        print(repo_dir)

    cam_high_dirs = []
    for repo_dir in repo_dirs:
        chunk_dirs = [
            d for d in (repo_dir / "videos").iterdir() if d.is_dir() and d.name.startswith("chunk-")
        ]
        print(chunk_dirs)

        for chunk_dir in chunk_dirs:
            cam_high_dirs.extend(
                [d for d in chunk_dir.iterdir() if d.is_dir() and "high" in d.name]
            )

    print(f"Fonding {len(cam_high_dirs)} cam_high_dirs:")
    for cam_high_dir in cam_high_dirs:
        print(cam_high_dir)

    with open("datas/jump_frame_detector_paths.txt", "w") as f:
        for cam_high_dir in cam_high_dirs:
            f.write(str(cam_high_dir))
            f.write("\n")
        pass
    logger = setup_logger(name="jump_frame_detector", log_dir=Path("logs"))

    results = {}
    for cam_high_dir in tqdm.tqdm(cam_high_dirs, desc="detect jump frames", unit="dir"):
        detector = JumpFrameDetector(cam_high_dir, logger=logger)
        results[str(cam_high_dir)] = detector.detect()

    with open("datas/jump_frame_results.json", "w") as f:
        json.dump(results, f)
