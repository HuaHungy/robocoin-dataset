"""
视频帧数验证工具
使用ffprobe快速获取视频帧数，并验证与其他数据源的帧数是否匹配
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional


def get_video_frame_count_ffprobe(video_path: Path, logger: Optional[logging.Logger] = None) -> int:
    """
    使用ffprobe获取视频的总帧数
    
    Args:
        video_path: 视频文件路径
        logger: 日志记录器（可选）
    
    Returns:
        视频总帧数
        
    Raises:
        RuntimeError: 如果ffprobe执行失败或无法获取帧数
        FileNotFoundError: 如果视频文件不存在
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    try:
        # 使用ffprobe获取视频流信息
        # -v error: 只显示错误信息
        # -select_streams v:0: 选择第一个视频流
        # -count_packets: 计算包数量
        # -show_entries stream=nb_read_packets: 显示读取的包数量
        # -of csv=p=0: 输出为CSV格式，不带标题
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
            logger.debug(f"📹 Video frame count: {video_path.name} = {frame_count} frames")
        
        return frame_count
        
    except subprocess.CalledProcessError as e:
        error_msg = (
            f"❌ ffprobe failed to read video file\n"
            f"   📄 File: {video_path}\n"
            f"   ⚠️ Error: {e.stderr.strip() if e.stderr else str(e)}\n"
            f"   💡 Please check:\n"
            f"      1. ffprobe is installed (part of ffmpeg)\n"
            f"      2. Video file is not corrupted\n"
            f"      3. Video codec is supported"
        )
        if logger:
            logger.error(error_msg)
        raise RuntimeError(error_msg) from e
        
    except subprocess.TimeoutExpired as e:
        error_msg = (
            f"❌ ffprobe timeout\n"
            f"   📄 File: {video_path}\n"
            f"   ⏱️ Timeout: 30 seconds\n"
            f"   💡 Video file might be too large or corrupted"
        )
        if logger:
            logger.error(error_msg)
        raise RuntimeError(error_msg) from e
        
    except ValueError as e:
        error_msg = (
            f"❌ Failed to parse frame count from ffprobe output\n"
            f"   📄 File: {video_path}\n"
            f"   📤 Output: {result.stdout.strip()}\n"
            f"   ⚠️ Error: {str(e)}"
        )
        if logger:
            logger.error(error_msg)
        raise RuntimeError(error_msg) from e


def validate_video_frame_count(
    video_path: Path,
    expected_frame_count: int,
    data_source: str,
    logger: Optional[logging.Logger] = None,
    tolerance: int = 0
) -> None:
    """
    验证视频帧数是否与预期帧数匹配
    
    Args:
        video_path: 视频文件路径
        expected_frame_count: 预期的帧数
        data_source: 数据源描述（用于错误信息，如 "H5 file", "JSON data"）
        logger: 日志记录器（可选）
        tolerance: 允许的帧数误差（默认为0，必须完全匹配）
        
    Raises:
        ValueError: 如果帧数不匹配
    """
    actual_frame_count = get_video_frame_count_ffprobe(video_path, logger)
    
    frame_diff = abs(actual_frame_count - expected_frame_count)
    
    if frame_diff > tolerance:
        error_msg = (
            f"❌ Video frame count mismatch\n"
            f"   📄 Video: {video_path.name}\n"
            f"   🎬 Video frames: {actual_frame_count}\n"
            f"   📊 {data_source} frames: {expected_frame_count}\n"
            f"   ⚠️ Difference: {frame_diff} frames\n"
        )
        
        if tolerance > 0:
            error_msg += f"   📏 Tolerance: ±{tolerance} frames\n"
        
        error_msg += (
            f"   💡 Possible causes:\n"
            f"      1. Video recording was interrupted\n"
            f"      2. Data collection was stopped early\n"
            f"      3. Frame timestamps mismatch between video and data\n"
            f"      4. Video encoding dropped frames\n"
            f"   💡 Solutions:\n"
            f"      1. Re-record the episode\n"
            f"      2. Trim the data to match video length\n"
            f"      3. Check data collection pipeline"
        )
        
        if logger:
            logger.error(error_msg)
        
        raise ValueError(error_msg)
    
    if logger:
        if frame_diff == 0:
            logger.info(
                f"✅ Video frame count validated: {video_path.name}\n"
                f"   🎬 Video frames: {actual_frame_count}\n"
                f"   📊 {data_source} frames: {expected_frame_count}\n"
                f"   ✓ Perfect match!"
            )
        else:
            logger.info(
                f"✅ Video frame count validated (within tolerance): {video_path.name}\n"
                f"   🎬 Video frames: {actual_frame_count}\n"
                f"   📊 {data_source} frames: {expected_frame_count}\n"
                f"   ⚠️ Difference: {frame_diff} frames (tolerance: ±{tolerance})"
            )


def get_video_info_ffprobe(video_path: Path, logger: Optional[logging.Logger] = None) -> dict:
    """
    使用ffprobe获取视频的详细信息
    
    Args:
        video_path: 视频文件路径
        logger: 日志记录器（可选）
    
    Returns:
        包含视频信息的字典（width, height, fps, duration, frame_count等）
        
    Raises:
        RuntimeError: 如果ffprobe执行失败
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,r_frame_rate,duration,nb_frames,nb_read_packets',
            '-of', 'json',
            str(video_path)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )
        
        data = json.loads(result.stdout)
        stream_info = data['streams'][0] if data.get('streams') else {}
        
        # 解析帧率（格式如 "30/1" 或 "30000/1001"）
        fps_str = stream_info.get('r_frame_rate', '0/1')
        num, den = map(int, fps_str.split('/'))
        fps = num / den if den != 0 else 0
        
        info = {
            'width': stream_info.get('width', 0),
            'height': stream_info.get('height', 0),
            'fps': fps,
            'duration': float(stream_info.get('duration', 0)),
            'frame_count': int(stream_info.get('nb_read_packets', 0)),  # 使用nb_read_packets作为帧数
        }
        
        if logger:
            logger.debug(
                f"📹 Video info: {video_path.name}\n"
                f"   Resolution: {info['width']}x{info['height']}\n"
                f"   FPS: {info['fps']:.2f}\n"
                f"   Duration: {info['duration']:.2f}s\n"
                f"   Frames: {info['frame_count']}"
            )
        
        return info
        
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, ValueError) as e:
        error_msg = f"Failed to get video info from {video_path}: {str(e)}"
        if logger:
            logger.error(error_msg)
        raise RuntimeError(error_msg) from e
