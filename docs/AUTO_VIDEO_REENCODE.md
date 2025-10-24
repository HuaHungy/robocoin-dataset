# 自动视频重编码功能

## 📖 概述

为了解决视频编码兼容性问题（如AV1编码），我们实现了**自动视频重编码功能**，在转换过程中动态检测和修复视频编码问题，无需手动预处理。

## 🎯 解决的问题

### 问题背景

某些数据集（如 `galaxea_r1_lite:h5_mp4_version`）使用AV1编码，部分平台不支持硬件加速解码：

```
[av1 @ ...] Your platform doesn't suppport hardware accelerated AV1 decoding.
[av1 @ ...] Failed to get pixel format.
[av1 @ ...] Missing Sequence Header.
RuntimeError: Failed to read frame 0 from xxx.mp4
```

### 传统解决方案的问题

**方案1: 手动预处理**
```bash
# 需要手动重编码所有问题视频
ffmpeg -i input.mp4 -c:v libx264 -crf 23 output.mp4
```

❌ 缺点：
- 需要提前识别所有问题视频
- 占用额外磁盘空间
- 手动操作繁琐

**方案2: 集成到代码**
- 在 converter 中硬编码重编码逻辑

❌ 缺点：
- 增加代码复杂度
- 混淆数据处理和预处理逻辑
- 难以维护

## ✅ 新解决方案：动态自动重编码

### 核心思想

**"外部在转换函数动态调用"**：
- 不集成到核心代码
- 在运行时检测问题
- 自动调用外部ffmpeg
- 使用临时文件

### 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 尝试打开视频                                             │
│    ↓                                                        │
│    打开失败？                                               │
│    ├─ No → 正常使用                                         │
│    └─ Yes → 检查 auto_reencode                             │
│         ├─ False → 报错退出                                 │
│         └─ True → 进入步骤2                                 │
│                                                             │
│ 2. 自动重编码                                               │
│    • 检查 ffmpeg 是否可用                                   │
│    • 调用: ffmpeg -i input.mp4 -c:v libx264 output.mp4    │
│    • 保存到临时目录                                         │
│    • 缓存重编码结果                                         │
│    ↓                                                        │
│                                                             │
│ 3. 使用重编码后的视频                                       │
│    • 更新视频路径为临时文件                                 │
│    • 继续正常转换                                           │
│    ↓                                                        │
│                                                             │
│ 4. 转换完成后                                               │
│    • 临时文件保留在 /tmp/robocoin_reencoded/              │
│    • 可选：调用 cleanup() 清理                              │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 使用方法

### 方法1：通过 LazyVideoReader（推荐）

```python
from robocoin_dataset.format_converter.tolerobot.lazy_video_reader import LazyVideoReader

# 开启自动重编码
reader = LazyVideoReader(
    video_path="path/to/video.mp4",
    auto_reencode=True  # ← 关键参数
)

# 正常使用，自动处理编码问题
frame = reader[0]  # 如果视频有问题，会自动重编码
```

### 方法2：在 Converter 中启用

*（待实现：在 converter 配置中添加 auto_reencode 参数）*

```python
converter = LerobotFormatConverterH5Mp4(
    dataset_path=dataset_path,
    converter_config=config,
    auto_reencode=True  # ← 传递给所有 LazyVideoReader
)
```

### 方法3：直接使用 VideoReencoder

```python
from robocoin_dataset.format_converter.utils.video_reencoder import VideoReencoder

reencoder = VideoReencoder()

# 检查 ffmpeg 是否可用
if reencoder.check_ffmpeg_available():
    # 重编码单个视频
    success, output_path, error = reencoder.reencode_video(
        video_path=Path("problematic_video.mp4")
    )
    
    if success:
        print(f"✅ Re-encoded to: {output_path}")
    else:
        print(f"❌ Failed: {error}")
```

## 📊 特性

### 1. 智能检测

- **自动检测**：打开失败或帧读取失败时触发
- **单次尝试**：每个视频最多重编码一次
- **错误回退**：重编码失败则报告原始错误

### 2. 缓存机制

```python
# 第一次处理 video1.mp4
reader1 = LazyVideoReader("video1.mp4", auto_reencode=True)  # 触发重编码

# 第二次处理同一视频
reader2 = LazyVideoReader("video1.mp4", auto_reencode=True)  # 使用缓存，无需重编码
```

