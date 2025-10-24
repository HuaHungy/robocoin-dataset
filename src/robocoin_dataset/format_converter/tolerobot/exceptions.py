"""
异常类定义 - 用于转换器的分层错误处理

这个模块定义了转换器框架中使用的异常层次结构，用于区分不同类型的错误：
- 配置错误：需要立即停止并修正配置
- 数据质量错误：可以跳过并继续处理
- 严重数据错误：需要跳过整个episode

Created: 2025-10-21
Author: Refactoring Team
"""


class ConverterError(Exception):
    """转换器基础异常类
    
    所有转换器相关异常的基类
    """
    pass


class ConfigError(ConverterError):
    """配置错误异常
    
    当配置文件中指定的字段路径、数据类型、或其他配置项与实际数据不匹配时抛出。
    
    处理策略：立即停止转换，要求用户修正配置文件
    
    示例场景：
    - H5文件中不存在配置指定的路径
    - JSON中缺少配置要求的字段
    - 数据类型与配置不匹配（如期望数组但实际是标量）
    - 相机名称在配置中存在但视频文件中找不到
    
    Usage:
        raise ConfigError(
            f"配置错误: H5路径 '{h5_path}' 不存在\n"
            f"可用路径: {available_paths}\n"
            f"请检查配置文件中的 'h5_path' 字段"
        )
    """
    pass


class DataQualityError(ConverterError):
    """数据质量问题异常
    
    当个别帧或数据点存在质量问题但不影响整体转换时抛出。
    
    处理策略：记录警告日志，跳过该帧，继续处理其他数据
    
    示例场景：
    - 单个视频帧无法解码
    - 单个图像文件损坏
    - 某一帧的传感器数据缺失
    - JSON中某个时间戳的数据为null
    
    Usage:
        raise DataQualityError(
            f"帧 {frame_idx} 的图像文件损坏: {image_path}\n"
            f"将跳过此帧并继续处理"
        )
    """
    pass


class CriticalDataError(ConverterError):
    """严重数据错误异常
    
    当整个episode的数据不可用或有效数据不足时抛出。
    
    处理策略：跳过整个episode，记录警告，继续处理下一个episode
    
    示例场景：
    - H5文件中不同数据集的帧数严重不一致
    - 视频文件完全损坏无法打开
    - episode的有效帧数少于阈值（如<50%）
    - 所有相机的视频文件都缺失
    
    Usage:
        raise CriticalDataError(
            f"Episode {ep_idx} 的有效帧数仅 {valid_frames}/{total_frames} ({ratio:.1%})\n"
            f"低于最小阈值 50%，将跳过整个episode"
        )
    """
    pass


class FrameCountMismatchError(CriticalDataError):
    """帧数不匹配错误
    
    当不同数据源（视频、H5、JSON等）的帧数不一致时抛出。
    这是 CriticalDataError 的特殊情况。
    
    处理策略：在严格模式下可能升级为ConfigError，否则作为CriticalDataError处理
    
    示例场景：
    - MP4视频帧数与JSON数据长度不一致
    - H5文件内不同数据集的shape[0]不同
    - 多个相机的视频帧数差异过大
    
    Usage:
        raise FrameCountMismatchError(
            f"帧数不匹配:\n"
            f"  视频: {video_frames} 帧\n"
            f"  JSON: {json_frames} 帧\n"
            f"  差异: {abs(video_frames - json_frames)} 帧"
        )
    """
    pass


class ResourceError(ConverterError):
    """资源错误异常
    
    当系统资源不足或资源访问失败时抛出。
    
    处理策略：记录错误，可能需要人工干预
    
    示例场景：
    - 磁盘空间不足
    - 无法创建输出目录
    - 文件权限问题
    - 内存不足
    
    Usage:
        raise ResourceError(
            f"无法创建输出目录: {output_path}\n"
            f"错误: {e}\n"
            f"请检查磁盘空间和文件权限"
        )
    """
    pass


# 便利函数：根据场景自动选择异常类型

def raise_field_not_found_error(field_path: str, available_fields: list, data_source: str = "data"):
    """字段未找到时抛出ConfigError
    
    Args:
        field_path: 缺失的字段路径
        available_fields: 可用的字段列表
        data_source: 数据源描述（如"H5 file", "JSON"）
    """
    raise ConfigError(
        f"❌ 配置错误：字段路径不存在\n"
        f"   🔍 请求的路径：{field_path}\n"
        f"   📊 数据源：{data_source}\n"
        f"   📋 可用字段：\n" +
        "\n".join(f"      - {field}" for field in available_fields[:20]) +
        (f"\n      ... 还有 {len(available_fields) - 20} 个字段" if len(available_fields) > 20 else "") +
        f"\n\n💡 解决方案：\n"
        f"   1. 检查配置文件中的字段路径拼写\n"
        f"   2. 使用 diagnose_converter_config.py 工具检查配置\n"
        f"   3. 使用 discover_dataset_schema.py 查看数据集的完整结构"
    )


def raise_frame_count_error(frame_counts: dict, strict_mode: bool = False):
    """帧数不匹配时抛出合适的异常
    
    Args:
        frame_counts: {source_name: frame_count} 字典
        strict_mode: 是否为严格模式（前N个episode）
    
    Raises:
        ConfigError: 严格模式下
        FrameCountMismatchError: 非严格模式下
    """
    sources = list(frame_counts.keys())
    counts = list(frame_counts.values())
    
    error_msg = (
        f"❌ 帧数不一致\n"
        f"   📊 各数据源帧数：\n" +
        "\n".join(f"      {src}: {cnt} 帧" for src, cnt in frame_counts.items()) +
        f"\n   📈 最大值：{max(counts)}\n"
        f"   📉 最小值：{min(counts)}\n"
        f"   📏 差异：{max(counts) - min(counts)} 帧\n"
        f"\n💡 可能原因：\n"
        f"   1. 数据采集中断或不完整\n"
        f"   2. 不同数据源的采样率不同\n"
        f"   3. 文件损坏或传输不完整\n"
        f"\n💡 解决方案：\n"
        f"   1. 检查数据采集日志\n"
        f"   2. 重新采集该episode\n"
        f"   3. 如果差异很小（<5%），可能是正常的同步误差"
    )
    
    if strict_mode:
        error_msg = (
            f"⚠️ 严格模式：前几个episode发现帧数不一致，可能是配置错误\n\n" + error_msg +
            f"\n\n🔍 建议：\n"
            f"   如果这是普遍问题而非个别episode，请检查配置文件是否正确"
        )
        raise ConfigError(error_msg)
    else:
        raise FrameCountMismatchError(error_msg)

