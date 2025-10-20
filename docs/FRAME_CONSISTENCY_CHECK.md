# 帧数一致性检查 - 完整改进文档

## 📊 问题背景

在转换智平方数据集时发现IndexError：
```
IndexError: index 66 is out of bounds for axis 0 with size 66
```

**根本原因**：H5文件内不同数据集的帧数不一致
- `observations/timestamp`: 66帧
- `observations/arm/left/joints`: 184帧
- 转换器使用第一个数据集判断总帧数，访问其他数据集时越界

---

## 🔧 已完成的改进

### 1. ✅ 智平方 H5转换器 - 添加严格检查

**文件**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5.py`

**修改**: `_get_episode_frames_num()` 函数（第761行）

**新功能**:
- 检查所有 `sub_state` 的 `h5_path` 帧数
- 如果帧数不一致，立即抛出详细错误
- 错误信息包含：
  - 完整文件路径
  - 任务名和episode索引
  - 每个数据集的帧数对比
  - 可执行的修复命令

**策略**: **严格模式 - 直接报错**
- 理由：H5文件内数据应该同步写入，不一致说明数据采集有严重问题

**示例错误**:
```
❌ H5数据集帧数不一致（数据质量问题）
   🗂️  文件: 0629_a.h5
   📁 完整路径: /mnt/nas/.../算法采集_PCB/.../0629_a.h5
   📍 任务: 算法采集_PCB
   📍 Episode索引: 198
   
   📊 参考帧数（来自 sub_state[0]）:
    observations/arm/left/joints: 184 帧
   
   ❌ 以下数据集帧数不一致:
    sub_state[4] observations/timestamp: 66 帧
   
   🔧 解决方案：
      1. 移动此文件到 error/ 文件夹：
         mkdir -p '/path/to/error'
         mv '/path/to/file.h5' '/path/to/error/'
```

---

### 2. ✅ 智平方预验证器 - 添加帧数检查

**文件**: `scripts/dataset_statistics/zhipingfang_preconversion_validator_v2.py`

**修改**: `_validate_episode_worker()` 函数（第498行）

**新功能**:
- 检查所有H5数据集的帧数
- 跳过视频压缩数据（shape=()）
- 跳过空数据集（未使用的arm）
- 如果帧数不一致，添加到errors列表

**验证逻辑**:
```python
# 收集帧数
frame_counts = {}
for path in required_h5_paths:
    if 'video' in path and shape == ():
        continue  # 视频压缩
    if shape[0] == 0:
        continue  # 空数据集
    frame_counts[path] = shape[0]

# 检查一致性
if len(set(frame_counts.values())) > 1:
    errors.append("帧数不一致: " + 详细信息)
```

---

### 3. ✅ 银河预验证器 - 添加帧数检查

**文件**: `scripts/dataset_statistics/yinhe_preconversion_validator_v2.py`

**修改**: `_validate_episode_worker()` 函数（第642行）

**新功能**:
- 检查所有视频的帧数（使用cv2）
- 检查所有JSON字段的帧数
- 对比视频与JSON的帧数

**策略**: **智能分级 - 区分轻微和严重不一致**
```python
if 差异 > 10%:
    errors.append("帧数不一致")  # 严重问题
else:
    warnings.append("轻微不一致")  # 可能是正常的同步误差
```

**理由**:
- MP4和JSON是独立采集的数据源
- ±1-2帧的差异是正常的同步误差
- 只有差异>10%才说明有严重问题

---

### 4. ✅ 银河转换器 - 已有保护机制

**文件**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_mp4_json.py`

**现状**: 第327行的 `_get_episode_frames_num()` 已经有完善的检查：
- ✅ 检查JSON各字段帧数
- ✅ 检查所有视频帧数
- ✅ 使用最小帧数（截断策略）
- ✅ 输出详细的Warning日志

**无需修改** - 已经足够robust

---

## 📋 各数据集策略对比

| 数据集 | 格式 | 转换器策略 | 预验证器策略 |
|--------|------|-----------|-------------|
| **智平方** | H5 | 严格报错 | 严格检查 |
| **银河** | MP4+JSON | 使用最小值+Warning | 分级检查（>10%报错） |
| **软通** | H5 | 严格报错 | 待添加 |
| **瑞曼** | H5 | 严格报错 | 待添加 |
| **格拉西亚** | MCAP | 待检查 | 待添加 |
| **乐聚** | 外部格式 | 待检查 | 待添加 |

---

## 🎯 使用建议

### 智平方数据集

**推荐流程**：直接运行转换器，边转换边修复

```bash
# 启动转换
cd scripts/format_converters/tolerobot
python3 server.py

# 另一终端启动客户端
python3 multi_client.py --device-model zhipingfang

# 遇到错误时：
# 1. 复制错误信息中的 mkdir 和 mv 命令
# 2. 执行命令移动问题文件到 error/
# 3. 继续转换
```

**为什么不用预验证器？**
- NAS文件系统扫描太慢
- 转换器错误信息已经足够详细
- 可以边转换边修复，不浪费时间

### 银河数据集

**推荐流程**：可以先预验证（如果时间允许）

```bash
# 预验证
python3 scripts/dataset_statistics/yinhe_preconversion_validator_v2.py \
  --dataset-path /path/to/yinhe \
  --workers 8 \
  --move-errors  # 自动移动严重不一致的episodes

# 然后转换
python3 convert2lerobot.py --device-model yinhe ...
```

**为什么可以预验证？**
- 银河预验证器读取视频帧数较快
- 可以提前发现>10%的严重不一致
- 轻微不一致（<10%）会被转换器自动处理

---

## 🔍 待办事项

### 其他H5格式数据集

需要为以下数据集的转换器和预验证器添加帧数检查：

1. **软通天擎** (ruantong)
   - [ ] 转换器：lerobot_format_converter_h5.py
   - [ ] 预验证器：ruantong_preconversion_validator_v2.py

2. **瑞曼** (realman)
   - [ ] 转换器：lerobot_format_converter_h5.py（同一个）
   - [ ] 预验证器：realman_preconversion_validator_v2.py

3. **格拉西亚** (galaxea)
   - [ ] 检查是否使用H5格式
   - [ ] 如果是，添加相应检查

### MCAP格式数据集

4. **乐聚** (leju)
   - [ ] 检查MCAP格式是否有类似问题
   - [ ] 如需要，添加topic消息数量一致性检查

---

## 📚 测试脚本

### 智平方
```bash
# 快速测试单个文件
python3 scripts/dataset_statistics/quick_test_frame_check.py

# 模拟转换器检查
python3 scripts/dataset_statistics/simulate_converter_check.py
```

### 银河
```bash
# 创建测试数据并验证
python3 scripts/dataset_statistics/test_yinhe_frame_check.py
```

---

## 🎓 经验教训

1. **预验证的价值**：能提前发现问题，但需要权衡扫描速度
2. **转换器防御性编程**：应该在读取数据时就检查一致性，而不是等到访问时才报错
3. **错误信息的重要性**：详细的错误信息（文件路径、具体数值、修复命令）能大大提高效率
4. **策略要因地制宜**：
   - H5格式：严格报错（数据应该同步）
   - MP4+JSON：智能截断（多数据源可能有微小差异）

---

最后更新：2025-10-20
作者：GitHub Copilot
