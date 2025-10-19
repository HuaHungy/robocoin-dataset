# 预转换验证工具使用指南

## 概述

为不同数据集格式提供预转换验证工具，提前检测会导致转换失败的数据问题。

## 工具列表

### 1. 智平方验证器 (zhipingfang_preconversion_validator.py)

**数据格式**: H5 文件格式（`episode_*.h5`, `episode_*.hdf5`）

**使用场景**:
- 智平方数据集（多版本自动发现）
- 其他使用 H5 文件格式的数据集

**基本用法**:
```bash
# 自动发现所有版本
python scripts/dataset_statistics/zhipingfang_preconversion_validator.py \\
    --data-root /mnt/nas/synnas/docker2/外部数据/智平方 \\
    --config-base examples/configs

# 所有版本使用同一配置
python scripts/dataset_statistics/zhipingfang_preconversion_validator.py \\
    --data-root /path/to/data \\
    --config examples/configs/converter_config_xxx.yaml

# Dry-run（不移动文件）
python scripts/dataset_statistics/zhipingfang_preconversion_validator.py \\
    --data-root /path/to/data \\
    --config-base examples/configs \\
    --dry-run
```

**检测的错误类型**:
- **KeyError**: 配置中的 `h5_path` 在 H5 文件中不存在
- **IndexError**: 无法访问第一帧数据
- **ValueError**: 
  - 标量数据尝试切片
  - 切片范围超出边界 (`range_from`/`range_to`)
- **视频格式错误**: 压缩视频相关路径/索引缺失

**输出**:
- 实时控制台输出（带进度）
- 详细报告: `validation_report_YYYYMMDD_HHMMSS.txt`
- 失败文件自动隔离到 `error/` 目录

---

### 2. 软通天擎验证器 (ruantong_preconversion_validator.py)

**数据格式**: Episode 目录 + H5 + 图像文件
```
episode_dir/
├── aligned_joints.h5      # State/Action 数据
├── camera/                # 相机数据
│   ├── 0/                 # 帧0
│   │   ├── head_color.jpg
│   │   ├── hand_left_color.jpg
│   │   └── ...
│   └── 1/                 # 帧1
│       └── ...
└── meta_info.json         # 元数据
```

**使用场景**:
- 软通天擎数据集（gt01, gt02, jx01, jx02 等版本）
- 其他使用 Episode目录 + 图像 格式的数据集

**基本用法**:
```bash
# 验证所有版本
python scripts/dataset_statistics/ruantong_preconversion_validator.py \\
    --data-root /mnt/nas/synnas/docker2/外部数据/软通天擎 \\
    --config-dir scripts/format_converters/tolerobot/configs

# Dry-run（不移动文件）
python scripts/dataset_statistics/ruantong_preconversion_validator.py \\
    --data-root /path/to/data \\
    --config-dir /path/to/configs \\
    --dry-run

# 快速测试（仅验证少量样本）
python scripts/dataset_statistics/ruantong_quick_test.py
```

**检测的错误类型**:
- **结构缺失**: 缺少 `aligned_joints.h5`, `camera/` 目录
- **KeyError**: 
  - H5 文件缺少 `state` 或 `action` group
  - 配置中的路径在 H5 中不存在
  - 图像文件路径不存在
- **IndexError**: 无法读取第一帧数据
- **ValueError**: 数据切片范围无效

**输出**:
- 实时控制台输出（带进度）
- 详细报告: `validation_report_YYYYMMDD_HHMMSS.txt`
- 失败 episode 自动隔离到 `error/` 目录

---

### 3. 银河通用验证器 (yinhe_preconversion_validator.py)

**数据格式**: Episode 目录 + MP4 视频 + JSON 数据
```
task_name/robot_id/YYYYMMDD_recordN/
├── camera_front_head_rgb.mp4   # 头部前视相机
├── camera_left_wrist.mp4       # 左腕相机
├── camera_right_wrist.mp4      # 右腕相机
├── data.json                   # State/Action 数据
└── report.txt                  # 元数据（可选）
```

**data.json 结构**:
```json
{
  "header": {
    "state_left_arm_joint_position": {"num_data": ..., "frequency": ...},
    "camera_front_head_rgb": {"num_data": ..., "video_path": "..."},
    ...
  },
  "data": {
    "state_left_arm_joint_position": [
      {
        "names": ["left_arm_joint1", ...],
        "position": [...],
        "velocity": [...],
        "timestamp": ...
      },
      ...
    ],
    ...
  }
}
```

**使用场景**:
- 银河通用/Galaxea R1 数据集
- 其他使用 MP4视频 + JSON 格式的数据集

**基本用法**:
```bash
# 验证所有episodes
python scripts/dataset_statistics/yinhe_preconversion_validator.py \\
    --dataset-path /mnt/nas/synnas/docker/外部数据/银河通用

# 验证前N个episodes（快速测试）
python scripts/dataset_statistics/yinhe_preconversion_validator.py \\
    --max-episodes 50 --verbose

# 快速测试工具
python scripts/dataset_statistics/yinhe_quick_test.py
```

