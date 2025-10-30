# 数据集转换错误解决方案总结

**日期**: 2025-10-30  
**问题**: 两个不同的转换失败案例  
**状态**: ✅ 已分析并提供解决方案

---

## 📋 问题概览

你遇到了**两个完全不同**的转换失败问题：

| 问题 | 数据集 | 错误类型 | 解决方案 |
|------|--------|---------|---------|
| 1️⃣ | 银河通用 | 数据质量问题 | ✅ **已修复** - 容错机制 |
| 2️⃣ | MMK2 | 配置错误 | ⏳ **需诊断** - 修正配置 |

---

## 1️⃣ 银河数据集问题 - 已修复 ✅

### **问题现象**
```python
IndexError: Frame index out of range in JSON data
   JSON path: 'cmd_body_joint'
   JSON data length: 0 (valid range: 0--1)
```

### **根本原因**
- JSON文件中某些字段完全为空
- 代码抛出 `IndexError` 未被容错机制捕获
- 导致整个任务失败

### **解决方案**
修改了 `lerobot_format_converter_mp4_json.py` 中的**5处异常**：

```python
# 修复前
raise IndexError("Frame index out of range...")

# 修复后
from robocoin_dataset.format_converter.tolerobot.exceptions import CriticalDataError
raise CriticalDataError("Frame index out of range (episode will be skipped)...")
```

### **修复的位置**
1. ✅ 第820行：JSON字段数据为空
2. ✅ 第748行：相机不存在
3. ✅ 第762行：相机帧数不足
4. ✅ 第810行：JSON数据类型错误
5. ✅ 第852行：JSON字段缺失

### **修复效果**
```
修复前 ❌:
  IndexError → 任务失败 → 数据集转换停止

修复后 ✅:
  CriticalDataError → Episode跳过 → 继续转换
  → 任务状态: COMPLETED (显示跳过统计)
```

### **下一步操作**
```bash
# 重新运行转换（问题episode会被自动跳过）
python scripts/format_converters/tolerobot/server.py \
    --db-file=db/datasets.db \
    --host=172.16.13.140 --port=8769

# 预期结果：
# ✅ 转换成功完成
# 📊 显示: Total: 10, Converted: 9, Skipped: 1
# 📝 error/corrupted_episodes.txt 记录跳过的episode
```

---

## 2️⃣ MMK2数据集问题 - 需诊断 ⏳

### **问题现象**
```python
ConfigError: 前3个episode失败率过高
  尝试转换: 34 episodes
  跳过: 31 episodes
  失败率: 91.2% (超过80%阈值)

错误: The feature 'action' of shape '(35,)' 
      does not have the expected shape '(37,)'.
```

### **根本原因**
- **配置文件期望**: 37维 action
- **实际数据**: 35维 action
- **差距**: 缺少2维

这是**配置错误**，不是数据质量问题！

### **为什么不应该容错？**

| 指标 | 银河数据集 | MMK2数据集 |
|------|-----------|-----------|
| 失败率 | <20% | **91.2%** |
| 失败模式 | 随机、偶发 | **系统性、一致** |
| 失败原因 | 多样 | **全部相同** |
| 根本原因 | 数据质量 | **配置不匹配** |
| 正确处理 | 容错跳过 | **修正配置** |

**关键判断**: 
> 如果80%的数据都"有问题"，那真正有问题的是配置，不是数据。

### **解决步骤**

#### Step 1: 诊断数据实际结构

我已经创建了诊断工具：

```bash
python scripts/diagnostics/diagnose_mmk2_dimensions.py \
    --episode-dir "/mnt/nas/synnas/docker/6discover_robotics_aitbot_mmk2/storage_peaches_and_pears/the left hand throws the peach into the left compartment, the right hand throws the pear into the right compartment./0"
```

**诊断工具会告诉你**：
- 实际的action维度构成
- 哪些组件存在/缺失
- 应该使用哪个配置

#### Step 2: 根据诊断结果处理

##### 场景A: 数据是37D（lite版本）✅
```bash
# 数据正确，只需更新数据库
UPDATE dmv_annotation 
SET device_model_version = 'third_view_lite'
WHERE dataset_uuid = 'xxx';
```

##### 场景B: 数据是39D（full版本）✅
```bash
# 数据正确，只需更新数据库
UPDATE dmv_annotation 
SET device_model_version = 'third_view_full'
WHERE dataset_uuid = 'xxx';
```

##### 场景C: 数据是35D（自定义版本）⚠️

需要创建新配置：

