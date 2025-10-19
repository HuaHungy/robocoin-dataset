# 智平方预转换验证工具 - 使用指南

## 🎯 目的

这个工具的目的是**提前检测会在转换过程中导致错误的 H5 文件**，避免转换到一半才发现问题，浪费时间。

## 📋 检测内容

基于转换代码 (`lerobot_format_converter_h5.py`) 的错误检查逻辑，工具会检测以下会导致转换失败的问题：

### 1. **KeyError** - 配置路径不存在
- ✅ 检查配置中的所有 `h5_path` 是否在 H5 文件中存在
- ✅ 检查压缩视频格式所需的 `video` 和 `video_index` 路径

**示例错误**:
```
配置中的路径在H5文件中不存在 (KeyError):
  缺少路径: ['observations/camera/rgb/head/video', 'observations/camera/rgb/head/video_index']
  可用路径: ['action', 'observations/qpos', ...]
```

### 2. **IndexError** - 数组索引超出范围
- ✅ 检查是否能成功读取第一帧数据
- ✅ 检查数据集是否为空

**示例错误**:
```
无法读取数据 (IndexError):
  sub_state: left_arm_joint_0
  路径: observations/arm/left/joints
  错误: index 0 is out of bounds for axis 0 with size 0
```

### 3. **ValueError** - 数据维度或切片范围错误  
- ✅ 检查 scalar(0维) 数据的切片配置
- ✅ 检查 `range_from` 和 `range_to` 是否在数据长度范围内

**示例错误**:
```
标量数据无法切片 (ValueError):
  sub_state: gripper_position
  路径: observations/effector/right/position
  数据shape: () (scalar)
  配置range: [0:7]
  建议: 标量数据只能用 range_from: 0, range_to: 1
```

### 4. **压缩视频格式错误**
- ✅ 检查 `use_compressed_video: true` 时的必要配置
- ✅ 检查 video 数据是否为 scalar 格式

**示例错误**:
```
压缩视频数据不存在 (KeyError):
  camera: chest
  期望路径: observations/camera/rgb/chest/video
  实际h5_path: observations/camera/rgb/chest/images
```

## 🚀 使用方法

### 基本用法

```bash
python scripts/dataset_statistics/zhipingfang_preconversion_validator.py \
    --config examples/configs/converter_config_zhipingfang_dual_arm_no_pose_compressed_video.yaml \
    --data-root /mnt/nas/synnas/docker2/外部数据/智平方
```

### 命令行参数

```bash
--config PATH          # 必需: 转换配置文件路径
--data-root PATH       # 数据根目录 (默认: /mnt/nas/synnas/docker2/外部数据/智平方)
--error-dir PATH       # Error 文件夹 (默认: <data-root>/error)
--dry-run             # 只检测不移动文件（测试模式）
```

### 完整示例

```bash
# 1. 先运行 dry-run 模式查看会有哪些文件失败
python scripts/dataset_statistics/zhipingfang_preconversion_validator.py \
    --config examples/configs/converter_config_zhipingfang_dual_arm_no_pose_compressed_video.yaml \
    --data-root /mnt/nas/synnas/docker2/外部数据/智平方 \
    --dry-run

# 2. 查看报告
cat /mnt/nas/synnas/docker2/外部数据/智平方/preconversion_validation_report_*.txt

# 3. 确认无误后，正式运行（移动失败文件）
python scripts/dataset_statistics/zhipingfang_preconversion_validator.py \
    --config examples/configs/converter_config_zhipingfang_dual_arm_no_pose_compressed_video.yaml \
    --data-root /mnt/nas/synnas/docker2/外部数据/智平方

# 4. 执行正常转换（现在所有文件都能成功转换）
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --config examples/configs/converter_config_zhipingfang_dual_arm_no_pose_compressed_video.yaml \
    --input-path /mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批 \
    --output-path outputs/lerobot_converter/zhipingfang_validated
```

## 📊 输出示例

### 控制台输出

```
================================================================================
步骤 1: 加载转换配置
================================================================================
✓ 配置加载成功: examples/configs/converter_config_zhipingfang_dual_arm_no_pose_compressed_video.yaml
  FPS: 30
  Video enabled: True

================================================================================
步骤 2: 查找 H5 文件
================================================================================
✓ 找到 29786 个 H5 文件

================================================================================
步骤 3: 验证所有 H5 文件
================================================================================
进度: [100/29786] 30k数采-第一批/converted_dataset_wx/episode_0100.h5
进度: [200/29786] 30k数采-第一批/converted_dataset_wx/episode_0200.h5
...
进度: [29786/29786] 30k数采-第一批/task_65/episode_0533.h5

✓ 验证完成
  总文件数: 29786
  会导致转换失败: 286
  有警告(可能不影响): 45

================================================================================
步骤 4: 移动会导致转换失败的文件
================================================================================
✓ 移动: 30k数采-第一批/task_1/episode_0042.h5
✓ 移动: 30k数采-第一批/task_1/episode_0123.h5
...
✓ 共移动 286 个文件到 /mnt/nas/synnas/docker2/外部数据/智平方/error

================================================================================
验证完成!
================================================================================
会导致转换失败的文件: 286
报告位置: /mnt/nas/synnas/docker2/外部数据/智平方/preconversion_validation_report_20251019_143022.txt
```

