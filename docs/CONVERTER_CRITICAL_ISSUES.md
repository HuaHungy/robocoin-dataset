# 🚨 Converter 代码审查 - 发现的严重问题

## 日期：2025-10-21

## 问题 1：视频类 Converter 的内存溢出风险 ⚠️⚠️⚠️

### 受影响的 Converter
1. **LerobotFormatConverterLejuWaibu** (`lerobot_format_converter_leju_waibu.py`)
2. **LerobotFormatConverterMp4Json** (`lerobot_format_converter_mp4_json.py`)
3. 可能还有其他使用 MP4/视频的 converter

### 问题描述
这些 converter 在 `_prepare_episode_images_buffer()` 中**将整个视频的所有帧加载到内存**：

```python
def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int):
    frames = []
    cap = cv2.VideoCapture(str(video_path))
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(frame_rgb)  # ❗ 累积所有帧到内存
    cap.release()
    images_buffer[cam_name] = frames  # ❗ 保存所有帧
    return images_buffer
```

### 内存占用计算

**假设场景**：
- Episode 长度：1000 帧（约 33 秒 @ 30 FPS）
- 相机数量：3 个
- 图像分辨率：1920×1080 (Full HD)
- 颜色通道：3 (RGB)

**单帧大小**：
```
1920 × 1080 × 3 bytes = 6,220,800 bytes ≈ 6.2 MB
```

**单相机内存**：
```
6.2 MB × 1000 frames = 6,200 MB ≈ 6.2 GB
```

**三相机总内存**：
```
6.2 GB × 3 cameras = 18.6 GB
```

**10 个 episode 并发处理**：
```
18.6 GB × 10 = 186 GB  ❗❗❗
```

### 实际影响

1. **正常转换模式**：
   - 单机转换可能导致内存不足（OOM）
   - 多 episode 并发处理会快速耗尽内存
   - 系统可能进入swap，性能急剧下降

2. **Test 模式**：
   - 即使只测试 1 个 episode，仍会加载所有帧
   - Test 模式失去"快速验证"的意义

3. **生产环境风险**：
   - Multi-client 并发处理时，多个 worker 同时加载视频
   - 可能导致整个转换集群崩溃

### 对比：H5 Converter 的正确做法

查看 `lerobot_format_converter_h5_mp4.py`：

```python
def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int):
    # 读取完整视频到内存（❌ 同样的问题！）
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return {cam: frames for cam in cameras}
```

**H5 Converter 也有同样问题！**

### 根本原因分析

#### 设计缺陷
当前架构假设：
1. Buffer 在 `_prepare_episode_buffers()` 中一次性准备好
2. 后续 `_get_frame_*()` 方法只是从 buffer 中读取

这个设计对于：
- ✅ **小数据**（如 BSON、JSON）：可以接受，数据量小
- ✅ **H5 文件**：numpy array 直接映射，不占额外内存
- ❌ **视频文件**：每帧都是独立的大图像，全部加载=灾难

#### 为什么 MCAP 没有这个问题？
MCAP converter 虽然也解析整个文件，但：
1. 解析后的数据是压缩的（CompressedImage messages）
2. 只在需要时才解码图像
3. 我们的优化让 test 模式只解析前 N 帧

### 建议的修复方案

#### 方案 A：延迟加载（Lazy Loading）- 推荐

修改视频 converter，不在 buffer 阶段加载帧：

```python
def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False):
    """只保存视频文件路径，不加载帧"""
    video_paths = {}
    for cam_name in cameras:
        video_path = self._get_video_file_path(task_path, ep_idx, cam_name)
        video_paths[cam_name] = {
            'path': video_path,
            'cap': None,  # VideoCapture 对象将在 _get_frame_image 中创建
            'frame_count': self._get_video_frame_count(video_path),
        }
    
    return video_paths

def _get_frame_image(self, task_path, ep_idx, frame_idx, args_dict, images_buffer):
    """按需读取视频帧"""
    cam_name = args_dict['cam_name']
    video_info = images_buffer[cam_name]
    
    # 打开视频（如果还没打开）
    if video_info['cap'] is None:
        video_info['cap'] = cv2.VideoCapture(str(video_info['path']))
    
    # 定位到目标帧
    cap = video_info['cap']
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    
    if not ret:
        raise ValueError(f"Failed to read frame {frame_idx}")
    
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
```

