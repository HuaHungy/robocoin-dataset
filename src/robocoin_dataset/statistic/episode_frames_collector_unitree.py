import json
from pathlib import Path

from .episode_frames_collector import EpisodeFramesCollector


class EpisodeFramesCollectorUnitree(EpisodeFramesCollector):
    def __init__(self, dataset_info_file: Path, dataset_dir: Path) -> None:
        super().__init__(dataset_info_file, dataset_dir)

    def _collect_episode_frames_num(self) -> list[int]:
        """
        Collect the number of frames in each episode by finding the max 'idx' in data.json.
        """
        data_files = self.dataset_dir.glob("**/data.json")
        episode_frames_num = []
        for data_file in data_files:
            try:
                with open(data_file, "r") as file:
                    data = json.load(file)  
                    entries = data.get("data", [])  
                    if not entries:
                        episode_frame_num = 0
                    else:
                        idxs = [item["idx"] for item in entries if "idx" in item]
                        episode_frame_num = max(idxs) if idxs else 0
                    episode_frames_num.append(episode_frame_num)
                    print(f" {data_file} → max idx = {episode_frame_num}")
            except Exception as e:
                print(f" Error reading {data_file}: {e}")
                continue
        return episode_frames_num