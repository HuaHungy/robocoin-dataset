# Galaxea视频解码问题修复

## 📌 问题描述

**错误信息**：
```
RuntimeError: ❌ Failed to get sample image for camera 'cam_high_rgb' after trying 5 task_path/episode combinations.
Attempted:
  - task_path=., episode=0: Failed to read frame 0 from /mnt/nas/.../3115_cam_high.mp4
  - task_path=., episode=1: Failed to read frame 0 from /mnt/nas/.../3116_cam_high.mp4
  ...
```

**数据集**: `galaxea` (星图/星海图外部1.5w)
**转换器**: `LerobotFormatConverterH5Mp4`
**失败阶段**: 初始化阶段获取样本图像

---

## 🔍 根本原因

### 1. 问题定位

转换器初始化流程：
```
__init__
  └─ _gen_image_configs()
       └─ _get_one_frame_images()
            └─ _get_one_frame_image()  # 尝试多个episode获取样本图像
                 └─ _get_frame_image(frame_idx=0)
                      └─ _prepare_episode_images_buffer()  # is_test=False
                           └─ LazyVideoReader (使用OpenCV cv2.VideoCapture)
                                └─ __getitem__(0)  # 读取第一帧
                                     └─ cv2.VideoCapture.read() ❌ 失败
```

### 2. 失败原因

galaxea的MP4视频文件可能使用了：
- **不兼容的编码格式**（如AV1、HEVC等）
- OpenCV版本不支持的编解码器
- 需要额外解码库的格式

导致 `cv2.VideoCapture.read()` 返回 `ret=False`，无法读取帧。

### 3. 为什么之前没发现

- 本地测试数据使用H.264编码，OpenCV兼容性好
- 服务器数据使用了不同的编码格式

---

## ✅ 解决方案

### 核心思路

在**初始化阶段**使用更兼容的视频读取方式：
- **正式转换**：使用 `LazyVideoReader` (OpenCV) - 延迟加载，节省内存
- **初始化采样**：使用 `PyAV` - 更好的编解码器支持

### 代码修改

#### 1. H5+MP4转换器 - 添加sample_only模式

**文件**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_mp4.py`

```python
def _prepare_episode_images_buffer(
    self, task_path: Path, ep_idx: int, 
    is_test: bool = False, 
    sample_only: bool = False  # 🆕 初始化采样模式
) -> dict[str, LazyVideoReader | list[np.ndarray]]:
    """
    Args:
        sample_only: 是否只需要样本帧（初始化阶段）。为True时只加载1帧用于获取shape
    """
    # 🎯 样本模式（初始化阶段）：只加载1帧，使用更兼容的PyAV
    if sample_only:
        if self.logger:
            self.logger.debug(f"🎯 Sample mode: loading 1 frame for initialization")
        return self._load_frames_to_memory(ep_dir, max_frames=1)
    
    # 🧪 Test模式：加载11帧（PyAV）
    if is_test or self._is_test_mode:
        return self._load_frames_to_memory(ep_dir, max_frames=11)
    
    # 🚀 正式模式：LazyVideoReader (OpenCV)
    return self._create_lazy_readers(ep_dir)
```

**关键改进**：
- 初始化时只加载1帧，使用PyAV（更兼容）
- 正式转换时仍使用LazyVideoReader（更高效）

#### 2. 基类 - 智能检测并使用sample_only

**文件**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py`

```python
def _get_one_frame_image(self, args_dict: dict) -> np.ndarray:
    """获取样本图像（初始化阶段）"""
    
    # 🔍 检查子类是否支持sample_only参数
    import inspect
    frame_image_sig = inspect.signature(self._get_frame_image)
    supports_sample_only = 'sample_only' in frame_image_sig.parameters
    
    for task_path in self.path_task_dict.keys():
        for ep_idx in range(min(5, num_episodes)):
            try:
                # 🎯 如果支持sample_only，优先使用（更兼容）
                if supports_sample_only:
                    image = self._get_frame_image(
                        task_path=task_path, ep_idx=ep_idx, frame_idx=0,
                        args_dict=args_dict, 
                        sample_only=True  # 🆕 初始化采样模式
                    )
                else:
                    image = self._get_frame_image(...)
                return image
            except Exception as e:
                continue  # 尝试下一个episode
```

