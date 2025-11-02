# 配置文件版本选择指南

## 📋 概述

针对数据完整性差异，提供了两套配置文件（full/lite），自动处理不同数据版本。

---

## 🎯 核心原则

**选择策略**：根据**多数episode的数据完整性**决定配置版本

```
如果 > 50% 的episode有完整数据:
    使用 full 版本配置
    容错机制自动跳过少数不完整的episode
else:
    使用 lite 版本配置
    处理多数不完整的数据
```

---

## 📊 配置文件对比

### leju_waibu数据集

| 配置文件 | State维度 | Action维度 | 关键区别 | 适用场景 |
|---------|----------|-----------|---------|---------|
| `converter_config_leju_waibu_full.yaml` | 118维 | 54维 | observation.state使用`state/*`路径 | 有完整state数据的新版本 |
| `converter_config_leju_waibu_lite.yaml` | 54维 | 54维 | observation.state使用`action/*`路径 | 只有action数据的旧版本 |

**特殊说明**：
- leju的问题与yinhe/mmk2不同：不是部分字段缺失，而是**整个state部分缺失**
- Full版本：期望有独立的 `state/*` 路径（包含P1/P2扩展字段：effort、EEF、IMU等）
- Lite版本：将 `action/*` 当作 `state`（因为没有独立的state数据）
- **当前服务器大部分数据**：使用Lite版本（只有action，没有state）

### yinhe数据集

| 配置文件 | action维度 | 包含字段 | 适用场景 |
|---------|-----------|---------|---------|
| `converter_config_yinhe_full.yaml` | 16维 | head(2) + left_arm(7) + right_arm(7) | 完整数据（有head action） |
| `converter_config_yinhe_lite.yaml` | 14维 | left_arm(7) + right_arm(7) | 不完整数据（无head action） |

### mmk2数据集

| 配置文件 | action维度 | 包含字段 | 适用场景 |
|---------|-----------|---------|---------|
| `converter_config_discover_robotics_aitbot_mmk2_third_view_full.yaml` | 39维 | left_arm(6) + right_arm(6) + head(2) + spine(1) + hands(24) | 完整数据（有head action） |
| `converter_config_discover_robotics_aitbot_mmk2_third_view_lite.yaml` | 37维 | left_arm(6) + right_arm(6) + spine(1) + hands(24) | 不完整数据（无head action） |

---

## 🔍 如何判断使用哪个版本？

### 方法1：快速检查（推荐）

```bash
# leju_waibu数据集
cd /path/to/leju/dataset
python << 'EOF'
import h5py
from pathlib import Path

# 检查是否有state/*路径
episodes = list(Path('.').glob('*/proprio_stats.hdf5'))[:5]
has_state_count = 0

for ep in episodes:
    with h5py.File(ep, 'r') as f:
        # 检查是否有state/路径
        has_state = any(key.startswith('state/') for key in f.keys())
        if has_state:
            has_state_count += 1
            print(f"✅ {ep.parent.name}: 有state数据")
        else:
            print(f"❌ {ep.parent.name}: 只有action数据")

print(f"\n完整数据比例: {has_state_count}/{len(episodes)}")
if has_state_count > len(episodes)/2:
    print("推荐配置: full (多数episode有state数据)")
else:
    print("推荐配置: lite (多数episode只有action数据)")
EOF
```

```bash
# yinhe数据集
cd /path/to/yinhe/dataset
python << 'EOF'
import json
from pathlib import Path

# 检查前10个task的头部action
tasks = list(Path('.').glob('*/data.json'))[:10]
complete_count = 0

for task in tasks:
    with open(task) as f:
        data = json.load(f)
    if 'data' in data and 'cmd_head_joint_state' in data['data']:
        if len(data['data']['cmd_head_joint_state']) > 0:
            complete_count += 1

print(f"完整数据比例: {complete_count}/{len(tasks)}")
print(f"推荐配置: {'full' if complete_count > len(tasks)/2 else 'lite'}")
EOF
```

```bash
# mmk2数据集
cd /path/to/mmk2/dataset
python << 'EOF'
import bson
from pathlib import Path

# 检查前10个episode的头部action
episodes = list(Path('.').glob('*/episode_0.bson'))[:10]
complete_count = 0

for ep in episodes:
    with open(ep, 'rb') as f:
        doc = bson.decode_all(f.read())[0]
    if '/action/head/joint_state' in doc.get('data', {}):
        if len(doc['data']['/action/head/joint_state']) > 0:
            complete_count += 1

print(f"完整数据比例: {complete_count}/{len(episodes)}")
print(f"推荐配置: {'full' if complete_count > len(episodes)/2 else 'lite'}")
EOF
```

### 方法2：根据错误信息判断

**如果看到这些错误**，说明应该换配置：

```
# 使用full版本时报错 → 多数数据不完整，换lite
IndexError: cmd_head_joint_state长度=0
ValueError: action维度不匹配 (期望39, 实际37)

# 使用lite版本时 → 丢失了head信息，应该用full
⚠️ 跳过了多数episode（超过50%）
```

---

## 🛡️ 容错机制说明

### full版本 + 容错跳过

**工作原理**：
1. 使用full版本配置（包含所有字段）
2. 遇到episode缺失head数据时：
   - ✅ 自动跳过该episode
   - ✅ 继续处理其他episode
   - ✅ 不影响整体转换
   - ✅ 数据库记录跳过统计

**适用于**：
- 大多数episode有完整数据
- 只有少数episode（< 50%）缺失head

**优点**：
- ✅ 完整数据不丢失信息
- ✅ 自动处理不完整episode
- ✅ 无需手动筛选

