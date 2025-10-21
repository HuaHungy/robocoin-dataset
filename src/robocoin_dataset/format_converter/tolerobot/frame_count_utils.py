"""
帧数获取和对齐工具 - 统一的帧数获取接口

这个模块提供了从不同数据源快速获取帧数的统一接口，以及帧数对齐策略。
核心目标：避免加载整个视频/数据到内存，只获取元数据。

支持的数据源：
- MP4/视频文件: 使用ffprobe快速获取
- H5/HDF5文件: 读取dataset.shape[0]
- JSON文件: 读取数组长度
- MCAP文件: 统计topic消息数

Created: 2025-10-21
Author: Refactoring Team
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

import h5py
import numpy as np


# ============================================================================
# 视频帧数获取
# ============================================================================

def get_video_frame_count(
    video_path: Union[str, Path],
    logger: Optional[logging.Logger] = None,
    use_fallback: bool = True
) -> int:
    """使用ffprobe快速获取视频帧数
    
    Args:
        video_path: 视频文件路径
        logger: 日志记录器
        use_fallback: 如果ffprobe失败，是否使用cv2作为备用方案
    
    Returns:
        视频总帧数
    
    Raises:
        RuntimeError: 如果无法获取帧数
        FileNotFoundError: 如果文件不存在
    """
    video_path = Path(video_path)
    
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # 优先使用ffprobe（快速且准确）
    try:
        return _get_video_frame_count_ffprobe(video_path, logger)
    except RuntimeError as e:
        if not use_fallback:
            raise
        
        # 备用方案：使用cv2
        if logger:
            logger.warning(f"ffprobe failed, falling back to cv2: {e}")
        
        try:
            return _get_video_frame_count_cv2(video_path, logger)
        except Exception as cv2_error:
            raise RuntimeError(
                f"Both ffprobe and cv2 failed to get frame count:\n"
                f"  ffprobe error: {e}\n"
                f"  cv2 error: {cv2_error}"
            )


def _get_video_frame_count_ffprobe(
    video_path: Path,
    logger: Optional[logging.Logger] = None
) -> int:
    """使用ffprobe获取视频帧数（内部函数）"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-count_packets',
            '-show_entries', 'stream=nb_read_packets',
            '-of', 'csv=p=0',
            str(video_path)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )
        
        frame_count = int(result.stdout.strip())
        
        if logger:
            logger.debug(f"ffprobe: {video_path.name} = {frame_count} frames")
        
        return frame_count
        
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed: {e.stderr.strip() if e.stderr else str(e)}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timeout (30s) for {video_path.name}")
    except ValueError as e:
        raise RuntimeError(f"Invalid ffprobe output: {result.stdout.strip()}")


def _get_video_frame_count_cv2(
    video_path: Path,
    logger: Optional[logging.Logger] = None
) -> int:
    """使用cv2获取视频帧数（备用方案，内部函数）"""
    import cv2
    
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    
    try:
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if logger:
            logger.debug(f"cv2: {video_path.name} = {frame_count} frames")
        
        return frame_count
    finally:
        cap.release()


# ============================================================================
# H5/HDF5帧数获取
# ============================================================================

def get_h5_frame_count(
    h5_path: Union[str, Path],
    dataset_path: str,
    logger: Optional[logging.Logger] = None
) -> int:
    """从H5文件中获取数据集的帧数
    
    Args:
        h5_path: H5文件路径
        dataset_path: H5内部数据集路径（如 "observations/qpos"）
        logger: 日志记录器
    
    Returns:
        数据集的第一个维度大小（帧数）
    
    Raises:
        FileNotFoundError: 如果H5文件不存在
        KeyError: 如果数据集路径不存在
        ValueError: 如果数据集是标量
    """
    h5_path = Path(h5_path)
    
    if not h5_path.exists():
        raise FileNotFoundError(f"H5 file not found: {h5_path}")
    
    try:
        with h5py.File(h5_path, 'r') as f:
            if dataset_path not in f:
                available_paths = list(f.keys())
                raise KeyError(
                    f"Dataset path '{dataset_path}' not found in H5 file\n"
                    f"Available top-level keys: {available_paths}"
                )
            
            dataset = f[dataset_path]
            
            if not isinstance(dataset, h5py.Dataset):
                raise ValueError(
                    f"Path '{dataset_path}' is not a dataset (it's a {type(dataset).__name__})"
                )
            
            shape = dataset.shape
            
            if len(shape) == 0:
                raise ValueError(
                    f"Dataset '{dataset_path}' is a scalar (shape={shape})"
                )
            
            frame_count = shape[0]
            
            if logger:
                logger.debug(
                    f"H5: {h5_path.name}::{dataset_path} = {frame_count} frames "
                    f"(shape={shape})"
                )
            
            return frame_count
            
    except OSError as e:
        raise RuntimeError(f"Cannot read H5 file {h5_path}: {e}")


