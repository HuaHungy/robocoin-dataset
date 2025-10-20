#!/usr/bin/env python3
"""
增强银河转换器的帧数检查：
如果帧数差异超过阈值（如10%），从Warning升级为Error
"""

# 建议的改进（伪代码）：
"""
在 lerobot_format_converter_mp4_json.py 的 _get_episode_frames_num 中：

# 当前逻辑（第395-423行）
if 帧数不一致:
    logger.warning(...)  # 只是警告
    return min_frames     # 继续使用最小值

# 建议改进：
if 帧数不一致:
    max_diff_ratio = (max_frames - min_frames) / max_frames
    
    if max_diff_ratio > 0.1:  # 差异超过10%
        raise ValueError(
            f"❌ 帧数差异过大（超过10%）！\\n"
            f"   这可能表示数据采集严重不同步\\n"
            f"   最小帧数: {min_frames}\\n"
            f"   最大帧数: {max_frames}\\n"
            f"   差异: {max_diff_ratio*100:.1f}%\\n"
            + 详细的源信息...
        )
    else:  # 差异在可接受范围内
        logger.warning(...)  # 只是警告
        return min_frames
"""

print(__doc__)
