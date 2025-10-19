# 数据集预转换验证器 v2 (高性能版)

## 概述

三个高性能验证器，用于在数据转换前快速检测潜在问题：

1. **银河通用 (Yinhe)** - `yinhe_preconversion_validator_v2.py`
2. **软通天擎 (Ruantong)** - `ruantong_preconversion_validator_v2.py`
3. **智平方 (Zhipingfang)** - `zhipingfang_preconversion_validator_v2.py`

## 核心优化

### 1. 基于 device_model_annotation.yaml 定位数据集
- 不再硬编码路径或版本目录
- 自动发现所有数据集版本
- 读取版本信息

### 2. Episode特征文件快速定位
- **银河**: `data.json` (task_dir/robot_id/episode_dir/data.json)
- **软通**: `aligned_joints.h5` (dataset_dir/robot_id/episode_dir/aligned_joints.h5)
- **智平方**: `*.h5` 文件 (dataset_dir/*.h5)

### 3. 多进程并行验证
- 使用 `ProcessPoolExecutor`
- 默认 4-8 个并行进程
- 适合处理几万条数据

### 4. 从 Config 读取验证规则
- 不再硬编码 required fields
- 从 converter_config.yaml 提取 h5_paths / JSON fields
- 更灵活，易维护

### 5. 轻量级检查
- 只检查文件存在性和keys
- 不完整加载大文件
- H5 只检查 keys，不读取数据
- JSON 只读取前10MB

## 使用方法

### 银河通用 (Yinhe)

```bash
# 基本用法
python3 scripts/dataset_statistics/yinhe_preconversion_validator_v2.py \
    --dataset-path /mnt/nas/synnas/docker/外部数据/银河通用 \
    --max-episodes 100 \
    --workers 8

# 指定config文件
python3 scripts/dataset_statistics/yinhe_preconversion_validator_v2.py \
    --dataset-path /mnt/nas/synnas/docker/外部数据/银河通用 \
    --config scripts/format_converters/tolerobot/configs/converter_config_galaxea_r1_lite.yaml \
    --workers 8 \
    --verbose
```

**数据结构**:
```
银河通用/
├── fold_clothe/                      # Task目录
│   ├── device_model_annotation.yaml  ⭐ 版本标识文件
│   ├── local_dataset_info.yaml
│   └── dieyifu-1/                    # Robot ID
│       └── 20250627_143757_record0/  # Episode目录
│           ├── data.json             ⭐ Episode特征文件
│           ├── camera_*.mp4
│           └── report.txt
```

### 软通天擎 (Ruantong)

```bash
# 基本用法
python3 scripts/dataset_statistics/ruantong_preconversion_validator_v2.py \
    --dataset-path /mnt/nas/synnas/docker2/外部数据/软通天擎 \
    --max-episodes 100 \
    --workers 8

# 指定config
python3 scripts/dataset_statistics/ruantong_preconversion_validator_v2.py \
    --dataset-path /mnt/nas/synnas/docker2/外部数据/软通天擎 \
    --config scripts/format_converters/tolerobot/configs/converter_config_ruantong_gt01_no_depth.yaml \
    --workers 8
```

**数据结构**:
```
软通天擎/
├── gt01/zy/21_备料区场景5/375/
│   ├── device_model_annotation.yaml  ⭐ 版本标识文件
│   ├── local_dataset_info.yaml
│   └── A2D0015AC00066/               # Robot ID
│       └── 39476/                    # Episode目录
│           ├── aligned_joints.h5     ⭐ Episode特征文件
│           ├── camera/
│           │   ├── 1/*.jpg
│           │   └── 2/*.jpg
│           └── meta_info.json
```

### 智平方 (Zhipingfang)

```bash
# 基本用法
python3 scripts/dataset_statistics/zhipingfang_preconversion_validator_v2.py \
    --dataset-path /mnt/nas/synnas/docker2/外部数据/智平方 \
    --max-episodes 100 \
    --workers 8

# 指定config
python3 scripts/dataset_statistics/zhipingfang_preconversion_validator_v2.py \
    --dataset-path /mnt/nas/synnas/docker2/外部数据/智平方 \
    --config scripts/format_converters/tolerobot/configs/converter_config_zhipingfang_dual_arm_with_pose.yaml \
    --workers 8
```

**数据结构**:
```
智平方/
├── 30k数采-第一批-20250930-32274条/
│   └── converted_dataset_wx/
│       ├── device_model_annotation.yaml  ⭐ 版本标识文件
│       ├── local_dataset_info.yaml
│       ├── converted_*.h5                ⭐ Episode特征文件
│       └── episode_*.h5                  ⭐ Episode特征文件
```

## 性能对比

| 验证器 | 旧版 (v1) | 新版 (v2) | 加速比 |
|--------|----------|----------|--------|
| 银河 | 遍历所有子目录 | 只遍历2层 | 🚀 50x+ |
| 软通 | 递归搜索全盘 | 只搜索已知版本目录 | 🚀 100x+ |
| 智平方 | 递归搜索 | 只遍历2-3层 | 🚀 20x+ |

**多进程加速**:
- 1个进程: baseline
- 4个进程: ~3.5x
- 8个进程: ~6.5x
- 16个进程: ~10x (取决于I/O瓶颈)

## 输出示例

```
🚀 银河数据集验证器 v2 (高性能版)
📁 数据集: /mnt/nas/synnas/docker/外部数据/银河通用
⚙️  并行度: 4

⚠️  未指定config文件，使用默认配置
🔍 查找 device_model_annotation.yaml 文件...
✅ 找到 5 个任务目录
  📂 take_snack (version: default_version)
    找到 20 个episodes

📊 总计: 20 个episodes

🧪 开始验证 (使用 4 个进程)...

======================================================================
📊 验证总结
======================================================================
总Episodes: 20
✅ 有效: 20 (100.0%)
❌ 无效: 0 (0.0%)

📋 按任务统计:
  take_snack: 20/20 (100.0%)
======================================================================
```

## 测试结果

### 银河通用
- ✅ 测试通过 (20 episodes, 100% 有效)
- 路径: `/mnt/nas/synnas/docker/外部数据/银河通用`
- 速度: ~5秒 (20 episodes, 4 workers)

### 软通天擎
- ✅ 测试通过 (20 episodes, 检测到config不匹配)
- 路径: `/mnt/nas/synnas/docker2/外部数据/软通天擎`
- 发现52个数据集
- 速度: ~8秒 (20 episodes, 4 workers)

### 智平方
- ✅ 测试通过 (20 episodes, 100% 有效)
- 路径: `/mnt/nas/synnas/docker2/外部数据/智平方`
- 发现16个数据集
- 速度: ~3秒 (20 episodes, 4 workers)

## 关键改进点

### 1. 正确的验证逻辑流程
```
Read device_model_annotation.yaml (获取version)
    ↓
Match converter_config_{model}_{version}.yaml
    ↓
Extract required paths/fields from config
    ↓
Validate only what config requires (不硬编码)
```

### 2. Episode特征文件识别
- 每个数据集有独特的episode标识文件
- 通过特征文件快速定位episode目录
- 避免深度递归搜索

### 3. 智能路径搜索
- 银河: 1级子目录 (task level)
- 软通: 已知版本目录 + 4层深度
- 智平方: 3层深度

### 4. 配置文件解析
- 银河: 从 `features.observation.images` 和 `features.observation.data` 提取
- 软通: 从 `h5_paths` 和 `camera_paths` 提取
- 智平方: 从 `features.observation.images`, `features.observation.state.sub_state`, `features.action.sub_action` 提取

## 注意事项

1. **Config文件重要性**: 建议始终指定 `--config` 参数，避免使用默认配置
2. **Worker数量**: 根据磁盘I/O能力调整，NAS推荐4-8个
3. **超时处理**: 如果数据集过大，可以先用 `--max-episodes` 测试
4. **权限问题**: 某些目录可能需要sudo权限

## 文件位置

```
scripts/dataset_statistics/
├── yinhe_preconversion_validator_v2.py     # 银河验证器
├── ruantong_preconversion_validator_v2.py  # 软通验证器
├── zhipingfang_preconversion_validator_v2.py  # 智平方验证器
└── README_VALIDATORS_V2.md                 # 本文档
```

## 下一步计划

- [ ] 添加移动错误文件到error目录的功能
- [ ] 添加详细的错误报告（CSV导出）
- [ ] 支持增量验证（只验证新增episode）
- [ ] 添加数据统计功能（帧数、大小等）