def get_h5_all_frame_counts(
    h5_path: Union[str, Path],
    dataset_paths: List[str],
    logger: Optional[logging.Logger] = None
) -> Dict[str, int]:
    """批量获取H5文件中多个数据集的帧数
    
    Args:
        h5_path: H5文件路径
        dataset_paths: 数据集路径列表
        logger: 日志记录器
    
    Returns:
        {dataset_path: frame_count} 字典
    """
    h5_path = Path(h5_path)
    frame_counts = {}
    
    with h5py.File(h5_path, 'r') as f:
        for dataset_path in dataset_paths:
            try:
                if dataset_path in f:
                    dataset = f[dataset_path]
                    if isinstance(dataset, h5py.Dataset) and len(dataset.shape) > 0:
                        frame_counts[dataset_path] = dataset.shape[0]
            except Exception as e:
                if logger:
                    logger.warning(f"Failed to get frame count for {dataset_path}: {e}")
    
    return frame_counts


# ============================================================================
# JSON帧数获取
# ============================================================================

def get_json_frame_count(
    json_path: Union[str, Path],
    array_key: str = "data",
    logger: Optional[logging.Logger] = None
) -> int:
    """从JSON文件中获取数组的长度
    
    Args:
        json_path: JSON文件路径
        array_key: 数组字段的键（支持嵌套，如 "data.frames"）
        logger: 日志记录器
    
    Returns:
        数组长度（帧数）
    
    Raises:
        FileNotFoundError: 如果JSON文件不存在
        KeyError: 如果键不存在
        ValueError: 如果值不是数组
    """
    json_path = Path(json_path)
    
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 支持嵌套键（如 "data.frames"）
        keys = array_key.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict):
                if key not in current:
                    raise KeyError(
                        f"Key '{key}' not found in JSON path '{array_key}'\n"
                        f"Available keys at this level: {list(current.keys())}"
                    )
                current = current[key]
            else:
                raise ValueError(
                    f"Cannot access key '{key}' in non-dict type {type(current).__name__}"
                )
        
        if not isinstance(current, (list, tuple)):
            raise ValueError(
                f"Value at '{array_key}' is not an array (type: {type(current).__name__})"
            )
        
        frame_count = len(current)
        
        if logger:
            logger.debug(f"JSON: {json_path.name}::{array_key} = {frame_count} frames")
        
        return frame_count
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON file {json_path}: {e}")


# ============================================================================
# MCAP帧数获取
# ============================================================================

def get_mcap_frame_count(
    mcap_path: Union[str, Path],
    topic: str,
    logger: Optional[logging.Logger] = None
) -> int:
    """从MCAP文件中获取指定topic的消息数量
    
    Args:
        mcap_path: MCAP文件路径
        topic: topic名称
        logger: 日志记录器
    
    Returns:
        消息数量（帧数）
    
    Raises:
        FileNotFoundError: 如果MCAP文件不存在
        ImportError: 如果mcap库未安装
        KeyError: 如果topic不存在
    """
    mcap_path = Path(mcap_path)
    
    if not mcap_path.exists():
        raise FileNotFoundError(f"MCAP file not found: {mcap_path}")
    
    try:
        from mcap.reader import make_reader
    except ImportError:
        raise ImportError(
            "mcap library is required for MCAP support. "
            "Install with: pip install mcap"
        )
    
    try:
        message_count = 0
        
        with open(mcap_path, "rb") as f:
            reader = make_reader(f)
            
            # 只统计指定topic的消息
            for schema, channel, message in reader.iter_messages(topics=[topic]):
                message_count += 1
        
        if message_count == 0:
            # 检查topic是否存在
            with open(mcap_path, "rb") as f:
                reader = make_reader(f)
                summary = reader.get_summary()
                if summary and summary.channels:
                    available_topics = [ch.topic for ch in summary.channels.values()]
                    raise KeyError(
                        f"Topic '{topic}' has no messages\n"
                        f"Available topics: {available_topics}"
                    )
        
        if logger:
            logger.debug(f"MCAP: {mcap_path.name}::{topic} = {message_count} messages")
        
        return message_count
        
    except Exception as e:
        raise RuntimeError(f"Failed to read MCAP file {mcap_path}: {e}")