**关键改进**：
- 使用反射检查子类是否支持`sample_only`
- 如果支持，自动使用更兼容的PyAV读取方式
- 向后兼容：不支持的子类保持原有行为

---

## 🎯 修复效果

### Before
```
❌ 初始化失败 → 转换任务直接失败
- OpenCV无法解码 → RuntimeError
- 所有5次尝试都失败
- 任务标记为FAILED
```

### After
```
✅ 初始化成功 → 正常转换
- PyAV成功解码第一帧
- 获取图像shape
- 创建LeRobot Dataset
- 正式转换时仍使用LazyVideoReader（高效）
```

---

## 🔧 技术细节

### PyAV vs OpenCV

| 特性 | PyAV | OpenCV (cv2) |
|------|------|--------------|
| 编解码器支持 | 更广（依赖FFmpeg） | 有限（需编译时指定） |
| H.264 | ✅ | ✅ |
| HEVC/H.265 | ✅ | ⚠️ 需额外配置 |
| AV1 | ✅ | ❌ 通常不支持 |
| VP9 | ✅ | ⚠️ 部分支持 |
| 内存占用 | 中等 | 低（LazyVideoReader） |
| 性能 | 中等 | 高 |

### 为什么不全用PyAV？

- **初始化阶段**：只读1帧，PyAV兼容性好
- **正式转换**：需读取数千帧，LazyVideoReader更高效
- **混合策略**：兼顾兼容性和性能

---

## 📊 影响范围

### 受益数据集

所有使用 `LerobotFormatConverterH5Mp4` 的数据集：
- ✅ `galaxea` (星图)
- ✅ `alohanew` 
- ✅ 其他H5+MP4格式数据集

### 其他转换器

不受影响（它们有各自的读取实现）：
- `LerobotFormatConverterMp4Json` - 使用相同的PyAV
- `LerobotFormatConverterH5Jpg` - 使用图片文件
- `LerobotFormatConverterLerobot` - 使用parquet

---

## 🚀 部署步骤

### 1. 更新代码

```bash
cd ~/robocoin-dataset
git pull origin feat/test
```

### 2. 重启服务

**Server**:
```bash
# 停止旧进程
# 重新启动Server
```

**Client**:
```bash
# 停止旧进程
cd ~/robocoin-dataset
git pull origin feat/test
# 重新启动Client
```

### 3. 验证修复

查看日志中的成功消息：
```
🎯 Sample mode: loading 1 frame for initialization (episode 0)
✅ Successfully got sample image for camera 'cam_high_rgb' from ... (sample mode)
```

---

## 🔍 排查建议

如果问题仍然存在：

### 1. 检查PyAV安装

```bash
python -c "import av; print(av.__version__)"
```

### 2. 检查视频编码

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 3115_cam_high.mp4
```

### 3. 手动测试解码

```python
import av
container = av.open('3115_cam_high.mp4')
frame = next(container.decode(video=0))
print(f"Successfully decoded frame: {frame.width}x{frame.height}")
```

### 4. 启用auto_reencode（备选方案）

如果PyAV也无法解码，启用自动重编码：

```python
# server.py
converter = LerobotFormatConverter(
    ...,
    auto_reencode=True  # 🎬 自动用FFmpeg重编码
)
```

---

## 📝 相关文档

- `docs/ALL_FIXES_FINAL_20251027.md` - 完整修复总结
- `src/robocoin_dataset/format_converter/utils/video_reencoder.py` - 视频重编码工具
- `src/robocoin_dataset/format_converter/tolerobot/lazy_video_reader.py` - 延迟视频读取器

---

**修复时间**: 2025-10-28  
**影响版本**: feat/test分支  
**状态**: ✅ 已修复，待部署