### 3. 临时文件管理

- **位置**: `/tmp/robocoin_reencoded/` 或自定义目录
- **命名**: `{original_name}_reencoded.mp4`
- **清理**: 可选，手动调用 `reencoder.cleanup()`

### 4. 配置选项

```python
reencoder = VideoReencoder(
    temp_dir=Path("/custom/temp/dir"),  # 自定义临时目录
    codec="libx264",                     # 视频编码器
    crf=23,                              # 压缩质量 (0-51)
    logger=my_logger                     # 自定义日志
)
```

## 💡 最佳实践

### 1. 何时启用 auto_reencode

✅ **推荐启用**：
- 处理来源不明的数据集
- 已知有编码兼容性问题
- 需要最大容错性

❌ **不推荐启用**：
- 数据集已验证兼容
- 性能要求极高（重编码耗时）
- 磁盘空间受限

### 2. 依赖检查

确保系统已安装 ffmpeg：

```bash
# 检查 ffmpeg
ffmpeg -version

# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg
```

### 3. 性能考虑

- **首次重编码**：耗时较长（取决于视频大小和时长）
- **后续使用**：从缓存读取，无额外开销
- **磁盘空间**：重编码后的文件通常比原文件小

## 🔍 调试

### 查看重编码日志

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("robocoin_dataset")

reader = LazyVideoReader(
    "video.mp4",
    auto_reencode=True,
    logger=logger
)

# 日志输出示例：
# ⚠️  Failed to open video: video.mp4. Attempting automatic re-encoding...
# 🔄 Re-encoding video: video.mp4
#    Codec: libx264, CRF: 23
# ✅ Re-encoding successful: video_reencoded.mp4
#    Original: 104.5 MB
#    Re-encoded: 89.3 MB
# ✅ Successfully re-encoded video, using: video_reencoded.mp4
```

### 查看缓存信息

```python
reencoder = VideoReencoder()
# ... 处理一些视频 ...

info = reencoder.get_cache_info()
print(f"Cached videos: {info['cached_videos']}")
print(f"Total size: {info['total_size_mb']:.2f} MB")
print(f"Temp dir: {info['temp_dir']}")
```

## 🐛 故障排除

### 问题1：ffmpeg not found

```
❌ Re-encoding failed: ffmpeg is not available. Please install ffmpeg.
```

**解决方案**：
```bash
# 安装 ffmpeg
sudo apt-get install ffmpeg  # Linux
brew install ffmpeg          # macOS
```

### 问题2：重编码超时

```
❌ Re-encoding failed: Re-encoding timeout (>5 minutes)
```

**原因**：视频文件过大或编码复杂度高

**解决方案**：
1. 手动预处理该视频
2. 增加超时时间（修改 `video_reencoder.py` 中的 `timeout` 参数）

### 问题3：磁盘空间不足

```
❌ Re-encoding failed: No space left on device
```

**解决方案**：
1. 清理临时目录：`reencoder.cleanup()`
2. 更改临时目录到更大的分区

## 📈 性能对比

### Galaxea 数据集示例

| 场景 | 传统方案 | 自动重编码 |
|------|---------|-----------|
| 预处理时间 | 5分钟（手动） | 0（无需预处理） |
| 转换时首次开销 | 0 | 首次+5分钟 |
| 转换时后续开销 | 0 | 0（缓存） |
| 磁盘占用 | 原始+重编码 | 仅重编码（临时） |
| 操作复杂度 | 高（需手动） | 低（自动） |

## 🎯 总结

自动视频重编码功能实现了：

✅ **无侵入性**：不修改核心转换逻辑  
✅ **自动化**：无需手动预处理  
✅ **智能**：仅在需要时触发  
✅ **高效**：缓存机制避免重复工作  
✅ **灵活**：可选启用/禁用  

**核心优势**：将视频编码问题从"必须提前处理"变为"运行时自动修复"，极大简化了工作流程。

## 📝 更新日志

- **2025-10-24**: 初始实现
  - 创建 `VideoReencoder` 类
  - 在 `LazyVideoReader` 中集成自动重编码
  - 添加缓存机制
  - 支持打开失败和帧读取失败两种场景

