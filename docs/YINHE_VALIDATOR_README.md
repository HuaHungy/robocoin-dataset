# 银河通用(Yinhe/Galaxea)数据集预转换验证

## 概述

银河通用数据集验证工具用于检测数据集中可能导致转换失败的问题，支持大规模数据集（已测试 23000+ episodes）。

## 数据集结构

```
银河通用/
├── fold_clothe/                # 任务1: 叠衣服
│   ├── robot_id_1/
│   │   ├── YYYYMMDD_record0/
│   │   │   ├── camera_front_head_rgb.mp4
│   │   │   ├── camera_left_wrist.mp4
│   │   │   ├── camera_right_wrist.mp4
│   │   │   ├── data.json
│   │   │   └── report.txt
│   │   └── ...
│   └── ...
├── steamer_storage_baozi/      # 任务2: 蒸笼存储包子
├── take_snack/                 # 任务3: 拿零食
├── use_dryer/                  # 任务4: 使用烘干机
└── use_washing_machine/        # 任务5: 使用洗衣机
```

## 快速开始

### 1. 快速测试（推荐先运行）

```bash
cd /home/diy01/dev/robocoin-dataset
python3 scripts/dataset_statistics/yinhe_quick_test.py
```

这会:
- 验证前 10 个 episodes
- 统计所有任务的 episode 数量
- 检测前 20 个 episodes 的常见问题
- 给出数据集质量评估

### 2. 部分验证

```bash
# 验证前 50 个 episodes
python3 scripts/dataset_statistics/yinhe_preconversion_validator.py --max-episodes 50

# 详细模式（显示每个 episode 的问题）
python3 scripts/dataset_statistics/yinhe_preconversion_validator.py --max-episodes 50 --verbose
```

### 3. 完整验证

```bash
# 验证所有 episodes
python3 scripts/dataset_statistics/yinhe_preconversion_validator.py

# 自定义数据集路径
python3 scripts/dataset_statistics/yinhe_preconversion_validator.py \
    --dataset-path /path/to/银河通用
```

## 检测的问题类型

### 错误（会导致转换失败）

1. **视频文件缺失**
   - `camera_front_head_rgb.mp4` 缺失
   - `camera_left_wrist.mp4` 缺失
   - `camera_right_wrist.mp4` 缺失

2. **视频文件损坏**
   - 文件大小为 0

3. **data.json 问题**
   - 文件缺失
   - JSON 解析失败
   - 缺少必需字段:
     - `data` (顶层)
     - `header` (顶层，可选但推荐)
   - 缺少必需数据字段:
     - `state_left_arm_joint_position`
     - `state_right_arm_joint_position`
     - `state_left_arm_gripper_width`
     - `state_right_arm_gripper_width`
     - `cmd_left_joint_state`
     - `cmd_right_joint_state`
   - 数据字段为空列表
   - 数据项结构错误（缺少 `timestamp`, `position` 等）

### 警告（可能影响数据质量）

1. **时间戳不一致**
   - 不同数据流时间戳范围差异过大（>1秒）

2. **可选字段缺失**
   - `report.txt` 缺失
   - `state_body_joint_position` 缺失
   - `state_front_head_joint` 缺失

## 输出示例

### 快速测试输出

```
🚀 银河数据集快速验证测试
======================================================================

📊 阶段1: 快速测试前10个episodes
----------------------------------------------------------------------
快速测试结果: 10/10 episodes有效 (100.0%)

📊 阶段2: 统计任务和episode数量
----------------------------------------------------------------------
总共找到 23143 个episodes

按任务分布:
  fold_clothe: 6640 episodes
  steamer_storage_baozi: 10327 episodes
  take_snack: 6176 episodes

📊 阶段3: 检查前20个episodes的常见问题
----------------------------------------------------------------------
发现的错误类型 (共12个错误):
  [6] 缺失视频文件: camera_front_head_rgb.mp4
  [6] 缺失data.json文件

✅ 数据集质量良好: 70.0% episodes有效
```

### 完整验证输出

```
🚀 银河数据集预转换验证器
📁 数据集路径: /mnt/nas/synnas/docker/外部数据/银河通用

🔍 查找银河数据集中的episode...
📊 找到 23143 个episodes

🧪 开始验证...
  进度: 1000/23143 episodes
  进度: 2000/23143 episodes
  ...

======================================================================
📊 验证总结
======================================================================
总Episode数: 23143
✅ 有效: 22800 (98.5%)
❌ 无效: 343 (1.5%)

📋 按任务统计:
  fold_clothe: 6580/6640 有效 (99.1%)
  steamer_storage_baozi: 10200/10327 有效 (98.8%)
  take_snack: 6020/6176 有效 (97.5%)

❌ 常见错误类型:
  [200] 缺失视频文件: camera_front_head_rgb.mp4
  [143] 缺失data.json文件
  [50] JSON字段为空: data.cmd_left_joint_state

❌ 失败的Episodes:
  fold_clothe/robot_1/20250330_record5
    - 缺失视频文件: camera_front_head_rgb.mp4
    - 缺失data.json文件
  ...
======================================================================
```

