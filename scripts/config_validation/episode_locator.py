"""
Episode定位器 - 针对不同数据格式快速定位episodes

支持的格式：
- H5: episode_{idx}.hdf5 或 episode_{idx}.h5
- MP4+JSON: task文件夹下的episodes
- MCAP: .mcap文件
- MMK2 BSON: episode文件夹（包含episode_*.bson）
- JPG+JSON: episode文件夹（包含图片序列）
- Leju Waibu: 特殊的嵌套结构
"""

import logging
import random
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import re


class EpisodeInfo:
    """Episode信息"""
    def __init__(
        self,
        episode_idx: int,
        episode_path: Path,
        format_type: str,
        task_path: Optional[Path] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.episode_idx = episode_idx
        self.episode_path = episode_path
        self.format_type = format_type
        self.task_path = task_path
        self.metadata = metadata or {}
    
    def __repr__(self):
        return f"EpisodeInfo(idx={self.episode_idx}, path={self.episode_path}, format={self.format_type})"


class EpisodeLocator:
    """Episode定位器"""
    
    # 支持的数据格式
    FORMAT_H5 = "h5"
    FORMAT_MP4_JSON = "mp4_json"
    FORMAT_JPG_JSON = "jpg_json"
    FORMAT_MCAP = "mcap"
    FORMAT_MMK2_BSON = "mmk2_bson"
    FORMAT_LEJU_WAIBU = "leju_waibu"
    FORMAT_H5_MP4 = "h5_mp4"
    FORMAT_H5_JPG = "h5_jpg"
    FORMAT_ROSBAG = "rosbag"
    FORMAT_LEROBOT = "lerobot"
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def detect_format(self, dataset_path: Path) -> str:
        """
        自动检测数据集格式
        
        Returns:
            格式类型字符串
        """
        dataset_path = Path(dataset_path)
        
        # 检查是否有特定文件模式
        has_h5 = list(dataset_path.rglob("*.hdf5")) or list(dataset_path.rglob("*.h5"))
        has_mp4 = list(dataset_path.rglob("*.mp4"))
        has_jpg = list(dataset_path.rglob("*.jpg")) or list(dataset_path.rglob("*.png"))
        has_json = list(dataset_path.rglob("*.json"))
        has_mcap = list(dataset_path.rglob("*.mcap"))
        has_bson = list(dataset_path.rglob("*.bson"))
        has_bag = list(dataset_path.rglob("*.bag"))
        
        # LeRobot格式检测（有meta/info.json）
        if (dataset_path / "meta" / "info.json").exists():
            return self.FORMAT_LEROBOT
        
        # MMK2 BSON格式（有xhand_control_data.bson）
        if has_bson:
            xhand_files = list(dataset_path.rglob("xhand_control_data.bson"))
            if xhand_files:
                return self.FORMAT_MMK2_BSON
        
        # Leju Waibu格式检测（特殊的嵌套结构：episode_*/timestep_*/...）
        episode_dirs = list(dataset_path.glob("episode_*"))
        if episode_dirs and has_mp4 and has_json:
            # 检查是否有timestep子目录
            first_ep = episode_dirs[0]
            if list(first_ep.glob("timestep_*")):
                return self.FORMAT_LEJU_WAIBU
        
        # MCAP格式
        if has_mcap:
            return self.FORMAT_MCAP
        
        # ROS Bag格式
        if has_bag:
            return self.FORMAT_ROSBAG
        
        # H5 + MP4格式（H5文件和对应的MP4视频）
        if has_h5 and has_mp4:
            # 检查是否有匹配的文件名模式
            h5_files = [f.stem for f in (list(dataset_path.rglob("*.hdf5")) + list(dataset_path.rglob("*.h5")))[:10]]
            mp4_files = [f.stem for f in list(dataset_path.rglob("*.mp4"))[:10]]
            # 如果有匹配的文件名（如episode_0.h5 和 episode_0_cam.mp4）
            for h5_stem in h5_files:
                if any(h5_stem in mp4_stem for mp4_stem in mp4_files):
                    return self.FORMAT_H5_MP4
        
        # H5 + JPG格式
        if has_h5 and has_jpg:
            return self.FORMAT_H5_JPG
        
        # 纯H5格式
        if has_h5 and not has_mp4 and not has_jpg:
            return self.FORMAT_H5
        
        # MP4 + JSON格式
        if has_mp4 and has_json and not has_h5:
            return self.FORMAT_MP4_JSON
        
        # JPG + JSON格式
        if has_jpg and has_json and not has_h5:
            return self.FORMAT_JPG_JSON
        
        raise ValueError(f"无法识别数据集格式: {dataset_path}")
    
    def locate_episodes(
        self,
        dataset_path: Path,
        format_type: Optional[str] = None,
        num_samples: int = 2
    ) -> List[EpisodeInfo]:
        """
        定位并采样episodes
        
        Args:
            dataset_path: 数据集路径
            format_type: 格式类型（None表示自动检测）
            num_samples: 采样数量
            
        Returns:
            采样的Episode信息列表
        """
        dataset_path = Path(dataset_path)
        
        if format_type is None:
            format_type = self.detect_format(dataset_path)
        
        self.logger.info(f"检测到格式: {format_type}")
        
        # 根据格式调用对应的定位方法
        if format_type == self.FORMAT_H5:
            all_episodes = self._locate_h5_episodes(dataset_path)
        elif format_type == self.FORMAT_MP4_JSON:
            all_episodes = self._locate_mp4_json_episodes(dataset_path)
        elif format_type == self.FORMAT_JPG_JSON:
            all_episodes = self._locate_jpg_json_episodes(dataset_path)
        elif format_type == self.FORMAT_MCAP:
            all_episodes = self._locate_mcap_episodes(dataset_path)
        elif format_type == self.FORMAT_MMK2_BSON:
            all_episodes = self._locate_mmk2_episodes(dataset_path)
        elif format_type == self.FORMAT_LEJU_WAIBU:
            all_episodes = self._locate_leju_waibu_episodes(dataset_path)
        elif format_type == self.FORMAT_H5_MP4:
            all_episodes = self._locate_h5_mp4_episodes(dataset_path)
        elif format_type == self.FORMAT_H5_JPG:
            all_episodes = self._locate_h5_jpg_episodes(dataset_path)
        elif format_type == self.FORMAT_ROSBAG:
            all_episodes = self._locate_rosbag_episodes(dataset_path)
        elif format_type == self.FORMAT_LEROBOT:
            all_episodes = self._locate_lerobot_episodes(dataset_path)
        else:
            raise ValueError(f"不支持的格式类型: {format_type}")
        
        if not all_episodes:
            raise ValueError(f"未找到任何episodes: {dataset_path}")
        
        self.logger.info(f"找到 {len(all_episodes)} 个episodes")
        
        # 随机采样
        if len(all_episodes) <= num_samples:
            sampled = all_episodes
        else:
            sampled = random.sample(all_episodes, num_samples)
        
        # 按episode_idx排序
        sampled.sort(key=lambda x: x.episode_idx)
        
        self.logger.info(f"采样 {len(sampled)} 个episodes: {[ep.episode_idx for ep in sampled]}")
        
        return sampled
    
    def _locate_h5_episodes(self, dataset_path: Path) -> List[EpisodeInfo]:
        """定位纯H5格式的episodes"""
        episodes = []
        
        # 查找所有episode_{idx}.hdf5或episode_{idx}.h5文件
        for pattern in ["**/episode_*.hdf5", "**/episode_*.h5"]:
            for h5_file in dataset_path.glob(pattern):
                match = re.search(r'episode_(\d+)', h5_file.stem)
                if match:
                    idx = int(match.group(1))
                    task_path = h5_file.parent
                    episodes.append(EpisodeInfo(
                        episode_idx=idx,
                        episode_path=h5_file,
                        format_type=self.FORMAT_H5,
                        task_path=task_path
                    ))
        
        return episodes
    
    def _locate_mp4_json_episodes(self, dataset_path: Path) -> List[EpisodeInfo]:
        """定位MP4+JSON格式的episodes"""
        episodes = []
        
        # 查找所有task目录（通常在第一层或第二层）
        for depth in range(3):
            pattern = "/".join(["*"] * depth) + "/"
            for task_dir in dataset_path.glob(pattern):
                if not task_dir.is_dir():
                    continue
                
                # 检查是否有episode_{idx}目录
                episode_dirs = list(task_dir.glob("episode_*"))
                for ep_dir in episode_dirs:
                    match = re.search(r'episode_(\d+)', ep_dir.name)
                    if match:
                        idx = int(match.group(1))
                        episodes.append(EpisodeInfo(
                            episode_idx=idx,
                            episode_path=ep_dir,
                            format_type=self.FORMAT_MP4_JSON,
                            task_path=task_dir
                        ))
        
        return episodes
    
    def _locate_jpg_json_episodes(self, dataset_path: Path) -> List[EpisodeInfo]:
        """定位JPG+JSON格式的episodes"""
        # 类似MP4+JSON
        return self._locate_mp4_json_episodes(dataset_path)
    
    def _locate_mcap_episodes(self, dataset_path: Path) -> List[EpisodeInfo]:
        """定位MCAP格式的episodes"""
        episodes = []
        
        # MCAP文件通常按照某种模式命名，每个文件是一个episode
        mcap_files = list(dataset_path.rglob("*.mcap"))
        
        for idx, mcap_file in enumerate(mcap_files):
            episodes.append(EpisodeInfo(
                episode_idx=idx,
                episode_path=mcap_file,
                format_type=self.FORMAT_MCAP,
                task_path=mcap_file.parent,
                metadata={'original_filename': mcap_file.name}
            ))
        
        return episodes
    
    def _locate_mmk2_episodes(self, dataset_path: Path) -> List[EpisodeInfo]:
        """定位MMK2 BSON格式的episodes"""
        episodes = []
        
        # MMK2格式：每个episode是一个文件夹，包含episode_*.bson和xhand_control_data.bson
        for task_dir in dataset_path.rglob("*"):
            if not task_dir.is_dir():
                continue
            
            # 检查是否有xhand_control_data.bson
            if not (task_dir / "xhand_control_data.bson").exists():
                continue
            
            # 查找episode_*.bson文件
            episode_bson_files = list(task_dir.glob("episode_*.bson"))
            for bson_file in episode_bson_files:
                match = re.search(r'episode_(\d+)', bson_file.stem)
                if match:
                    idx = int(match.group(1))
                    episodes.append(EpisodeInfo(
                        episode_idx=idx,
                        episode_path=task_dir,  # 整个文件夹是episode
                        format_type=self.FORMAT_MMK2_BSON,
                        task_path=task_dir.parent,
                        metadata={'bson_file': bson_file.name}
                    ))
        
        return episodes
    
    def _locate_leju_waibu_episodes(self, dataset_path: Path) -> List[EpisodeInfo]:
        """
        定位Leju Waibu格式的episodes
        
        特殊结构：
        dataset/
          task/
            episode_0/
              timestep_0/
                *.mp4, *.json
              timestep_1/
                ...
            episode_1/
              ...
        """
        episodes = []
        
        # 查找所有task目录
        for task_dir in dataset_path.rglob("*"):
            if not task_dir.is_dir():
                continue
            
            # 查找episode_*目录
            episode_dirs = list(task_dir.glob("episode_*"))
            for ep_dir in episode_dirs:
                # 检查是否有timestep子目录（Leju Waibu的特征）
                if not list(ep_dir.glob("timestep_*")):
                    continue
                
                match = re.search(r'episode_(\d+)', ep_dir.name)
                if match:
                    idx = int(match.group(1))
                    episodes.append(EpisodeInfo(
                        episode_idx=idx,
                        episode_path=ep_dir,
                        format_type=self.FORMAT_LEJU_WAIBU,
                        task_path=task_dir,
                        metadata={'has_timesteps': True}
                    ))
        
        return episodes
    
    def _locate_h5_mp4_episodes(self, dataset_path: Path) -> List[EpisodeInfo]:
        """定位H5+MP4格式的episodes"""
        episodes = []
        
        # 查找所有H5文件
        for h5_file in dataset_path.rglob("*.hdf5"):
            match = re.search(r'episode_(\d+)|(\d+)\.hdf5', h5_file.stem)
            if match:
                idx_str = match.group(1) or match.group(2)
                idx = int(idx_str)
                task_path = h5_file.parent
                episodes.append(EpisodeInfo(
                    episode_idx=idx,
                    episode_path=h5_file,
                    format_type=self.FORMAT_H5_MP4,
                    task_path=task_path
                ))
        
        return episodes
    
    def _locate_h5_jpg_episodes(self, dataset_path: Path) -> List[EpisodeInfo]:
        """定位H5+JPG格式的episodes"""
        # 类似H5+MP4
        return self._locate_h5_episodes(dataset_path)
    
    def _locate_rosbag_episodes(self, dataset_path: Path) -> List[EpisodeInfo]:
        """定位ROS Bag格式的episodes"""
        episodes = []
        
        bag_files = list(dataset_path.rglob("*.bag"))
        for idx, bag_file in enumerate(bag_files):
            episodes.append(EpisodeInfo(
                episode_idx=idx,
                episode_path=bag_file,
                format_type=self.FORMAT_ROSBAG,
                task_path=bag_file.parent,
                metadata={'original_filename': bag_file.name}
            ))
        
        return episodes
    
    def _locate_lerobot_episodes(self, dataset_path: Path) -> List[EpisodeInfo]:
        """定位LeRobot格式的episodes"""
        episodes = []
        
        # LeRobot格式：data/chunk-*/episode_*.parquet
        parquet_files = list(dataset_path.rglob("data/chunk-*/episode_*.parquet"))
        for pq_file in parquet_files:
            match = re.search(r'episode_(\d+)', pq_file.stem)
            if match:
                idx = int(match.group(1))
                episodes.append(EpisodeInfo(
                    episode_idx=idx,
                    episode_path=pq_file,
                    format_type=self.FORMAT_LEROBOT,
                    task_path=dataset_path
                ))
        
        return episodes


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    locator = EpisodeLocator()
    
    # 测试路径
    test_path = Path("/mnt/nas/synnas/docker/6discover_robotics_aitbot_mmk2/apple_storage")
    if test_path.exists():
        try:
            episodes = locator.locate_episodes(test_path, num_samples=2)
            for ep in episodes:
                print(ep)
        except Exception as e:
            print(f"Error: {e}")

