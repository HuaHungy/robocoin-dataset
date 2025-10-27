import cv2
from pathlib import Path
from typing import List
from .episode_frames_collector import EpisodeFramesCollector


class EpisodeFramesCollectorGalbo(EpisodeFramesCollector):
    def __init__(self, dataset_info_file: Path, dataset_dir: Path) -> None:
        super().__init__(dataset_info_file, dataset_dir)
        

    def _collect_episode_frames_num(self) -> List[int]:
        """
        只要文件夹里出现 camera_right_wrist.mp4 就：
          1. 用 cv2 计算总帧数；
          2. 把该文件夹标记为已处理（裁枝，不再递归子目录）。
        返回各 episode 的帧数列表。
        """
        episode_frames_num: List[int] = []
        # 已处理的文件夹集合，防止重复
        seen_dirs = set()

        for mp4_path in self.dataset_dir.rglob("camera_right_wrist.mp4"):
            parent = mp4_path.parent
            if parent in seen_dirs:          # 同一文件夹多个 mp4 只算一次
                continue
            seen_dirs.add(parent)

            # 读帧数
            cap = cv2.VideoCapture(str(mp4_path))
            if not cap.isOpened():
                print(f"  WARN 无法打开 {mp4_path}")
                continue
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()

            episode_frames_num.append(total_frames)
            print(f" {mp4_path} → frames = {total_frames}")

        return episode_frames_num