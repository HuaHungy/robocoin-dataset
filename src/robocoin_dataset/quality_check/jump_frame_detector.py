import logging
import random
from pathlib import Path

import av
import imagehash
import matplotlib.pyplot as plt
import numpy as np
import tqdm


def detect_frame_dist(
    video_path: str,
    hash_size: int = 16,
) -> None:
    try:
        container = av.open(video_path)
        stream = container.streams.video[0]
        stream.thread_count = 1
    except Exception as e:
        raise RuntimeError(f"无法打开视频: {e}")

    keyframe_hashes = []
    total_frame_count = 0
    keyframe_count = 0

    # 提取所有关键帧的 phash
    for packet in container.demux(video=0):
        for frame in packet.decode():
            total_frame_count += 1

            if not (frame.key_frame or frame.pict_type == "I"):
                continue

            try:
                img = frame.to_image()
                h = imagehash.phash(img, hash_size=hash_size)
                keyframe_hashes.append(h)
                keyframe_count += 1
            except Exception as e:
                print(f"处理第 {total_frame_count - 1} 帧时出错: {e}")
                continue

    container.close()

    # 计算相邻关键帧的 phash 距离
    distances = [
        keyframe_hashes[i] - keyframe_hashes[i - 1] for i in range(1, len(keyframe_hashes))
    ]
    plt.plot(distances)
    plt.show()


def detect_max_jump_after_stable(
    video_path: str,
    hash_size: int = 16,
    stable_distance_threshold: int = 1,  # 静止期：phash 距离 <= 1
    min_stable_frames: int = 2,  # 静止期最少连续帧数（关键帧对）
) -> int:
    """
    检测在连续静止关键帧之后，图像跳变的最大 phash 距离。

    算法逻辑：
    1. 提取所有关键帧（I-frame）
    2. 计算相邻关键帧的 phash 汉明距离
    3. 找到所有“连续多个距离 <= 阈值”的静止段
    4. 对每个静止段，查看其**后一个距离**（即跳变）
    5. 返回这些跳变距离中的最大值

    Args:
        video_path: 视频路径
        hash_size: phash 哈希尺寸（推荐 16）
        stable_distance_threshold: 判断为“静止”的最大 phash 距离
        min_stable_frames: 静止段最少包含多少个“小距离”（即连续静止帧对数）

    Returns:
        int: 所有“静止后跳变”中，跳变距离的最大值。如果没有符合条件的跳变，返回 0。
    """
    try:
        container = av.open(video_path)
        stream = container.streams.video[0]
        stream.thread_count = 1
    except Exception as e:
        raise RuntimeError(f"无法打开视频: {e}")

    keyframe_hashes = []
    total_frame_count = 0
    keyframe_count = 0

    # 提取所有关键帧的 phash
    for packet in container.demux(video=0):
        for frame in packet.decode():
            total_frame_count += 1

            if not (frame.key_frame or frame.pict_type == "I"):
                continue

            try:
                img = frame.to_image()
                h = imagehash.phash(img, hash_size=hash_size)
                keyframe_hashes.append(h)
                keyframe_count += 1
            except Exception as e:
                print(f"处理第 {total_frame_count - 1} 帧时出错: {e}")
                continue

    container.close()

    if len(keyframe_hashes) < 2:
        return 0  # 帧数不足

    # 计算相邻关键帧的 phash 距离
    distances = [
        keyframe_hashes[i] - keyframe_hashes[i - 1] for i in range(1, len(keyframe_hashes))
    ]

    max_jump = 0  # 存储最大跳变距离

    # 遍历所有可能的跳变点（从第 min_stable_frames 个距离开始）
    for i in range(min_stable_frames, len(distances)):
        # 检查前 min_stable_frames 个距离是否都 <= 阈值（静止段）
        is_stable = all(
            d <= stable_distance_threshold for d in distances[i - min_stable_frames : i]
        )

        if is_stable:
            # 当前距离就是“跳变”
            jump_distance = distances[i]
            if jump_distance > max_jump:
                max_jump = jump_distance

    return max_jump


class JumpFrameDetector:
    def __init__(
        self,
        video_dir_path: str,
        logger: logging.Logger,
        hash_size: int = 16,
        stable_distance_threshold: int = 2,
        min_statble_frames: int = 10,
        sample_rate: float = 0.1,
    ) -> None:
        self.video_dir_path = video_dir_path
        self.hash_size = hash_size
        self.stable_distance_threshold = stable_distance_threshold
        self.min_stable_frames = min_statble_frames
        self.sample_rate = np.clip(sample_rate, 0.01, 0.2)
        self.logger = logger

    def detect(self) -> dict[str | Path, int]:
        video_paths = [p for p in Path(self.video_dir_path).glob("*.mp4") if p.is_file()]
        video_paths = random.sample(video_paths, int(len(video_paths) * self.sample_rate))
        results = {}
        for video_path in tqdm.tqdm(video_paths, desc="Detect Jump Frame in Videos", unit="video"):
            results[video_path.name] = detect_max_jump_after_stable(video_path)
        self.logger.info(f"{self.video_dir_path} 检测结果：\n")
        self.logger.info(results)
        return results