## data.json 数据结构

### 文件结构

```json
{
  "header": {
    "state_left_arm_joint_position": {
      "num_data": 5093,
      "frequency": 304.34
    },
    "camera_front_head_rgb": {
      "num_data": 612,
      "frequency": 30.0,
      "video_path": "camera_front_head_rgb.mp4"
    },
    ...
  },
  "data": {
    "state_left_arm_joint_position": [
      {
        "names": ["left_arm_joint1", "left_arm_joint2", ..., "left_arm_joint7"],
        "position": [2.23, -1.20, 0.01, 1.99, -1.80, -0.00, -0.54],
        "velocity": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "effort": [0.20, 1.10, -1.12, 3.99, 0.01, -0.11, 0.28],
        "timestamp": 1743302887.286
      },
      ...
    ],
    "cmd_left_joint_state": [
      {
        "positions": [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        "timestamp": 1743302887.298
      },
      ...
    ],
    ...
  }
}
```

### 必需字段说明

| 字段名 | 类型 | 说明 |
|-------|------|------|
| `state_left_arm_joint_position` | list | 左臂关节位置（7个关节） |
| `state_right_arm_joint_position` | list | 右臂关节位置（7个关节） |
| `state_left_arm_gripper_width` | list | 左夹爪宽度 |
| `state_right_arm_gripper_width` | list | 右夹爪宽度 |
| `cmd_left_joint_state` | list | 左臂控制指令 |
| `cmd_right_joint_state` | list | 右臂控制指令 |

### 可选字段

| 字段名 | 类型 | 说明 |
|-------|------|------|
| `state_body_joint_position` | list | 身体关节位置（3个关节） |
| `state_front_head_joint` | list | 头部关节位置（2个关节） |
| `cmd_body_joint` | list | 身体控制指令 |
| `cmd_head_joint_state` | list | 头部控制指令 |
| `odom` | list | 里程计数据 |

## 性能说明

- **Episode 发现速度**: 非常快（浅层目录结构）
- **验证速度**: 约 100-200 episodes/秒
- **适用规模**: 数千到数万个 episodes
- **内存占用**: 低（逐 episode 验证）

### 大规模数据集优化建议

1. **先运行快速测试**: 了解数据集整体质量
   ```bash
   python3 scripts/dataset_statistics/yinhe_quick_test.py
   ```

2. **分批验证**: 使用 `--max-episodes` 参数
   ```bash
   python3 scripts/dataset_statistics/yinhe_preconversion_validator.py --max-episodes 1000
   ```

3. **按任务验证**: 手动验证单个任务目录
   ```bash
   # 临时修改代码中的 dataset_path 到具体任务
   python3 scripts/dataset_statistics/yinhe_preconversion_validator.py \
       --dataset-path /path/to/银河通用/fold_clothe
   ```

## 转换配置参考

验证器基于以下转换配置文件:
- `scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml`
- `scripts/format_converters/tolerobot/configs/converter_config_galaxea_r1_lite.yaml`
- `scripts/format_converters/tolerobot/configs/converter_config_galaxea_r1_lite_h5_mp4.yaml`

## 故障排除

### 问题: 找不到 episodes

**可能原因**:
- 目录结构不符合 `task/robot_id/YYYYMMDD_recordN` 格式
- Episode 名称不包含 `_record`

**解决方案**:
检查目录结构是否正确

### 问题: JSON 解析失败

**可能原因**:
- data.json 文件损坏
- JSON 格式错误

**解决方案**:
手动检查 JSON 文件:
```bash
python3 -c "import json; json.load(open('data.json'))"
```

### 问题: 大量时间戳警告

**说明**: 这通常不是问题，只是不同数据流的时间范围略有差异

**如果需要消除警告**: 使用非详细模式（不加 `--verbose`）

## 相关文档

- [预转换验证工具使用指南](PRECONVERSION_VALIDATOR_GUIDE.md) - 完整文档
- 转换器配置: `scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml`
- 转换器代码: `src/robocoin_dataset/format_converter/tolerobot/`
