# 智平方压缩视频格式支持

## 📋 概述

智平方数据集现在支持一种新的压缩视频存储格式，该格式使用 `video` + `video_index` 字段替代传统的 `images` 数组，大幅减少存储空间。

## 🔍 格式特征

### 传统格式
```
observations/camera/rgb/head/images: shape=(327, H, W, 3), dtype=uint8
```

### 压缩视频格式
```
observations/camera/rgb/head/images: shape=(0,), dtype=float64          # 空数组
observations/camera/rgb/head/video: shape=(), dtype=|V792479            # 压缩视频数据
observations/camera/rgb/head/video_index: shape=(34,), dtype=int64      # 帧索引
```

## 🎯 关键特点

1. **压缩存储**: 使用 MP4/H264 压缩，大幅减少存储空间
2. **降采样**: 图像帧率低于机械臂数据（例如：10 视频帧 vs 327 机械臂数据帧）
3. **自动检测**: 转换器自动检测并处理压缩视频格式
4. **透明解码**: 对用户透明，无需修改配置文件

## 🔧 技术实现

### 数据结构

- **video**: `numpy.void` 类型的标量，存储完整的 MP4 视频数据
- **video_index**: 长度为 N+1 的数组，其中 N 是某种帧映射（具体用途待确认）
- **images**: 空数组，仅保留字段兼容性

### 解码流程

```python
# 1. 检测格式
if 'video' in buffer and 'video_index' in buffer:
    # 使用压缩视频格式

# 2. 提取字节数据
video_bytes = np.array(video_data).tobytes()

# 3. 临时文件解码
with tempfile.NamedTemporaryFile(suffix='.mp4') as tmp:
    tmp.write(video_bytes)
    cap = cv2.VideoCapture(tmp.name)
    
    # 4. 帧映射（最近邻插值）
    video_frame_idx = int(arm_frame_idx * total_video_frames / total_arm_frames)
    
    # 5. 读取帧
    cap.set(cv2.CAP_PROP_POS_FRAMES, video_frame_idx)
    ret, frame = cap.read()
    
    # 6. BGR → RGB
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
```

### 帧映射策略

由于视频帧数少于机械臂数据帧数，使用**最近邻插值**：

```
机械臂帧 → 视频帧
    0    →    0
  100    →    3
  200    →    6
  326    →    9
```

计算公式：
```python
video_frame = min(int(arm_frame * video_frames / arm_frames), video_frames - 1)
```

## 📊 性能对比

| 格式 | 存储大小 | 帧率 | 特点 |
|------|----------|------|------|
| 传统格式 | ~300MB/episode | 30 FPS | 无损，完整帧率 |
| 压缩视频格式 | ~3MB/episode | ~3 FPS | 有损压缩，降采样 |

## 🚀 使用方法

### 1. 确认格式

检查 H5 文件是否使用压缩视频格式：

```bash
python3 -c "
import h5py
with h5py.File('your_file.h5', 'r') as f:
    has_video = 'observations/camera/rgb/head/video' in f
    has_images = f['observations/camera/rgb/head/images'].shape[0] > 0
    print(f'压缩视频格式: {has_video and not has_images}')
"
```

### 2. 使用现有配置

压缩视频格式使用与传统格式**相同的配置文件**：

```yaml
# 例如：对于双臂机器人，有 pose 数据
version: dual_arm_with_pose
device_model_version: dual_arm_with_pose
```

配置选择：
- **双臂 + pose**: `dual_arm_with_pose`
- **双臂无 pose**: `dual_arm_no_pose`
- **单左臂 + pose**: `left_arm_with_pose`
- **单右臂 + pose**: `right_arm_with_pose`

### 3. 运行转换

```bash
# 更新数据库
python scripts/annotation/device_model_annotation.py <path_to_datasets.db>

# 运行转换（自动检测格式）
# 转换器会自动识别并处理压缩视频格式
```

## ⚠️ 注意事项

1. **帧率降低**: 视频帧率低于机械臂数据，部分细节可能丢失
2. **有损压缩**: MP4 压缩会引入压缩伪影
3. **性能开销**: 每次读取需要解码视频，比直接读取数组慢
4. **临时文件**: 解码过程会创建临时文件（自动清理）

## 🐛 已知问题

1. **硬编码帧数**: 当前代码中机械臂数据帧数（327）是硬编码的，后续应从 H5 文件动态获取
2. **video_index 用途未明**: video_index 数组的确切用途尚未完全理解
3. **内存开销**: 每次解码都会创建临时文件，频繁访问时可能影响性能

## 🔮 未来改进

1. **缓存机制**: 缓存解码后的视频帧，避免重复解码
2. **动态帧数**: 从 H5 文件或配置中获取机械臂数据帧数
3. **并行解码**: 支持多进程并行解码，提高转换速度
4. **更好的插值**: 使用双线性或三次插值代替最近邻

## 📚 相关文件

- **转换器**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5.py`
- **配置文件**: `scripts/format_converters/tolerobot/configs/converter_config_zhipingfang_*.yaml`
- **测试数据**: `/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/公共服务/`

## 📞 问题反馈

如遇到问题，请提供：
1. H5 文件路径
2. 错误日志
3. H5 文件结构（使用 `h5dump` 或 `h5py` 检查）

---

**最后更新**: 2025-10-15
**版本**: 1.0.0
