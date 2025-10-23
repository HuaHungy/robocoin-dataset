"""
统一的Episode定位器

使用BFS搜索，不依赖固定的目录层级结构，支持单文件和目录格式。
"""

from pathlib import Path
from collections import deque
from typing import List, Callable, Optional
import logging


class UnifiedEpisodeLocator:
    """统一的Episode定位器，使用BFS搜索"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def locate_episodes_bfs(
        self,
        dataset_path: Path,
        is_episode_func: Callable[[Path], bool],
        max_depth: int = 10,
        skip_dirs: Optional[List[str]] = None
    ) -> List[Path]:
        """
        使用BFS查找所有符合条件的episodes
        
        Args:
            dataset_path: 数据集根目录
            is_episode_func: 判断函数，返回True表示是episode
            max_depth: 最大搜索深度（默认10层）
            skip_dirs: 要跳过的目录名列表
            
        Returns:
            所有找到的episode路径列表（排序后）
        """
        if skip_dirs is None:
            skip_dirs = ['.', '@eaDir', '__pycache__', '.git', 'logs', 
                        'config', 'calibration', 'parameters', 'error',
                        '.idea', '.vscode', 'node_modules']
        
        episodes = []
        queue = deque([(dataset_path, 0)])  # (path, depth)
        visited = set()  # 防止重复访问
        
        while queue:
            current_path, depth = queue.popleft()
            
            # 防止重复访问
            if current_path in visited:
                continue
            visited.add(current_path)
            
            # 深度限制
            if depth > max_depth:
                continue
            
            # 检查当前路径是否是episode
            try:
                if is_episode_func(current_path):
                    episodes.append(current_path)
                    # 找到episode后不再向下搜索其子目录
                    continue
            except Exception as e:
                if self.logger:
                    self.logger.debug(f"Error checking if {current_path} is episode: {e}")
                # 继续搜索，不中断
            
            # 如果当前是目录，继续搜索子项
            if current_path.is_dir():
                try:
                    for item in current_path.iterdir():
                        # 跳过特殊目录
                        if item.is_dir() and (item.name in skip_dirs or item.name.startswith('.')):
                            continue
                        
                        # 将文件和目录都加入队列
                        queue.append((item, depth + 1))
                except PermissionError:
                    if self.logger:
                        self.logger.warning(f"Permission denied: {current_path}")
                    continue
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Error iterating {current_path}: {e}")
                    continue
        
        # 排序并返回
        sorted_episodes = sorted(episodes)
        
        if self.logger:
            self.logger.info(f"BFS搜索完成: 找到 {len(sorted_episodes)} 个episodes (最大深度={max_depth})")
        
        return sorted_episodes


# ============================================================================
# 各种格式的Episode判断函数
# ============================================================================

def is_rosbag_episode(path: Path) -> bool:
    """ROS Bag: 单个.bag文件"""
    return path.is_file() and path.suffix == '.bag'


def is_mcap_episode(path: Path) -> bool:
    """MCAP: 单个.mcap文件"""
    return path.is_file() and path.suffix == '.mcap'


def is_single_h5_episode(path: Path) -> bool:
    """
    单H5文件: 独立的.h5/.hdf5文件（不在组合格式目录中）
    
    需要排除H5+MP4、H5+JPG等组合格式
    """
    if not (path.is_file() and path.suffix in ['.h5', '.hdf5']):
        return False
    
    parent_dir = path.parent
    
    try:
        # 检查父目录中是否有.mp4文件（排除H5+MP4格式）
        has_mp4 = any(f.suffix == '.mp4' for f in parent_dir.iterdir() if f.is_file())
        if has_mp4:
            return False
        
        # 检查父目录中是否有camera/子目录（排除H5+JPG格式）
        has_camera_dir = (parent_dir / "camera").is_dir()
        if has_camera_dir:
            return False
        
        # 都不是组合格式，则是单H5文件
        return True
    except Exception:
        # 如果检查失败，保守处理，认为是单H5文件
        return True


def is_h5_mp4_episode(path: Path) -> bool:
    """H5+MP4: 目录中同时有.h5和.mp4文件"""
    if not path.is_dir():
        return False
    
    try:
        files = list(path.iterdir())
        has_h5 = any(f.is_file() and f.suffix in ['.h5', '.hdf5'] for f in files)
        has_mp4 = any(f.is_file() and f.suffix == '.mp4' for f in files)
        
        return has_h5 and has_mp4
    except Exception:
        return False


def is_h5_jpg_episode(path: Path) -> bool:
    """H5+JPG (Ruantong): 目录中有aligned_joints.h5文件"""
    if not path.is_dir():
        return False
    
    return (path / "aligned_joints.h5").exists()


def is_bson_jpg_episode(path: Path) -> bool:
    """BSON+JPG (MMK2): 目录中有.bson文件"""
    if not path.is_dir():
        return False
    
    try:
        bson_files = list(path.glob("*.bson"))
        return len(bson_files) > 0
    except Exception:
        return False


def is_mp4_json_episode(path: Path) -> bool:
    """MP4+JSON (Yinhe): 目录中有data.json文件"""
    if not path.is_dir():
        return False
    
    return (path / "data.json").exists()


def is_jpg_json_episode(path: Path, required_subdirs: Optional[List[str]] = None) -> bool:
    """
    JPG+JSON (Mult_Sensor): 目录中有特定子目录结构
    
    Args:
        path: 要检查的路径
        required_subdirs: 必需的子目录列表（至少有一个存在）
    """
    if not path.is_dir():
        return False
    
    # 默认检查常见子目录
    if required_subdirs is None:
        required_subdirs = ['arm', 'camera', 'gripper', 'localization', 'imu']
    
    try:
        subdirs = [d.name for d in path.iterdir() if d.is_dir()]
        
        # 至少有一个必需子目录
        return any(req_dir in subdirs for req_dir in required_subdirs)
    except Exception:
        return False


def is_leju_waibu_episode(path: Path) -> bool:
    """Leju Waibu: 目录中有metadata.json和proprio_stats.hdf5"""
    if not path.is_dir():
        return False
    
    has_metadata = (path / "metadata.json").exists()
    has_proprio = (path / "proprio_stats" / "proprio_stats.hdf5").exists()
    
    return has_metadata and has_proprio


# ============================================================================
# 便捷函数：直接定位特定格式的episodes
# ============================================================================

def locate_rosbag_episodes(dataset_path: Path, logger: Optional[logging.Logger] = None) -> List[Path]:
    """定位ROS Bag episodes"""
    locator = UnifiedEpisodeLocator(logger=logger)
    return locator.locate_episodes_bfs(dataset_path, is_rosbag_episode)


def locate_mcap_episodes(dataset_path: Path, logger: Optional[logging.Logger] = None) -> List[Path]:
    """定位MCAP episodes"""
    locator = UnifiedEpisodeLocator(logger=logger)
    return locator.locate_episodes_bfs(dataset_path, is_mcap_episode)


def locate_h5_mp4_episodes(dataset_path: Path, logger: Optional[logging.Logger] = None) -> List[Path]:
    """定位H5+MP4 episodes"""
    locator = UnifiedEpisodeLocator(logger=logger)
    return locator.locate_episodes_bfs(dataset_path, is_h5_mp4_episode)


def locate_h5_jpg_episodes(dataset_path: Path, logger: Optional[logging.Logger] = None) -> List[Path]:
    """定位H5+JPG episodes"""
    locator = UnifiedEpisodeLocator(logger=logger)
    return locator.locate_episodes_bfs(dataset_path, is_h5_jpg_episode)


def locate_bson_jpg_episodes(dataset_path: Path, logger: Optional[logging.Logger] = None) -> List[Path]:
    """定位BSON+JPG episodes"""
    locator = UnifiedEpisodeLocator(logger=logger)
    return locator.locate_episodes_bfs(dataset_path, is_bson_jpg_episode)


def locate_mp4_json_episodes(dataset_path: Path, logger: Optional[logging.Logger] = None) -> List[Path]:
    """定位MP4+JSON episodes"""
    locator = UnifiedEpisodeLocator(logger=logger)
    return locator.locate_episodes_bfs(dataset_path, is_mp4_json_episode)


def locate_single_h5_episodes(dataset_path: Path, logger: Optional[logging.Logger] = None) -> List[Path]:
    """定位单H5文件episodes"""
    locator = UnifiedEpisodeLocator(logger=logger)
    return locator.locate_episodes_bfs(dataset_path, is_single_h5_episode)

