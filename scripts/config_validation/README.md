# 配置验证工具

轻量级配置验证工具，用于快速验证转换器配置的正确性。

## 功能

✅ **快速采样验证** - 每个数据集只分析2个随机episodes，30分钟内完成所有验证  
✅ **Episode智能定位** - 自动识别H5、MP4+JSON、MCAP、BSON等格式  
✅ **深度Schema分析** - 提取字段名、shape、dtype、range等信息  
✅ **配置对比** - 检查h5_path是否存在、维度是否匹配  
✅ **字段命名检查** - 基于realman_rmc_aidal的命名标准

## 工具组件

```
scripts/config_validation/
├── episode_locator.py      # Episode定位器（支持多种格式）
├── schema_analyzer.py       # Schema深度分析器
├── config_comparator.py     # 配置对比器
├── field_name_checker.py    # 字段命名检查器
├── batch_validation.py      # 批量验证脚本（主入口）
├── run_validation.sh        # 快速运行脚本
└── README.md
```

## 快速开始

### 方式1: 使用快速脚本

```bash
cd /home/liu/program/robocoin-dataset
bash scripts/config_validation/run_validation.sh
```

### 方式2: 手动运行

```bash
cd /home/liu/program/robocoin-dataset

python scripts/config_validation/batch_validation.py \
    --database /mnt/db/datasets.db \
    --config-dir ./scripts/format_converters/tolerobot/configs/ \
    --output-dir ./outputs/config_validation \
    --num-datasets 2 \
    --num-episodes 2
```

## 参数说明

- `--database`: 数据库路径
- `--config-dir`: 配置文件目录
- `--output-dir`: 输出目录
- `--device-models`: 要验证的device models（可选，默认验证优先级列表）
- `--num-datasets`: 每个model采样的数据集数量（默认2）
- `--num-episodes`: 每个数据集采样的episodes数量（默认2）

## 输出

### 1. 总体报告
`outputs/config_validation/validation_report.json`

### 2. 各数据集的详细报告
- `{dataset_name}_comparison.txt` - 配置对比报告
- `{dataset_name}_field_names.txt` - 字段命名检查报告

## 报告示例

### 配置对比报告

```
======================================================================
配置对比报告
======================================================================

总错误数: 2
总警告数: 1

======================================================================
Observations
======================================================================

[Images]
  ✓ cam_high_rgb
      Shape: (480, 640, 3)
  ✗ cam_left_wrist
      - 配置的摄像头 'cam_left_wrist' 未在数据中找到
  
[State]
  ✓ observations/qpos [0:7]
      Names: right_arm_joint_1_rad, right_arm_joint_2_rad, ...
  ✗ observations/qpos [30:33]
      - 维度越界: 配置要求到索引33, 但实际数据只有30个元素
```

### 字段命名检查报告

```
======================================================================
字段命名检查报告
======================================================================

总字段数: 16
符合规范: 12 (75.0%)
不符合规范: 3
警告: 1

======================================================================
不符合规范的字段
======================================================================

✗ joint_1
    - 缺少角度单位后缀（应为_rad）
    💡 建议: joint_1_rad

✗ eef_pos_x
    - 缺少长度单位后缀（应为_m）
    💡 建议: eef_pos_x_m
```

## 优先级Device Models

1. discover_robotics_aitbot_mmk2
2. yinhe
3. realman_rmc_aidal
4. agilex
5. leju
6. ruantong
7. zhipingfang
8. galaxea

## 命名规范

基于`converter_config_realman_rmc_aidal.yaml`的标准：

- **关节**: `{left/right}_arm_joint_N_rad` (N=1-7)
- **夹爪**: `{left/right}_gripper_open_rad` 或 `{left/right}_gripper_open`
- **末端位置**: `{left/right}_eef_pos_{x/y/z}_m`
- **末端姿态**: `{left/right}_eef_rot_euler_{x/y/z}_rad`
- **摄像头**: `cam_{high/left/right/wrist}_rgb`

### 单位要求

- ✅ 角度: `_rad` (弧度)
- ✅ 长度: `_m` (米)
- ❌ 不推荐: `_deg`, `_mm`, `_cm`

## 性能

- **全量扫描Schema Discovery**: ~4小时（扫描所有文件）
- **轻量级配置验证**: ~30分钟（只采样2个episodes）

快10倍！ 🚀

## 故障排查

### ImportError: No module named 'mcap'

```bash
pip install mcap
```

### ImportError: No module named 'bson'

```bash
pip install pymongo
```

### 数据集路径不存在

检查数据库中的`yaml_file_path`字段是否正确。

## 下一步

验证通过后，可以进行：
1. 修复发现的配置错误
2. 统一字段命名
3. 运行Test模式转换
4. 正式批量转换

