# 智平方数据集验证工具使用指南

## 概述

`zhipingfang_dataset_validator.py` 是用于验证智平方数据集完整性和一致性的工具。在正式转换之前，使用此工具可以自动检测和隔离有问题的数据文件。

## 功能特性

### 1. 自动发现数据集
- 查找所有 `device_model_annotation.yaml` 标记文件
- 索引同级及下一级目录中的所有 H5 文件

### 2. 数据完整性检查
- **非空数据检测**: 检查每个数据集是否包含实际数据（非零）
- **路径一致性**: 确认所有 H5 文件具有相同的数据集路径结构
- **Shape 自检**: 验证每个 H5 文件内部的数据形状一致性
- **少数服从多数**: 自动识别路径结构不一致的异常文件

### 3. 版本匹配检测
- 对比配置文件中的版本信息
- 当发现多种数据结构版本时发出警告
- 提示可能的配置错误

### 4. 异常文件处理
- 自动移动异常文件到 `error` 文件夹
- 保留原有目录结构（相对路径作为文件名）
- 避免污染正常转换流程

### 5. 详细报告生成
- 生成时间戳的 TXT 报告
- 包含统计摘要、异常文件列表、错误原因
- 完整执行日志便于问题排查

## 使用方法

### 基础用法

```bash
# 使用默认路径（/mnt/nas/synnas/docker2/外部数据/智平方）
python scripts/dataset_statistics/zhipingfang_dataset_validator.py
```

### 自定义路径

```bash
# 指定数据根目录
python scripts/dataset_statistics/zhipingfang_dataset_validator.py \
    --data-root /path/to/智平方

# 指定自定义 error 目录
python scripts/dataset_statistics/zhipingfang_dataset_validator.py \
    --data-root /path/to/智平方 \
    --error-dir /path/to/custom_error
```

### 测试模式（不移动文件）

```bash
# Dry-run 模式：只检测，不移动文件
python scripts/dataset_statistics/zhipingfang_dataset_validator.py --dry-run
```

## 输出结果

### 控制台输出

实时显示处理进度和结果：

```
[2025-10-19 12:00:00] [INFO] ================================================================================
[2025-10-19 12:00:00] [INFO] 步骤 1: 查找 device_model_annotation.yaml 文件
[2025-10-19 12:00:00] [INFO] ================================================================================
[2025-10-19 12:00:01] [INFO] 找到: 30k数采-第一批-20250930-32274条/device_model_annotation.yaml
[2025-10-19 12:00:01] [INFO] 共找到 1 个 device_model_annotation.yaml 文件

[2025-10-19 12:00:01] [INFO] ================================================================================
[2025-10-19 12:00:01] [INFO] 步骤 2: 索引 H5 文件（同级及下一级目录）
[2025-10-19 12:00:01] [INFO] ================================================================================
[2025-10-19 12:00:02] [INFO] 共找到 12345 个 H5 文件

[2025-10-19 12:00:02] [INFO] ================================================================================
[2025-10-19 12:00:02] [INFO] 步骤 3: 分析 H5 文件内部结构
[2025-10-19 12:00:02] [INFO] ================================================================================
[2025-10-19 12:00:03] [INFO] [1/12345] 分析: converted_dataset_wx/episode_0001.h5
[2025-10-19 12:00:03] [INFO]   ✓ 找到 45 个非空数据集
[2025-10-19 12:00:03] [INFO]   ✓ 内部 shape 一致
...
```

### 报告文件

生成 `validation_report_YYYYMMDD_HHMMSS.txt`，包含：

```
================================================================================
智平方数据集验证报告
================================================================================
生成时间: 2025-10-19 12:30:45
数据根目录: /mnt/nas/synnas/docker2/外部数据/智平方
Error目录: /mnt/nas/synnas/docker2/外部数据/智平方/error

================================================================================
统计摘要
================================================================================
总 H5 文件数: 12345
有效文件数: 12300
异常文件数: 45
已移动文件数: 45

================================================================================
异常文件详细列表
================================================================================

文件: converted_dataset_wx/episode_0042.h5
  错误原因:
    - 路径与多数派不一致: 缺少 3 个路径, 多出 1 个路径
  数据集路径数量: 43
  数据集路径列表:
    - action: shape=(150, 14)
    - observations/camera/rgb/chest/video: shape=()
    ...

文件: task2/episode_0123.h5
  错误原因:
    - 内部 shape 不一致
  数据集路径数量: 45
  ...

================================================================================
已移动文件记录
================================================================================
  converted_dataset_wx/episode_0042.h5 -> converted_dataset_wx/episode_0042.h5
  task2/episode_0123.h5 -> task2/episode_0123.h5
  ...
```

## 检测逻辑详解

### 1. "非空数据"定义

数据集被认为是"非空"需要满足：
1. 数据集存在且可访问
2. Shape 所有维度都 > 0
3. 数据内容有实际数值（不全为零）