### lite版本

**工作原理**：
1. 使用lite版本配置（删除head字段）
2. 所有episode按统一维度处理
3. 不会因head缺失而报错

**适用于**：
- 大多数episode缺失head数据
- 或整个task都没有head

**缺点**：
- ❌ 即使数据有head，也会被忽略
- ❌ 完整数据会丢失信息

---

## 📝 使用示例

### 场景1：本地新采集数据（完整）

```bash
# 数据特征：所有episode都有head action
# 推荐：使用full版本

# yinhe
python convert_script.py \
    --config converter_config_yinhe_full.yaml \
    --dataset /path/to/yinhe

# mmk2
python convert_script.py \
    --config converter_config_discover_robotics_aitbot_mmk2_third_view_full.yaml \
    --dataset /path/to/mmk2
```

### 场景2：服务器旧数据（多数不完整）

```bash
# 数据特征：大部分episode缺失head action
# 推荐：使用lite版本

# yinhe
python convert_script.py \
    --config converter_config_yinhe_lite.yaml \
    --dataset /path/to/yinhe

# mmk2
python convert_script.py \
    --config converter_config_discover_robotics_aitbot_mmk2_third_view_lite.yaml \
    --dataset /path/to/mmk2
```

### 场景3：混合数据（部分完整）

```bash
# 数据特征：60%有head，40%缺失
# 推荐：使用full版本 + 容错跳过

# 使用full版本，自动跳过40%不完整的episode
python convert_script.py \
    --config converter_config_yinhe_full.yaml \
    --dataset /path/to/yinhe

# 查看跳过统计
# 日志中会显示：
# "Skipped 40/100 episodes due to missing fields"
```

---

## 🔧 默认配置建议

**推荐设置**：

```bash
# 创建符号链接指向full版本（优先支持完整数据）
ln -sf converter_config_yinhe_full.yaml converter_config_yinhe.yaml
ln -sf converter_config_discover_robotics_aitbot_mmk2_third_view_full.yaml \
       converter_config_discover_robotics_aitbot_mmk2_third_view.yaml
```

**原因**：
- ✅ full版本通过容错机制兼容不完整数据
- ✅ 完整数据不会丢失信息
- ✅ 自动适应数据质量

---

## ⚠️ 注意事项

### 1. 跳过率监控

**正常情况**：
- 跳过率 < 10%：数据质量良好
- 跳过率 10-30%：部分数据质量问题
- 跳过率 30-50%：考虑检查数据采集

**异常情况**：
- 跳过率 > 50%：应该使用lite版本

### 2. 维度一致性

**重要**：同一个数据集的所有task必须使用相同配置版本

```bash
# ❌ 错误：混用配置
task1 → converter_config_yinhe_full.yaml  (16维)
task2 → converter_config_yinhe_lite.yaml  (14维)
# 会导致action维度不一致！

# ✅ 正确：统一配置
task1 → converter_config_yinhe_full.yaml  (16维)
task2 → converter_config_yinhe_full.yaml  (16维)
# 自动跳过task2中的不完整episode
```

### 3. 数据库一致性

配置变更后，已转换的数据需要重新转换，因为action维度已变化。

---

## 📚 技术细节

### 容错机制实现

```python
# src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py

def _convert_episode_with_fault_tolerance(...):
    try:
        # 准备episode数据（包括head字段）
        images_buffer, states_buffer, actions_buffer = \
            self._prepare_episode_buffers(task_path, task_ep_idx, is_test=is_test)
    except KeyError as e:
        # 捕获head字段缺失的情况
        if is_strict:
            # 严格模式：抛出错误
            raise ConfigError(...) from e
        else:
            # 非严格模式：跳过此episode
            self.logger.warning(f"Skipping episode due to missing field: {e}")
            return 0, 0  # 返回0帧，表示跳过
```

### 字段检测逻辑

```python
# lerobot_format_converter_mp4_json.py

def _get_episode_frames_num(...):
    # 1. 收集配置中使用的字段
    used_json_paths = {...}  # cmd_head_joint_state, cmd_left_joint_state, ...
    
    # 2. 统计每个字段的帧数
    for key, value in json_data['data'].items():
        if key in used_json_paths and len(value) > 0:
            json_frame_counts[key] = len(value)
    
    # 3. 如果某字段为空（len=0），不计入
    #    在访问时会触发KeyError，被容错机制捕获
```

---

## 🚀 快速开始

```bash
# 1. 检查数据完整性
cd /path/to/dataset
./check_data_completeness.sh  # 见上面的检查脚本

# 2. 选择配置
# 如果 > 50% 完整 → full版本
# 如果 < 50% 完整 → lite版本

# 3. 开始转换
python convert.py --config <选择的配置> --dataset /path/to/dataset

# 4. 检查跳过率
# 查看日志中的 "Skipped X/Y episodes"
# 如果跳过率 > 50%，考虑换lite版本
```

---

## 📞 问题排查

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| `IndexError: cmd_head_joint_state长度=0` | 使用full但数据不完整 | 1. 换lite版本<br>2. 或检查容错是否启用 |
| action维度不匹配 | 配置与数据不符 | 1. 检查数据完整性<br>2. 选择正确版本 |
| 跳过率 > 50% | full版本用于不完整数据 | 换lite版本 |
| 丢失head信息 | lite版本用于完整数据 | 换full版本 |

---

## 版本历史

- **2025-10-28**: 创建full/lite双版本配置，支持不同数据完整性
- **原因**: 发现本地数据（完整）与服务器数据（不完整）存在差异
- **数据源**: yinhe和mmk2数据集的不同采集版本

