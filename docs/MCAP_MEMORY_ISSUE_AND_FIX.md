# MCAP转换内存问题与解决方案

> 问题时间: 2025-10-24  
> 影响: realman_rmc_aidal:mcap_version 数据集转换导致系统卡死  
> 严重程度: 🔥🔥🔥 高危

## 📋 问题描述

用户报告在转换 `realman_rmc_aidal:mcap_version` 数据集时，电脑直接卡死无响应。

## 🔍 问题分析

### 数据集信息
```
文件: GroceryStore_Restrocking_Fallen_20251012_104159_192_168_10_124_0.mcap
大小: 6.7 GB
位置: data/realman_rmc_aidal:mcap_version/GroceryStore_Restrocking_Fallen_20251012_104159_192_168_10_124/
```

### 根本原因

**MCAP converter存在严重的内存管理问题**，导致6.7GB文件无法转换：

#### 问题1: 一次性加载所有消息到内存

**代码位置**: `lerobot_format_converter_mcap.py` Line 527-530

```python
for schema, channel, message in reader.iter_messages():
    topic = channel.topic
    if topic in topic_msgs:
        topic_msgs[topic].append((message.log_time, message.data))
        #                         ↑
        #                         所有消息（包括所有图像字节）都被加载到内存
```

**影响**:
- 6.7GB文件包含大量图像消息
- 所有消息一次性加载到 `topic_msgs` 字典
- 预计内存占用：~13-20GB

#### 问题2: 缓存整个Episode数据

**代码位置**: `lerobot_format_converter_mcap.py` Line 678-684

```python
def _get_episode_data(self, task_path: Path, ep_idx: int) -> dict:
    cache_key = (str(task_path), ep_idx)
    if cache_key not in self._episode_data_cache:
        mcap_file = self._get_episode_mcap_file(task_path, ep_idx)
        self._episode_data_cache[cache_key] = self._parse_mcap_episode(mcap_file)
        #                                      ↑
        #                                      整个episode数据永久保留在内存中
    return self._episode_data_cache[cache_key]
```

**影响**:
- 解析后的数据（包括所有解码的图像）保留在内存
- 缓存大小：~20-30GB（解码后的图像占用更多空间）
- 对于单episode数据集，缓存没有意义但仍然占用内存

#### 问题3: 解码所有图像到内存

**代码位置**: `lerobot_format_converter_mcap.py` Line 550-564

```python
for i, t in enumerate(main_times):
    for topic, cam_name in image_topics.items():
        img_bytes = find_nearest_msg(topic_msgs[topic], t)
        if img_bytes is not None:
            img_arr = decode_image_bytes(img_bytes, self.typestore)
            #         ↑
            #         解码JPEG图像为RGB数组 (每张图~1-2MB)
            images[cam_name].append(img_arr)
```

**影响**:
- 假设3个相机，每相机1000帧，每帧1MB解码后
- 内存占用：3 × 1000 × 1MB = 3GB
- 加上原始消息数据：总计可能超过20GB

### 内存占用估算

```
原始MCAP文件:        6.7 GB
加载所有消息:       ~10 GB (包含压缩图像)
解码所有图像:       ~8 GB (RGB数组)
状态/动作数据:      ~0.5 GB
缓存开销:           ~2 GB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
总计预估:           ~27 GB

一般PC内存:         8-16 GB
结果:               OOM (Out of Memory) → 系统卡死
```

## ✅ 解决方案

### 方案1: 使用 is_test 模式（立即可用）

**推荐用于快速测试**

MCAP converter已支持test模式，只处理前10帧：

```bash
# 测试命令（10帧，~50MB内存）
PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
  --dataset_path data/realman_rmc_aidal:mcap_version \
  --output_path outputs/mcap_test \
  --device_model realman_rmc_aidal \
  --device_model_version mcap_version \
  --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
  --repo_id test/realman_mcap \
  --log_dir outputs/conversion_logs \
  --image_writer_processes 2 \
  --image_writer_threads 2 \
  --video_backend pyav \
  --is-test  # ← 关键参数

# 或使用测试脚本
bash scripts/test_mcap_safe.sh
```