**优点**：
- 内存占用降低 1000 倍（只保存当前帧）
- Test 模式快速
- 支持大规模数据集

**缺点**：
- 需要修改多个 converter
- 视频随机访问可能较慢（需要 seek）

#### 方案 B：智能缓存（LRU Cache）

使用 LRU 缓存机制，只保留最近使用的帧：

```python
from functools import lru_cache

@lru_cache(maxsize=100)  # 只缓存最近 100 帧
def _get_cached_frame(video_path: str, frame_idx: int):
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise ValueError(f"Failed to read frame {frame_idx}")
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
```

**优点**：
- 实现简单
- 自动管理内存
- 对连续访问模式友好

**缺点**：
- 随机访问仍可能较慢
- LRU 大小需要调优

#### 方案 C：Test 模式特殊处理（临时方案）

在 test 模式下只加载前 N 帧：

```python
def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False):
    max_frames = 10 if is_test else None  # Test 模式只加载 10 帧
    
    frames = []
    cap = cv2.VideoCapture(str(video_path))
    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if is_test and frame_count >= max_frames:
            break  # Test 模式提前结束
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(frame_rgb)
        frame_count += 1
    
    cap.release()
    return frames
```

**优点**：
- 修改最小
- 快速解决 test 模式问题

**缺点**：
- 正常模式仍有内存问题
- 不是根本解决方案

### 推荐行动计划

1. **立即** - 方案 C：为所有视频 converter 添加 test 模式支持
   - 修改 `LejuWaibu`、`Mp4Json`、`H5Mp4` converter
   - 添加 `is_test` 参数
   - 限制加载帧数

2. **短期** - 方案 A：实现延迟加载
   - 重构视频 converter 的 buffer 机制
   - 测试性能影响
   - 逐步迁移

3. **长期** - 架构优化
   - 考虑统一的视频处理接口
   - 添加内存使用监控
   - 文档化最佳实践

---

## 问题 2：MCAP Converter 已修复 ✅

### 修复内容
1. 添加 `is_test` 参数支持
2. Test 模式只解析前 10+timeline_offset 帧
3. 使用实例标志 `_is_test_mode` 控制帧数
4. 重写 `convert()` 方法设置标志

### 验证结果
- ✅ Test 模式只解析 11 帧（而非 8348 帧）
- ✅ 没有 semaphore 泄漏警告
- ✅ 执行时间从分钟级降到秒级

---

## 问题 3：父类兼容性已修复 ✅

### 修复内容
使用 `inspect.signature()` 智能调用机制：

```python
def _prepare_episode_buffers(self, task_path, ep_idx, is_test=False):
    def smart_call(method, task_path, ep_idx, is_test):
        sig = inspect.signature(method)
        if 'is_test' in sig.parameters:
            return method(task_path=task_path, ep_idx=ep_idx, is_test=is_test)
        return method(task_path=task_path, ep_idx=ep_idx)
    
    return (
        smart_call(self._prepare_episode_images_buffer, task_path, ep_idx, is_test),
        smart_call(self._prepare_episode_states_buffer, task_path, ep_idx, is_test),
        smart_call(self._prepare_episode_actions_buffer, task_path, ep_idx, is_test),
    )
```

### 影响
- ✅ 新 converter（有 is_test）：正常工作
- ✅ 旧 converter（无 is_test）：兼容工作
- ✅ 不需要修改所有子类

---

## 待办事项

### 高优先级 🔴
- [ ] 为视频 converter 添加 is_test 支持（方案 C）
  - [ ] LejuWaibu converter
  - [ ] Mp4Json converter
  - [ ] H5Mp4 converter
  
### 中优先级 🟡
- [ ] 实现延迟加载机制（方案 A）
- [ ] 添加内存使用监控
- [ ] 文档化内存使用注意事项

### 低优先级 🟢
- [ ] 性能基准测试
- [ ] 优化视频读取性能
- [ ] 统一视频处理接口

