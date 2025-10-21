# 完整调用链分析与兼容性检查

## 目标
从用户命令行启动开始，追溯所有代码调用路径，发现潜在的兼容性问题。

## 场景 1：正式转换（不带 --is-test）

### 用户命令
```bash
python scripts/format_converters/tolerobot/server.py \
    --db-file=db/datasets.db \
    --host=172.16.18.160 \
    --port=8765 \
    --converter-factory-config-path=scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --convert-root-path=/mnt/nas/robocoin-datasets \
    --specific-device-model=realman_rmc_aidal
```

注意：**没有 --is-test 参数，所以 is_test=False（默认值）**

### 调用链追溯

#### 1. server.py 入口
```python
# scripts/format_converters/tolerobot/server.py
args = argparser.parse_args()  # is_test 默认 False

server = LeFormatConverterTaskServer(
    is_test=args.is_test,  # ✅ is_test=False
    ...
)

await server.start()
```

#### 2. LeFormatConverterTaskServer 初始化
```python
# src/robocoin_dataset/format_converter/tolerobot/server.py
class LeFormatConverterTaskServer:
    def __init__(self, is_test: bool = False, ...):
        self.is_test = is_test  # ✅ 保存 False
```

#### 3. 创建任务（create_task）
```python
def create_task(...) -> dict:
    task_content = {
        ...
        IS_TEST: self.is_test,  # ✅ 传递 False
    }
    return task_content
```

#### 4. Client 接收任务
```bash
python scripts/format_converters/tolerobot/multi_client.py \
    --host=172.16.18.160 \
    --port=8765
```

```python
# src/robocoin_dataset/format_converter/tolerobot/client.py
is_test = task_content.get(IS_TEST, False)  # ✅ 获取 False

for task, ep_idx, global_ep in tqdm(
    converter.convert(is_test),  # ✅ 调用 converter.convert(False)
    ...
):
```

#### 5. Converter 执行
```python
# src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py
def convert(self, is_test: bool = False):
    if not is_test:
        dataset = self._create_lerobot_dataset()  # ✅ 正常模式：创建 dataset
    
    for task_path, task in self.path_task_dict.items():
        episodes_num = self._get_task_episodes_num(task_path)
        if is_test:
            episodes_num = 1  # ⚠️ 不执行，因为 is_test=False
        
        for task_ep_idx in range(episodes_num):  # ✅ 处理所有 episode
            images_buffer, states_buffer, actions_buffer = self._prepare_episode_buffers(
                task_path, task_ep_idx, is_test=is_test  # ✅ 传递 False
            )
```

#### 6. 准备 Buffer（智能调用）
```python
def _prepare_episode_buffers(self, task_path, ep_idx, is_test=False):
    import inspect
    
    def smart_call(method, task_path, ep_idx, is_test):
        sig = inspect.signature(method)
        if 'is_test' in sig.parameters:
            return method(task_path=task_path, ep_idx=ep_idx, is_test=is_test)
        return method(task_path=task_path, ep_idx=ep_idx)  # ✅ 旧 converter 走这里
```

**关键问题检查点：**
- ✅ 旧 converter（无 is_test 参数）：调用 `method(task_path, ep_idx)`，不报错
- ✅ 新 converter（有 is_test 参数）：调用 `method(task_path, ep_idx, is_test=False)`，正常执行

---

## 场景 2：测试模式（带 --is-test）

### 用户命令
```bash
python scripts/format_converters/tolerobot/server.py \
    --db-file=db/datasets.db \
    --host=127.0.0.1 \
    --port=8766 \
    --convert-root-path=/tmp/test_output \
    --specific-device-model=realman_rmc_aidal \
    --is-test
```

注意：**有 --is-test 参数，所以 is_test=True**

### 调用链追溯

#### 1-4. 同上，is_test=True 传递

#### 5. Converter 执行（Test 模式）
```python
def convert(self, is_test: bool = True):  # ✅ is_test=True
    if not is_test:
        dataset = self._create_lerobot_dataset()  # ⚠️ 不执行！
    # ❗ 关键：不创建 dataset，不创建 AsyncImageWriter，不创建 semaphore
    
    for task_path, task in self.path_task_dict.items():
        episodes_num = self._get_task_episodes_num(task_path)
        if is_test:
            episodes_num = 1  # ✅ 只处理 1 个 episode
        
        for task_ep_idx in range(1):  # ✅ 只循环 1 次
            images_buffer, states_buffer, actions_buffer = self._prepare_episode_buffers(
                task_path, task_ep_idx, is_test=True  # ✅ 传递 True
            )
```

#### 6. MCAP Converter（特殊优化）
```python
# lerobot_format_converter_mcap.py
class LerobotFormatConverterRealmanRmcAidalMcap:
    def __init__(self, ...):
        self._is_test_mode = False  # 实例标志
        self._test_mode_frames = 10
    
    def convert(self, is_test: bool = True):
        self._is_test_mode = is_test  # ✅ 设置标志
        yield from super().convert(is_test=is_test)
    
    def _prepare_episode_images_buffer(self, task_path, ep_idx, is_test=True):
        if is_test:
            # ✅ 只解析 10+timeline_offset 帧
            max_frames = 10 + timeline_offset
            return self._get_episode_data_minimal(task_path, ep_idx, max_frames)
        # 正常模式：解析全部
    
    def _get_episode_frames_num(self, task_path, ep_idx):
        if self._is_test_mode:
            return self._test_mode_frames  # ✅ 返回 10，限制循环
        # 正常模式：统计完整帧数
```

**Test 模式优化效果：**
- ✅ 不创建 LeRobotDataset → 不创建 AsyncImageWriter → 不创建 semaphore
- ✅ 只处理 1 个 episode
- ✅ MCAP 只解析 11 帧（而不是 8348 帧）
- ✅ 不调用 `dataset.add_frame()` 和 `dataset.save_episode()`
- ✅ 快速验证配置和代码正确性

---

## 潜在问题检查清单

### ✅ 已解决的问题
1. **方法签名不兼容**：使用 `inspect.signature()` 智能调用，支持新旧 converter
2. **MCAP 资源泄漏**：Test 模式只解析少量帧
3. **数据库参数错误**：移除了 `convert_version_uuid`

### ⚠️ 需要检查的问题
1. **其他 Converter 是否正确实现了必要方法？**
2. **是否有 Converter 在 buffer 准备阶段有资源泄漏？**
3. **所有 Converter 的 `_get_episode_frames_num()` 是否正确？**
4. **是否有 Converter 依赖了不存在的配置字段？**

---

## 下一步：逐个检查 Converter

需要检查的 15 个 converter：
1. ✅ LerobotFormatConverterRealmanRmcAidalMcap - 已修复
2. ❓ LerobotFormatConverterMmk2
3. ❓ LerobotFormatConverterLejuWaibu
4. ❓ LerobotFormatConverterJpgJson
5. ❓ LerobotFormatConverterMp4Json
6. ❓ LerobotFormatConverterH5Jpg
7. ❓ LerobotFormatConverterH5Mp4
8. ❓ LerobotFormatConverterG1
9. ❓ LerobotFormatConverterHdf5
10. ❓ LerobotFormatConverterRosbag
11. ❓ LerobotFormatConverterLerobot
12. ❓ 其他...

