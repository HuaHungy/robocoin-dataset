"""
LeRobot 格式转换器包

注意：为了避免在导入子模块（例如 `constant`）时引入沉重依赖，
本包采用按需惰性导入（lazy import）。只有在实际访问对应符号时
才会导入相应子模块。
"""
__all__ = [
    # 基类和工厂（惰性导入）
    "LerobotFormatConverter",
    "LerobotFormatConverterFactory",

    # 异常类（惰性导入）
    "ConverterError",
    "ConfigError",
    "DataQualityError",
    "CriticalDataError",
    "FrameCountMismatchError",
    "ResourceError",
    "raise_field_not_found_error",
    "raise_frame_count_error",

    # 帧数工具（惰性导入）
    "get_video_frame_count",
    "get_h5_frame_count",
    "get_h5_all_frame_counts",
    "get_json_frame_count",
    "get_mcap_frame_count",
    "align_frame_counts",
    "FrameAlignmentStrategy",
    "get_frame_count_auto",
]


def __getattr__(name: str) -> object:
    # 懒加载：只有在访问到相应符号时才导入对应模块
    if name in {"LerobotFormatConverter", "LerobotFormatConverterFactory"}:
        from .lerobot_format_converter import (
            LerobotFormatConverter as _LerobotFormatConverter,
        )
        from .lerobot_format_converter import (
            LerobotFormatConverterFactory as _LerobotFormatConverterFactory,
        )
        return {
            "LerobotFormatConverter": _LerobotFormatConverter,
            "LerobotFormatConverterFactory": _LerobotFormatConverterFactory,
        }[name]

    if name in {
        "ConverterError",
        "ConfigError",
        "DataQualityError",
        "CriticalDataError",
        "FrameCountMismatchError",
        "ResourceError",
        "raise_field_not_found_error",
        "raise_frame_count_error",
    }:
        from .exceptions import (
            ConfigError as _ConfigError,
        )
        from .exceptions import (
            ConverterError as _ConverterError,
        )
        from .exceptions import (
            CriticalDataError as _CriticalDataError,
        )
        from .exceptions import (
            DataQualityError as _DataQualityError,
        )
        from .exceptions import (
            FrameCountMismatchError as _FrameCountMismatchError,
        )
        from .exceptions import (
            ResourceError as _ResourceError,
        )
        from .exceptions import (
            raise_field_not_found_error as _raise_field_not_found_error,
        )
        from .exceptions import (
            raise_frame_count_error as _raise_frame_count_error,
        )
        return {
            "ConverterError": _ConverterError,
            "ConfigError": _ConfigError,
            "DataQualityError": _DataQualityError,
            "CriticalDataError": _CriticalDataError,
            "FrameCountMismatchError": _FrameCountMismatchError,
            "ResourceError": _ResourceError,
            "raise_field_not_found_error": _raise_field_not_found_error,
            "raise_frame_count_error": _raise_frame_count_error,
        }[name]

    if name in {
        "get_video_frame_count",
        "get_h5_frame_count",
        "get_h5_all_frame_counts",
        "get_json_frame_count",
        "get_mcap_frame_count",
        "align_frame_counts",
        "FrameAlignmentStrategy",
        "get_frame_count_auto",
    }:
        from .frame_count_utils import (
            FrameAlignmentStrategy as _FrameAlignmentStrategy,
        )
        from .frame_count_utils import (
            align_frame_counts as _align_frame_counts,
        )
        from .frame_count_utils import (
            get_frame_count_auto as _get_frame_count_auto,
        )
        from .frame_count_utils import (
            get_h5_all_frame_counts as _get_h5_all_frame_counts,
        )
        from .frame_count_utils import (
            get_h5_frame_count as _get_h5_frame_count,
        )
        from .frame_count_utils import (
            get_json_frame_count as _get_json_frame_count,
        )
        from .frame_count_utils import (
            get_mcap_frame_count as _get_mcap_frame_count,
        )
        from .frame_count_utils import (
            get_video_frame_count as _get_video_frame_count,
        )
        return {
            "get_video_frame_count": _get_video_frame_count,
            "get_h5_frame_count": _get_h5_frame_count,
            "get_h5_all_frame_counts": _get_h5_all_frame_counts,
            "get_json_frame_count": _get_json_frame_count,
            "get_mcap_frame_count": _get_mcap_frame_count,
            "align_frame_counts": _align_frame_counts,
            "FrameAlignmentStrategy": _FrameAlignmentStrategy,
            "get_frame_count_auto": _get_frame_count_auto,
        }[name]

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
