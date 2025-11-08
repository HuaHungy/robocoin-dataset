import argparse
import json
from pathlib import Path

import tqdm

if __name__ == "__main__":
    error_path = []
    total_episodes = 0
    total_time_seconds = 0.0
    parser = argparse.ArgumentParser(description="compute statistics")
    parser.add_argument("--data_root", type=str, default="")
    args = parser.parse_args()
    data_root = Path(args.data_root)
    # 处理路径下文件夹，添加tqdm进度条
    for folder in tqdm.tqdm(
        data_root.iterdir(),
        desc="processing folders",
        total=len(list(data_root.iterdir())),
        unit="folder",
    ):
        if not folder.is_dir():
            continue
        try:
            info_file_path = folder / "meta/info.json"
            if not info_file_path.exists():
                raise FileNotFoundError(f"info.json not found in {folder}")
            fps = 0
            with info_file_path.open("r") as f:
                info = json.load(f)
                # 这里可以添加对info的处理逻辑
                fps = info.get("fps", None)
            if fps is None:
                raise ValueError(f"FPS not found in {info_file_path}")
            
            episode_info_path = folder / "meta/episodes.jsonl"
            if not episode_info_path.exists():
                raise FileNotFoundError(f"episodes.jsonl not found in {folder}")
            # 获取总帧数
            with episode_info_path.open("r") as f: 
                for line in f:
                    total_episodes += 1
                    episode_info = json.loads(line)
                    total_time_seconds += episode_info.get("length", 0) * 1 / fps
        except Exception as e:
            error_path.append(str(folder))
            print(f"Error processing {folder}: {e}")
            continue
    print(f"Total episodes: {total_episodes}")
    print(f"Total time (seconds): {total_time_seconds}")
    with open("error_paths.txt", "w") as ef:
        for path in error_path:
            ef.write(f"{path}\n")
        
'''
Usage:
python scripts/statistics/recent_statistics.py --data_root /mnt/nas/synnas/docker2/robocoin-datasets
'''