# ============================================================================
# 帧数对齐策略
# ============================================================================

class FrameAlignmentStrategy:
    """帧数对齐策略枚举"""
    MIN = "min"          # 取最小值
    MAX = "max"          # 取最大值
    STRICT = "strict"    # 严格相等，不一致则报错
    MAJORITY = "majority"  # 取多数值（最常见的帧数）


def align_frame_counts(
    frame_sources: Dict[str, int],
    strategy: str = FrameAlignmentStrategy.MIN,
    tolerance: int = 0,
    logger: Optional[logging.Logger] = None,
    strict_mode: bool = False
) -> int:
    """统一的帧数对齐策略
    
    Args:
        frame_sources: {source_name: frame_count} 字典
        strategy: 对齐策略 ("min", "max", "strict", "majority")
        tolerance: 允许的帧数差异（仅对非strict策略有效）
        logger: 日志记录器
        strict_mode: 严格模式（前N个episode），会将不一致升级为ConfigError
    
    Returns:
        对齐后的帧数
        
    Raises:
        ValueError: 如果帧数差异超过容差
        ConfigError: 如果strict_mode=True且帧数不一致
    """
    from .exceptions import raise_frame_count_error
    
    if not frame_sources:
        raise ValueError("frame_sources cannot be empty")
    
    counts = list(frame_sources.values())
    min_count = min(counts)
    max_count = max(counts)
    diff = max_count - min_count
    
    # 检查一致性
    if diff > tolerance:
        if logger:
            logger.warning(
                f"Frame count mismatch detected:\n" +
                "\n".join(f"  {src}: {cnt}" for src, cnt in frame_sources.items()) +
                f"\n  Difference: {diff} frames (tolerance: {tolerance})"
            )
        
        # 在严格模式或STRICT策略下，抛出异常
        if strict_mode or strategy == FrameAlignmentStrategy.STRICT:
            raise_frame_count_error(frame_sources, strict_mode=strict_mode)
    
    # 应用对齐策略
    if strategy == FrameAlignmentStrategy.MIN:
        aligned_count = min_count
    elif strategy == FrameAlignmentStrategy.MAX:
        aligned_count = max_count
    elif strategy == FrameAlignmentStrategy.STRICT:
        # 已在上面检查过
        aligned_count = min_count
    elif strategy == FrameAlignmentStrategy.MAJORITY:
        # 找到最常见的帧数
        from collections import Counter
        count_freq = Counter(counts)
        aligned_count = count_freq.most_common(1)[0][0]
    else:
        raise ValueError(f"Unknown alignment strategy: {strategy}")
    
    if logger and diff > 0:
        logger.info(
            f"Frame alignment: strategy={strategy}, "
            f"range=[{min_count}, {max_count}], "
            f"aligned={aligned_count}"
        )
    
    return aligned_count


# ============================================================================
# 便利函数：自动检测并获取帧数
# ============================================================================

def get_frame_count_auto(
    file_path: Union[str, Path],
    dataset_or_key: Optional[str] = None,
    logger: Optional[logging.Logger] = None
) -> int:
    """自动检测文件类型并获取帧数
    
    Args:
        file_path: 文件路径
        dataset_or_key: H5数据集路径或JSON键（可选）
        logger: 日志记录器
    
    Returns:
        帧数
    
    Raises:
        ValueError: 如果文件类型不支持
    """
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()
    
    if suffix in ['.mp4', '.avi', '.mov', '.mkv', '.flv']:
        return get_video_frame_count(file_path, logger=logger)
    
    elif suffix in ['.h5', '.hdf5']:
        if not dataset_or_key:
            raise ValueError("dataset_path is required for H5 files")
        return get_h5_frame_count(file_path, dataset_or_key, logger=logger)
    
    elif suffix == '.json':
        key = dataset_or_key or "data"
        return get_json_frame_count(file_path, key, logger=logger)
    
    elif suffix == '.mcap':
        if not dataset_or_key:
            raise ValueError("topic is required for MCAP files")
        return get_mcap_frame_count(file_path, dataset_or_key, logger=logger)
    
    else:
        raise ValueError(
            f"Unsupported file type: {suffix}\n"
            f"Supported: .mp4, .avi, .mov, .mkv, .h5, .hdf5, .json, .mcap"
        )

