# MCAP Test 模式 Semaphore 泄漏问题分析

## 问题描述
Realman MCAP 数据集在 test 模式 (`is_test=True`) 下仍然出现 semaphore 资源泄漏：
```
/usr/lib/python3.10/multiprocessing/resource_tracker.py:224: UserWarning: 
resource_tracker: There appear to be 8 leaked semaphore objects to clean up at shutdown
```

## 执行流程分析

### Test 模式下的调用链（当前实现）

```
convert(is_test=True)
├── episodes_num = 1  ✅ 只处理 1 个 episode
├── _prepare_episode_buffers()
│   ├── _prepare_episode_images_buffer()
│   │   └──  _get_episode_data() ❌ 触发完整解析！
│   │       └── _parse_mcap_episode()
│   │           ├── 读取所有 topic 消息
│   │           ├── 解码所有图像 (7443 帧 × N 个相机)
│   │           ├── 解析所有状态数据
│   │           └── 解析所有动作数据
│   ├── _prepare_episode_states_buffer()
│   │   └── _get_episode_data() ✅ 使用缓存，不重复解析
│   └── _prepare_episode_actions_buffer()
│       └── _get_episode_data() ✅ 使用缓存，不重复解析
└── _gen_episode_frames()
    ├── _get_episode_frames_num() ✅ 已修复：快速统计，不解析图像
    └── for frame_idx in range(frames):
        └── _get_lerobot_datas() ✅ 从缓存读取，不重复解析
```

### 问题根源

**`_parse_mcap_episode()` 会解码所有图像**（line 383-517）：
```python
def _parse_mcap_episode(self, mcap_file: Path) -> dict[str, Any]:
    ...
    # 解析图片（对齐主topic时间戳）
    images = {cam: [] for cam in image_topics.values()}
    decode_progress_step = max(1, frames // 10)
    
    for i, t in enumerate(main_times):  # ❌ 循环所有 7443 帧！
        for topic, cam_name in image_topics.items():
            nearest = find_nearest_msg(topic_msgs[topic], t)
            img_arr = decode_image_bytes(nearest, self.typestore)  # ❌ 解码图像！
            images[cam_name].append(img_arr)
```

即使是 test 模式，只要调用 `_prepare_episode_buffers()`，就会：
1. 解码所有 7443 帧的所有相机图像
2. 占用大量内存（可能 GB 级别）
3. 可能触发某些多进程资源（PIL、numpy、ROS typestore）

## 为什么会有 Semaphore 泄漏？

可能的来源：
1. **PIL/Pillow 图像解码**：`decode_image_bytes()` 使用 PIL.Image.open()
2. **ROS TypeStore**：`self.typestore` 可能有后台进程
3. **NumPy 内存映射**：大数组可能使用共享内存
4. **MCAP Reader**：`make_reader()` 可能创建资源

**但关键问题是**：在 test 模式下，我们根本不需要 `LeRobotDataset`（没有创建），所以 semaphore 不应该来自 `AsyncImageWriter`。

## 真正的根源：不是 AsyncImageWriter！

重新审视：
- Test 模式下 `dataset = None`（没有创建 LeRobotDataset）
- AsyncImageWriter 只在 LeRobotDataset 中使用
- 但仍然有 semaphore 泄漏

**结论**：Semaphore 来自 **MCAP 解析过程本身**，不是 LeRobotDataset！

可能的泄漏源：
1. **PIL.Image 的内部机制**
2. **ROS TypeStore 的多进程支持**
3. **MCAP Reader 的并发处理**

## 解决方案

### 方案 1：在 MCAP converter 中重写 convert() ❌ 不推荐
理由：破坏了继承体系，重复代码

### 方案 2：优化 _parse_mcap_episode() ✅ 推荐
在 test 模式下只解析前 10 帧，不解码图像

### 方案 3：添加清理机制 ✅ 推荐
在 MCAP converter 的 `__del__` 或 convert 结束时清理资源

### 方案 4：父类支持 test 模式标志 ✅ 最佳
在父类 convert() 中传递 is_test 到 _prepare_episode_buffers()

## 推荐实现：方案 4

### 步骤 1：修改父类 `_prepare_episode_buffers` 签名

```python
# lerobot_format_converter.py
def _prepare_episode_buffers(self, task_path: Path, ep_idx: int, is_test: bool = False) -> tuple[any, any, any]:
    return (
        self._prepare_episode_images_buffer(task_path=task_path, ep_idx=ep_idx, is_test=is_test),
        self._prepare_episode_states_buffer(task_path=task_path, ep_idx=ep_idx, is_test=is_test),
        self._prepare_episode_actions_buffer(task_path=task_path, ep_idx=ep_idx, is_test=is_test),
    )
```

### 步骤 2：修改 convert() 传递 is_test

```python
images_buffer, states_buffer, actions_buffer = self._prepare_episode_buffers(
    task_path, task_ep_idx, is_test=is_test
)
```

### 步骤 3：MCAP converter 实现 test 模式优化

```python
# lerobot_format_converter_mcap.py
def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False) -> Any:
    if is_test:
        # Test 模式：只解析前 10 帧，返回模拟数据
        return self._get_minimal_episode_data(task_path, ep_idx, max_frames=10)["images"]
    else:
        # 正常模式：完整解析
        episode_data = self._get_episode_data(task_path, ep_idx)
        return episode_data["images"]
```

## 当前状态

✅ 已优化 `_get_episode_frames_num()`：快速统计帧数，不解码图像
❌ 仍未解决：`_prepare_episode_buffers()` 在 test 模式下仍会解码所有图像

## 下一步

实施方案 4：
1. 修改父类方法签名
2. 在 MCAP converter 中实现 test 模式优化
3. 可选：添加资源清理机制

---

**日期**：2025-10-21  
**问题**：MCAP test 模式 semaphore 泄漏  
**根源**：MCAP 解析过程中的资源创建，不是 AsyncImageWriter