**优点**:
- 内存占用小（~50-100MB）
- 快速验证配置正确性
- 避免系统卡死

**缺点**:
- 只处理10帧，无法完整转换

### 方案2: 禁用缓存（已修复）

**代码修改**: `lerobot_format_converter_mcap.py:_get_episode_data()`

```python
def _get_episode_data(self, task_path: Path, ep_idx: int) -> dict:
    """获取episode数据，使用缓存避免重复解析
    
    ⚠️ 对于大文件（>1GB）禁用缓存以避免内存溢出
    """
    cache_key = (str(task_path), ep_idx)
    mcap_file = self._get_episode_mcap_file(task_path, ep_idx)
    
    # 🆕 检查文件大小
    file_size_gb = mcap_file.stat().st_size / (1024**3)
    use_cache = file_size_gb < 1.0  # 只对小于1GB的文件使用缓存
    
    if not use_cache:
        if self.logger:
            self.logger.warning(
                f"⚠️  MCAP文件较大，禁用缓存避免内存溢出\n"
                f"📄 文件: {mcap_file.name}\n"
                f"📊 大小: {file_size_gb:.2f} GB"
            )
        # 直接解析，不使用缓存
        return self._parse_mcap_episode(mcap_file)
    
    # 小文件使用缓存
    if cache_key not in self._episode_data_cache:
        self._episode_data_cache[cache_key] = self._parse_mcap_episode(mcap_file)
    return self._episode_data_cache[cache_key]
```

**效果**:
- 减少内存占用：~27GB → ~17GB
- 仍然可能导致内存不足

### 方案3: 内存警告（已添加）

**代码修改**: `lerobot_format_converter_mcap.py:_parse_mcap_episode()`

```python
def _parse_mcap_episode(self, mcap_file: Path, max_frames: int | None = None) -> dict[str, Any]:
    # 🆕 内存警告：检查文件大小
    file_size_gb = mcap_file.stat().st_size / (1024**3)
    if file_size_gb > 2.0 and max_frames is None:
        if self.logger:
            self.logger.warning(
                f"⚠️  ⚠️  ⚠️  警告：正在解析大型MCAP文件！\n"
                f"📄 文件: {mcap_file.name}\n"
                f"📊 大小: {file_size_gb:.2f} GB\n"
                f"💾 预计内存占用: ~{file_size_gb * 2:.2f} GB (可能导致系统卡死)\n"
                f"💡 建议：\n"
                f"   1. 使用 --is-test 模式先测试（只处理10帧）\n"
                f"   2. 确保系统有足够内存（建议 >{file_size_gb * 3:.0f}GB）\n"
                f"   3. 考虑分割大文件"
            )
```

**效果**:
- 提前警告用户
- 避免用户盲目运行导致系统崩溃

### 方案4: 流式处理（未来优化）

**需要重构 `_parse_mcap_episode` 方法**

核心思路：
1. **不保存所有消息**：只保存时间戳索引
2. **按需解码**：转换时再从MCAP文件中读取特定消息
3. **分批处理**：将大episode分割为多个小批次

**伪代码**:
```python
def _parse_mcap_episode_streaming(self, mcap_file: Path) -> dict:
    # 第一遍：只收集时间戳索引（不保存消息内容）
    message_index = {}  # {topic: [(timestamp, file_offset), ...]}
    
    with open(mcap_file, "rb") as f:
        reader = make_reader(f)
        for schema, channel, message in reader.iter_messages():
            # 只保存时间戳和文件偏移量，不保存消息内容
            message_index[channel.topic].append((message.log_time, f.tell()))
    
    # 返回索引而非数据
    return {"message_index": message_index, "mcap_file": mcap_file}

def _get_frame_image_streaming(self, frame_idx: int, cam_name: str, message_index: dict):
    # 按需从MCAP文件中读取特定帧
    topic = self.cam_topic_map[cam_name]
    timestamp, offset = message_index[topic][frame_idx]
    
    with open(message_index["mcap_file"], "rb") as f:
        f.seek(offset)
        message = reader.read_message()  # 只读取这一条消息
        return decode_image_bytes(message.data)
```

