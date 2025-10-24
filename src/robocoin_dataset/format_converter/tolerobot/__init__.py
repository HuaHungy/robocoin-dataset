"""
LeRobot格式转换器模块

这个模块提供了将各种机器人数据集格式转换为LeRobot标准格式的工具。
"""

from .lerobot_format_converter import (
    LerobotFormatConverter,
    LerobotFormatConverterFactory,
)

from .exceptions import (
    ConverterError,
    ConfigError,
    DataQualityError,
    CriticalDataError,
    FrameCountMismatchError,
    ResourceError,
    raise_field_not_found_error,
    raise_frame_count_error,
)

from .frame_count_utils import (
    get_video_frame_count,
    get_h5_frame_count,
    get_h5_all_frame_counts,
    get_json_frame_count,
    get_mcap_frame_count,
    align_frame_counts,
    FrameAlignmentStrategy,
    get_frame_count_auto,
)

__all__ = [
    # 基类和工厂
    "LerobotFormatConverter",
    "LerobotFormatConverterFactory",
    
    # 异常类
    "ConverterError",
    "ConfigError",
    "DataQualityError",
    "CriticalDataError",
    "FrameCountMismatchError",
    "ResourceError",
    "raise_field_not_found_error",
    "raise_frame_count_error",
    
    # 帧数工具
    "get_video_frame_count",
    "get_h5_frame_count",
    "get_h5_all_frame_counts",
    "get_json_frame_count",
    "get_mcap_frame_count",
    "align_frame_counts",
    "FrameAlignmentStrategy",
    "get_frame_count_auto",
]