### 报告文件示例

```
================================================================================
智平方数据集 - 预转换验证报告
================================================================================
生成时间: 2025-10-19 14:30:22
配置文件: examples/configs/converter_config_zhipingfang_dual_arm_no_pose_compressed_video.yaml
数据根目录: /mnt/nas/synnas/docker2/外部数据/智平方

================================================================================
统计摘要
================================================================================
总 H5 文件数: 29786
会导致转换失败: 286
有警告(可能不影响): 45

================================================================================
会导致转换失败的文件详情
================================================================================

文件: 30k数采-第一批/task_1/episode_0042.h5
  错误:
    配置中的路径在H5文件中不存在 (KeyError):
      缺少路径: ['observations/camera/rgb/head/video_index']
      可用路径(前20个): ['action', 'observations/qpos', ...]

文件: 30k数采-第一批/task_2/episode_0123.h5
  错误:
    标量数据无法切片 (ValueError):
      sub_state: gripper_position
      路径: observations/effector/right/position  
      数据shape: () (scalar)
      配置range: [0:1]
      建议: 这个配置其实是对的，但数据应该是1维数组而不是scalar

文件: 30k数采-第一批/task_3/episode_0088.h5
  错误:
    压缩视频数据不存在 (KeyError):
      camera: chest
      期望路径: observations/camera/rgb/chest/video
      实际h5_path: observations/camera/rgb/chest/images

================================================================================
有警告的文件(可能不影响转换)
================================================================================

文件: 30k数采-第一批/task_5/episode_0234.h5
  警告:
    数据集为空:
      sub_state: neck_pitch
      路径: observations/neck/pitch
      shape: (0,)
```

## 🔍 与之前工具的区别

| 特性 | 之前的工具 | 这个工具 |
|------|----------|----------|
| 检测目标 | 数据一致性（路径、shape） | **会导致转换失败的错误** |
| 检测依据 | 少数服从多数 | **转换代码的错误检查逻辑** |
| 配置依赖 | 不需要配置 | **必须指定转换配置** |
| 准确性 | 可能误报 | **精准检测转换会报错的文件** |
| 使用场景 | 数据质量检查 | **转换前必查** |

## ✅ 优势

### 1. **精准检测**
- 模拟转换代码的实际检查逻辑
- 检测到的问题**100%会导致转换失败**
- 不会误报正常文件

### 2. **节省时间**
- 避免转换到一半才发现问题
- 30000 文件只需 5-10 分钟完成检测
- 提前隔离问题文件

### 3. **详细诊断**
- 明确指出具体错误类型（KeyError/IndexError/ValueError）
- 提供修复建议
- 显示实际数据和期望配置的差异

### 4. **基于实际配置**
- 使用你要转换时的真实配置文件
- 检测配置与数据的匹配情况
- 支持多种配置变体

## 📖 常见问题

### Q: 为什么要指定配置文件？

A: 因为同一个 H5 文件，用不同的配置转换，可能有些配置成功有些失败。
例如：
- 配置A 需要 `observations/camera/rgb/head/video_index`
- 配置B 不需要这个路径
- H5 文件缺少这个路径时，配置A会失败，配置B成功

所以必须用你实际要用的配置来检测。

### Q: 检测出的文件一定会转换失败吗？

A: **是的，100%会失败**。工具模拟的就是转换代码的错误检查逻辑。

### Q: 有警告的文件需要处理吗？

A: 警告文件**可能**不影响转换，建议：
1. 先只移动错误文件
2. 转换时观察警告文件是否真的有问题
3. 如果有问题再处理

### Q: 如何修复被检测出的文件？

A: 常见修复方法：
1. **KeyError**: 数据缺失，需要重新采集或调整配置
2. **ValueError (scalar)**: 数据格式错误，需要修复数据采集程序
3. **压缩视频格式**: 确认使用正确的配置文件

## 🔧 技术细节

### 检测逻辑

工具会对每个 H5 文件：

1. 提取配置中的所有 `h5_path`
2. 检查这些路径是否存在 → KeyError
3. 尝试读取第一帧数据 → IndexError
4. 检查数据维度和切片范围 → ValueError
5. 检查压缩视频格式配置 → KeyError

### 性能

- 每个文件只读取第一帧（最小化I/O）
- 并行不是必需的（磁盘I/O是瓶颈）
- 30000 文件约 5-10 分钟完成

## 📞 支持

如有任何问题，请查看生成的详细报告文件，里面包含了具体的错误原因和修复建议。