1. **创建配置文件**
   ```bash
   cd scripts/format_converters/tolerobot/configs
   cp converter_config_discover_robotics_aitbot_mmk2_third_view_lite.yaml \
      converter_config_discover_robotics_aitbot_mmk2_35d.yaml
   ```

2. **修改action部分**
   根据诊断结果调整维度（删除缺失的字段）

3. **更新工厂配置**
   在 `converter_factory_config.yaml` 添加：
   ```yaml
   discover_robotics_aitbot_mmk2:
   - version: 35d_version
     verison_description: mmk2 with 35D action
     module: robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_mmk2
     class: LerobotFormatConverterMmk2
     converter_config_path: converter_config_discover_robotics_aitbot_mmk2_35d.yaml
   ```

4. **更新数据库**
   ```sql
   UPDATE dmv_annotation 
   SET device_model_version = '35d_version'
   WHERE dataset_uuid = 'xxx';
   ```

#### Step 3: 重新转换

```bash
# Test模式验证
python scripts/format_converters/tolerobot/server.py \
    --is-test \
    --specific-device-model discover_robotics_aitbot_mmk2

# 正式转换
python scripts/format_converters/tolerobot/server.py \
    --db-file=db/datasets.db
```

---

## 📚 创建的文档和工具

### 1. **MP4_JSON_FAULT_TOLERANCE_FIX.md**
- 银河数据集问题分析
- 修复详情和验证方法
- 容错机制最佳实践

### 2. **MMK2_DIMENSION_MISMATCH_GUIDE.md**
- MMK2维度不匹配完整诊断指南
- 配置版本对比（full/lite/35d）
- 详细的解决步骤

### 3. **FAULT_TOLERANCE_VS_CONFIG_ERROR.md**
- 区分容错问题和配置错误
- 决策流程图
- 80%阈值的设计哲学

### 4. **scripts/diagnostics/diagnose_mmk2_dimensions.py**
- 快速诊断工具
- 自动分析action维度
- 提供配置建议

---

## 🎯 核心理念

### 容错机制的目的

```
✅ 处理数据质量问题
   - 个别文件损坏
   - 偶发的字段缺失
   - 随机的采集错误

❌ 不是为了掩盖配置错误
   - 系统性的维度不匹配
   - 一致的路径错误
   - 大量的字段缺失
```

### 决策标准

| 失败率 | 判断 | 行动 |
|--------|------|------|
| 0-20% | 数据质量问题 | 容错，跳过episode |
| 20-80% | 需人工判断 | 分析具体情况 |
| 80-100% | 配置错误 | **停止，修正配置** |

---

## ✅ 立即行动清单

### 对于银河数据集（已修复）
- [ ] 重新运行转换
- [ ] 验证问题episode被跳过
- [ ] 检查 error/corrupted_episodes.txt
- [ ] 确认任务状态为 COMPLETED

### 对于MMK2数据集（需诊断）
- [ ] 运行诊断工具 `diagnose_mmk2_dimensions.py`
- [ ] 查看实际维度构成
- [ ] 根据结果选择正确配置
- [ ] 如果需要，创建35D配置
- [ ] 更新数据库 device_model_version
- [ ] Test模式验证
- [ ] 正式转换

---

## 💡 经验总结

### 1. 遇到大量失败不要急于容错
```
大量失败 → 先诊断 → 找根因 → 修配置
        ↓
     不是修代码
```

### 2. 容错机制有保护阈值
```
系统设计了80%阈值
    ↓
防止配置错误被掩盖
    ↓
节省计算资源
```

### 3. 使用诊断工具
```
猜测 ❌  →  诊断 ✅
    ↓          ↓
  修错了    修对了
```

---

## 📞 需要帮助？

### 查看相关文档
- `MP4_JSON_FAULT_TOLERANCE_FIX.md` - 银河问题详解
- `MMK2_DIMENSION_MISMATCH_GUIDE.md` - MMK2诊断指南
- `FAULT_TOLERANCE_VS_CONFIG_ERROR.md` - 概念区分
- `SERVER_CLIENT_FLOW_COMPLETE.md` - 系统流程

### 运行诊断工具
```bash
# MMK2维度诊断
python scripts/diagnostics/diagnose_mmk2_dimensions.py \
    --episode-dir /path/to/episode

# Schema发现
python scripts/dataset_schema_discovery/discover_dataset_schema.py \
    --dataset-path /path/to/dataset
```

### 联系支持
提供以下信息：
1. 诊断工具输出
2. 数据集路径
3. 使用的配置文件
4. 完整错误日志

---

**创建时间**: 2025-10-30  
**状态**: ✅ 银河已修复 | ⏳ MMK2需诊断  
**下一步**: 运行诊断工具确认MMK2实际维度