**检测的错误类型**:
- **视频文件缺失**: 缺少必需的 MP4 视频文件
  - `camera_front_head_rgb.mp4`
  - `camera_left_wrist.mp4`
  - `camera_right_wrist.mp4`
- **视频文件损坏**: 文件大小为 0
- **data.json 问题**:
  - 文件缺失或 JSON 解析失败
  - 缺少必需的顶层字段 (`data`, `header`)
  - 缺少必需的数据字段:
    - `state_left_arm_joint_position`
    - `state_right_arm_joint_position`
    - `state_left_arm_gripper_width`
    - `state_right_arm_gripper_width`
    - `cmd_left_joint_state`
    - `cmd_right_joint_state`
  - 数据字段为空列表
  - 数据项结构错误（缺少 `timestamp`, `position` 等）
- **时间戳不一致**: 不同数据流时间戳范围差异过大（警告）

**输出**:
- 实时控制台输出（带进度）
- 按任务统计验证结果
- 错误类型汇总
- 失败 episode 列表

**特点**:
- 不移动失败文件（只做验证和报告）
- 按任务（task）统计结果
- 支持大规模数据集（23000+ episodes）
- 提供快速测试工具

---

## 工作流程

### 典型工作流

1. **执行验证**（dry-run模式，先不移动文件）
```bash
python scripts/dataset_statistics/xxx_validator.py \\
    --data-root /path/to/data \\
    --config-dir /path/to/configs \\
    --dry-run
```

2. **查看报告**
```bash
cat /path/to/data/validation_report_*.txt
```

3. **确认无误后正式运行**（移动失败文件）
```bash
python scripts/dataset_statistics/xxx_validator.py \\
    --data-root /path/to/data \\
    --config-dir /path/to/configs
```

4. **处理失败文件**
- 失败文件被移动到 `<data-root>/error/` 目录
- 目录结构保持原有的相对路径
- 可以单独修复后移回

---

## 性能说明

### 智平方验证器
- **速度**: 约 100-200 文件/秒（取决于 H5 文件大小）
- **适用规模**: 数千到数万个文件
- **内存占用**: 低（逐文件验证）

### 软通天擎验证器
- **速度**: Episode 发现较慢（深度递归），验证约 50-100 episode/秒
- **适用规模**: 数百到数千个 episode
- **优化建议**: 
  - 使用 `ruantong_quick_test.py` 先快速检查
  - 对于超大数据集，可以按版本分别验证

### 银河通用验证器
- **速度**: Episode 发现快速（浅层目录结构），验证约 100-200 episode/秒
- **适用规模**: 数千到数万个 episode（已测试 23000+ episodes）
- **优化建议**:
  - 使用 `yinhe_quick_test.py` 先快速检查前 10-20 个 episodes
  - 使用 `--max-episodes N` 参数进行分批验证
  - 对于超大数据集，可以按任务（task）分别验证

---

## 故障排除

### 问题: 扫描太慢
**解决方案**:
1. 检查是否有网络文件系统延迟
2. 使用快速测试工具先验证结构
3. 考虑按子目录分批验证

### 问题: 配置文件未找到
**解决方案**:
1. 确认配置文件命名符合规范:
   - 智平方: `converter_config_zhipingfang_*.yaml`
   - 软通天擎: `converter_config_ruantong_{version}_*.yaml`
   - 银河通用: `converter_config_yinhe.yaml` 或 `converter_config_galaxea_*.yaml`
2. 使用 `--config` 参数指定具体配置文件

### 问题: 大量误报
**解决方案**:
1. 检查配置文件是否匹配数据版本
2. 查看报告中的具体错误信息
3. 与实际转换器代码对比验证逻辑

---

## 扩展到其他数据集

### 创建新的验证器

参考现有验证器的结构:

1. **理解数据格式**
   - 文件组织结构
   - 关键文件/目录
   - 数据访问路径

2. **分析转换配置**
   - 图像路径模式
   - State/Action 路径
   - 特殊配置项

3. **识别错误模式**
   - 查看转换器代码的异常处理
   - 提取关键的 KeyError, IndexError, ValueError 条件

4. **实现验证器**
   - 文件/目录结构检查
   - 路径存在性检查
   - 数据维度/切片检查
   - 多版本支持

5. **测试和优化**
   - 使用少量样本测试
   - 优化扫描性能
   - 完善错误信息

---

## 参考

- 转换器代码: `src/robocoin_dataset/format_converter/tolerobot/`
- 配置示例: `examples/configs/` 或 `scripts/format_converters/tolerobot/configs/`
- 智平方验证器: `scripts/dataset_statistics/zhipingfang_preconversion_validator.py`
- 软通天擎验证器: `scripts/dataset_statistics/ruantong_preconversion_validator.py`
- 银河通用验证器: `scripts/dataset_statistics/yinhe_preconversion_validator.py`
- 快速测试工具:
  - `scripts/dataset_statistics/ruantong_quick_test.py`
  - `scripts/dataset_statistics/yinhe_quick_test.py`