**优点**:
- 内存占用最小（只保存索引，~100MB）
- 支持任意大小的MCAP文件

**缺点**:
- 需要大量文件IO（每帧都要读取文件）
- 转换速度可能较慢
- 需要重构现有代码

## 📊 修复效果对比

| 方案 | 内存占用 | 转换速度 | 实现难度 | 状态 |
|------|----------|----------|----------|------|
| 原始代码 | ~27GB | 快 | - | ❌ 系统卡死 |
| is_test模式 | ~50MB | 极快（10帧） | 无需修改 | ✅ 已支持 |
| 禁用缓存 | ~17GB | 快 | 简单 | ✅ 已修复 |
| 内存警告 | 无改善 | 无影响 | 简单 | ✅ 已添加 |
| 流式处理 | ~100MB | 中等 | 困难 | ⏳ 未来优化 |

## 🧪 测试步骤

### Step 1: is_test 模式测试（推荐）

```bash
# 使用测试脚本
bash scripts/test_mcap_safe.sh

# 预期结果：
# - 成功转换10帧
# - 内存占用 < 500MB
# - 转换时间 < 1分钟
```

### Step 2: 正式转换（需要大内存机器）

**⚠️ 系统要求**:
- 内存: ≥ 32GB
- 可用磁盘: ≥ 50GB
- CPU: ≥ 8核

```bash
PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
  --dataset_path data/realman_rmc_aidal:mcap_version \
  --output_path outputs/realman_mcap_full \
  --device_model realman_rmc_aidal \
  --device_model_version mcap_version \
  --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
  --repo_id test/realman_mcap_full \
  --log_dir outputs/conversion_logs \
  --image_writer_processes 4 \
  --image_writer_threads 4 \
  --video_backend pyav
  # 不加 --is-test，将转换全部帧
```

**预期**:
- 内存占用：17-20GB（禁用缓存后）
- 转换时间：30-60分钟
- 需要监控内存使用情况

## 💡 建议

### 短期方案（立即可用）
1. ✅ 使用 `--is-test` 模式验证配置
2. ✅ 在大内存机器上进行正式转换（≥32GB）
3. ✅ 监控系统内存和swap使用情况

### 中期方案（如需频繁转换大文件）
1. 考虑分割MCAP文件（按时间或帧数分割）
2. 在配置中只保留必要的topic
3. 降低图像分辨率或使用压缩格式

### 长期方案（系统优化）
1. 实现流式处理（方案4）
2. 支持分批转换
3. 优化内存管理（使用内存映射文件）

## 📝 相关文件

- **Converter实现**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_mcap.py`
- **测试脚本**: `scripts/test_mcap_safe.sh`
- **配置文件**: `scripts/format_converters/tolerobot/configs/converter_config_realman_rmc_aidal_mcap.yaml`

## 🎯 结论

**当前状态**:
- ✅ 问题已识别并记录
- ✅ 短期解决方案已实现（is_test + 禁用缓存 + 警告）
- ⏳ 长期优化方案待实现（流式处理）

**建议操作**:
1. 先使用 `--is-test` 模式测试（10帧，安全）
2. 如需完整转换，使用≥32GB内存的机器
3. 监控内存使用，如接近极限立即终止
4. 考虑数据预处理（分割文件）

---

**更新日期**: 2025-10-24  
**状态**: 已修复（短期方案）| 待优化（长期方案）