为提高性能，使用采样策略：
- **小数据集** (< 1MB): 检查全部数据
- **大数据集**: 采样前 1000 个元素

### 2. 路径一致性检查

统计所有 H5 文件的数据集路径组合，采用"少数服从多数"原则：
- 找到出现次数最多的路径组合（多数派）
- 标记路径组合不同的文件为异常
- 记录具体的差异（缺少/多出的路径）

示例：
```
多数派 (12000 个文件):
  - action
  - observations/camera/rgb/chest/video
  - observations/camera/rgb/head/video
  - observations/qpos
  
异常文件 (300 个文件):
  - 缺少: observations/camera/rgb/head/video
  - 多出: observations/camera/depth/extra/video
```

### 3. Shape 自检

每个 H5 文件内部，检查相同根路径下的数据集形状一致性：
- 忽略时间维度（通常是第一维）
- 其他维度必须一致

示例：
```
✓ 一致的情况:
  /observations/qpos_left: (150, 7)
  /observations/qpos_right: (150, 7)
  /observations/qvel_left: (200, 7)   # 时间维度不同 OK
  /observations/qvel_right: (180, 7)

✗ 不一致的情况:
  /observations/qpos_left: (150, 7)
  /observations/qpos_right: (150, 8)   # 第二维不同，错误！
```

### 4. 版本匹配警告

当检测到多种数据结构版本时：
- 如果多数派占比 < 90%，发出警告
- 提示检查 `device_model_annotation.yaml` 中的 version 字段
- 建议用户手动确认版本配置

## 错误文件命名规则

异常文件移动到 error 文件夹时，保留完整的相对路径结构：

```
原始文件:
  /mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批/task1/episode_0001.h5

移动后:
  /mnt/nas/synnas/docker2/外部数据/智平方/error/30k数采-第一批/task1/episode_0001.h5
```

这样可以：
- 保持目录结构清晰
- 方便追溯原始位置
- 便于后续手动检查

## 工作流程建议

### 推荐流程

```bash
# 1. 先运行 dry-run 模式，检查结果
python scripts/dataset_statistics/zhipingfang_dataset_validator.py --dry-run

# 2. 查看报告，确认检测结果合理
cat /mnt/nas/synnas/docker2/外部数据/智平方/validation_report_*.txt

# 3. 如果有版本警告，检查并更新 device_model_annotation.yaml

# 4. 正式运行，移动异常文件
python scripts/dataset_statistics/zhipingfang_dataset_validator.py

# 5. 检查 error 目录，确认被移动的文件
ls -la /mnt/nas/synnas/docker2/外部数据/智平方/error/

# 6. 执行正常的数据转换流程
python scripts/format_converters/tolerobot/convert2lerobot.py ...
```

### 异常处理

如果发现大量异常文件：
1. **检查版本配置**: 确认 `device_model_annotation.yaml` 中的 version 正确
2. **人工抽查**: 随机检查几个被标记的文件
3. **重新采集**: 如果是数据采集问题，联系采集团队
4. **修复转换**: 如果是转换配置问题，调整配置后重新转换

## 性能说明

- **处理速度**: 约 50-100 个 H5 文件/秒（取决于文件大小和数据集数量）
- **内存占用**: 主要是文件路径和 shape 信息，通常 < 1GB
- **磁盘 I/O**: 读操作为主，采样检查避免全量读取

对于大规模数据集（>10000 个文件），预计运行时间：
- 10,000 文件: 约 3-5 分钟
- 30,000 文件: 约 8-12 分钟
- 50,000 文件: 约 15-20 分钟

## 故障排查

### 问题：找不到 device_model_annotation.yaml

**原因**: 目录结构不符合预期

**解决**:
```bash
# 手动查找
find /mnt/nas/synnas/docker2/外部数据/智平方 -name "device_model_annotation.yaml"

# 如果确实不存在，创建一个
cat > /path/to/device_model_annotation.yaml << EOF
device_model: zhipingfang
device_model_version: default_version
EOF
```

### 问题：打开 H5 文件失败

**原因**: 文件损坏或格式错误

**解决**:
```bash
# 使用 h5dump 检查文件
h5dump -H /path/to/episode.h5

# 或使用 Python
python -c "import h5py; f = h5py.File('/path/to/episode.h5', 'r'); print(list(f.keys()))"
```

### 问题：内存不足

**原因**: 文件数量太多

**解决**:
- 分批处理：将数据集分成多个子目录，分别运行验证
- 增加系统内存
- 优化代码（减少缓存的信息）

## 相关文档

- [智平方数据集转换指南](./ZHIPINGFANG_DUAL_ARM_NO_POSE_COMPRESSED_VIDEO.md)
- [压缩视频格式说明](./COMPRESSED_VIDEO_FORMAT_SUPPORT.md)
- [数据集修复记录](./dataset_converter_fixes_20251014.md)

## 更新日志

### 2025-10-19
- 初始版本
- 实现完整的检测和移动功能
- 支持 dry-run 模式
- 生成详细报告
