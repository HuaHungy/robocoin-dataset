# 完整重构计划

**日期**: 2025-10-21  
**状态**: 规划阶段

---

## 📋 总览

本文档整合了所有已讨论的问题和解决方案，形成完整的重构路线图。

### 相关文档
- `REFACTORING_ISSUES_SUMMARY.md`: 容错机制和分布式系统问题
- `SYSTEM_ARCHITECTURE_UNDERSTANDING.md`: 系统架构和配置文件问题
- `EPISODE_LEVEL_FAULT_TOLERANCE.md`: Episode级容错实现
- `CONVERTER_REFACTOR_GUIDE.md`: 转换器重构指南

---

## 🎯 核心问题矩阵

| 问题 | 来源 | 优先级 | 状态 | 文档 |
|------|------|--------|------|------|
| **1. Episode级容错机制** | 帧数不一致 | P0 | ✅ 已完成 | EPISODE_LEVEL_FAULT_TOLERANCE.md |
| **2. 严格模式在分布式环境的问题** | 容错+分布式 | 🔴 P0 | ⚠️ 需决策 | REFACTORING_ISSUES_SUMMARY.md |
| **3. PROCESSING状态永久卡住** | 分布式系统 | 🔴 P0 | ❌ 待解决 | REFACTORING_ISSUES_SUMMARY.md |
| **4. 视频加载内存溢出** | MP4读取 | 🔴 P0 | 🚧 部分完成 | CONVERTER_REFACTOR_GUIDE.md |
| **5. 配置文件与数据不匹配** | 配置错误 | 🔴 P0 | ❌ 待解决 | SYSTEM_ARCHITECTURE_UNDERSTANDING.md |
| **6. 字段命名不规范** | 配置错误 | 🟡 P1 | ❌ 待解决 | SYSTEM_ARCHITECTURE_UNDERSTANDING.md |
| **7. Schema自动发现** | 配置错误 | 🟡 P1 | ❌ 待解决 | SYSTEM_ARCHITECTURE_UNDERSTANDING.md |
| **8. device_model_annotation确认** | 配置错误 | 🟡 P1 | ❌ 待解决 | SYSTEM_ARCHITECTURE_UNDERSTANDING.md |
| **9. Episode Source Mapping文件生成** | 可追溯性 | 🔴 P0 | ⚠️ 部分实现 | 本文档 §2.4 |
| **10. 原始数据绝对路径Mapping** | 数据溯源 | 🔴 P0 | ❌ 待实现 | 本文档 §2.5 |

---

## 🔄 工作流程整合

### 全局流程图

```
┌─────────────────────────────────────────────────────────────┐
│                    阶段0: 基础设施（已完成）                    │
├─────────────────────────────────────────────────────────────┤
│ ✅ Episode级容错机制                                          │
│ ✅ 异常类体系 (ConfigError, DataQualityError, etc.)         │
│ ✅ 帧数工具 (ffprobe integration)                            │
│ ✅ 测试脚本 (test_fault_tolerance.py)                        │
│ ⚠️ Episode Source Mapping (部分转换器已实现)                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              阶段1: 配置文件规范化（当前焦点）                 │
├─────────────────────────────────────────────────────────────┤
│ 1.1 Schema Discovery                                        │
│     └─ 自动发现所有数据集的实际格式                          │
│                                                             │
│ 1.2 配置文件对比与修复                                       │
│     ├─ 对比 discovered_schema vs converter_config          │
│     ├─ 标记缺失/冗余/不规范字段                              │
│     └─ 生成修复建议                                          │
│                                                             │
│ 1.3 字段命名标准化                                           │
│     ├─ 定义统一命名规范（基于realman_rmc_aidal）            │
│     ├─ 自动重命名                                            │
│     └─ 量纲统一（rad, m）                                    │
│                                                             │
│ 1.4 device_model_annotation 确认                            │
│     ├─ 读取实际数据                                          │
│     ├─ 匹配最佳converter_config                             │
│     └─ 人工确认或自动更新                                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│           阶段2: 分布式系统问题解决（并行进行）                │
├─────────────────────────────────────────────────────────────┤
│ 2.1 严格模式优化                                             │
│     ├─ 选项A: 保持现状（快速失败）                          │
│     ├─ 选项B: 降级为警告                                     │
│     ├─ 选项C: 分离验证阶段                                   │
│     └─ 🎯 需要决策                                          │
│                                                             │
│ 2.2 PROCESSING卡住问题                                      │
│     ├─ 任务超时机制（24h自动重置）                          │
│     ├─ 心跳/进度上报                                         │
│     ├─ 手动重置工具                                          │
│     └─ 检测和报警                                            │
│                                                             │
│ 2.3 任务失败后的部分进度保存                                 │
│     └─ 避免前面成功的episodes丢失                            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              阶段3: 性能优化（并行进行）                       │
├─────────────────────────────────────────────────────────────┤
│ 3.1 视频延迟加载                                             │
│     ├─ 重构 MP4+JSON converter                              │
│     ├─ 重构 H5+MP4 converter                                │
│     ├─ 重构 Leju Waibu converter                            │
│     └─ 内存: 18GB → <2GB                                     │
│                                                             │
│ 3.2 其他性能优化                                             │
│     └─ (基于profiling结果)                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   阶段4: 批量测试验证                         │
├─────────────────────────────────────────────────────────────┤
│ 4.1 填充测试数据库                                           │
│     └─ python scripts/fill_test_db.py --all                │
│                                                             │
│ 4.2 启动Test Pipeline                                       │
│     ├─ Server (test mode)                                   │
│     └─ Multi-Client (8 workers)                             │
│                                                             │
│ 4.3 监控和分析                                               │
│     ├─ 测试成功率                                            │
│     ├─ 失败原因分类                                          │
│     └─ 生成修复建议                                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    阶段5: 正式转换                            │
├─────────────────────────────────────────────────────────────┤
│ 5.1 启动生产Pipeline                                         │
│ 5.2 持续监控                                                 │
│ 5.3 异常处理和恢复                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔥 当前焦点：阶段1 + 阶段2关键决策

### 阶段1: 配置文件规范化（用户最新需求）

#### 1.1 Schema Discovery工具

**目的**: 自动读取所有数据集，发现实际存在的字段

**需要实现**:
```python
# scripts/dataset_schema_discovery/
├── discover_h5_schema.py       # H5文件结构发现
├── discover_json_schema.py     # JSON结构发现
├── discover_mcap_schema.py     # MCAP/Rosbag topics发现
├── discover_video_schema.py    # 视频文件信息
├── discover_all.py             # 批量发现（按device_model或全部）
└── schema_reporter.py          # 生成人类可读报告
```

**输出示例**:
```yaml
# outputs/discovered_schemas/zhipingfang_dataset_001.yaml
dataset_uuid: "xxx-yyy-zzz"
dataset_name: "算法采集_PCB"
dataset_path: "/mnt/nas/..."
device_model: "zhipingfang"  # 从 device_model_annotation.yaml
device_model_version: "dual_arm_no_pose"

discovered_structure:
  format_type: "h5"  # or "mp4_json", "mcap", etc.
  
  h5_files:
    - path: "task_1/episode_0.h5"
      structure:
        observations:
          images:
            cam_high: 
              shape: [107, 480, 640, 3]
              dtype: uint8
            cam_left_wrist:
              shape: [107, 480, 640, 3]
              dtype: uint8
          qpos:
            shape: [107, 100]
            dtype: float32
            # 注意: 这里只知道总shape，不知道每个维度的含义
        actions:
          qpos:
            shape: [107, 100]
            dtype: float32
  
  videos:
    - path: "task_1/cam_high.mp4"
      frames: 107
      resolution: [480, 640]
      fps: 30
      
config_comparison:
  # 与当前 converter_config_zhipingfang_dual_arm_no_pose.yaml 对比
  status: "mismatch"
  issues:
    - type: "missing_in_config"
      field: "observations/qvel"
      actual_shape: [107, 100]
      suggestion: "添加到config的observation.state.sub_state"
      
    - type: "extra_in_config"
      field: "observations/images/cam_right_wrist"
      reason: "配置文件中有，但数据中不存在"
      
    - type: "shape_mismatch"
      field: "observations/qpos"
      config_expects: "range 0-50"
      actual_shape: 100
      suggestion: "检查range配置"
```

#### 1.2 配置文件诊断工具

**目的**: 对比schema与config，生成修复建议

```python
# scripts/config_tools/diagnose_config.py
def diagnose_converter_config(
    device_model: str,
    device_model_version: str,
    dataset_paths: List[Path]  # 该型号的所有数据集
) -> DiagnosisReport:
    """
    对于某个device_model+version:
    1. 读取所有该类型数据集的schema
    2. 加载对应的converter_config
    3. 找出所有不匹配的地方
    4. 生成修复建议
    """
    pass
```

**输出示例**:
```yaml
# outputs/config_diagnosis/zhipingfang_dual_arm_no_pose_diagnosis.yaml
device_model: "zhipingfang"
device_model_version: "dual_arm_no_pose"
converter_config: "converter_config_zhipingfang_dual_arm_no_pose.yaml"

analyzed_datasets: 50  # 分析了50个该类型数据集

common_issues:  # 在大多数数据集中都出现的问题
  - issue: "missing_field_in_config"
    field: "observations/qvel"
    frequency: 48/50  # 48个数据集都有这个字段，但config没配
    sample_shapes: [[100], [100], [100]]  # 采样的shape都一致
    confidence: "high"
    suggestion: |
      添加到 observation.state.sub_state:
      - names: [velocity_1, velocity_2, ...]
        args:
          h5_path: observations/qvel
          range_from: 0
          range_to: 100

dataset_specific_issues:  # 某些数据集特有的问题
  - dataset_uuid: "xxx-yyy-zzz"
    dataset_name: "特殊数据集"
    issues:
      - field: "observations/images/cam_depth"
        reason: "只有这个数据集有深度相机"
        suggestion: "创建新的version: dual_arm_no_pose_with_depth"

field_naming_issues:  # 命名不规范
  - current_name: "right_joint_1"
    standard_name: "right_arm_joint_1_rad"
    reason: "缺少'arm'和单位后缀"
  
  - current_name: "gripper_position"
    standard_name: "right_gripper_open"
    reason: "不明确是左还是右，且应该用'open'表示开合度"

unit_issues:  # 量纲问题
  - field: "observations/qpos[0:7]"
    current_unit: "unknown"
    target_unit: "rad"
    has_convert_func: false
    suggestion: "需要确认原始单位，可能需要 convert_func: degree2rad"

recommended_actions:
  1. "修复common_issues中的缺失字段（自动化程度：高）"
  2. "重命名不规范字段（需要人工确认）"
  3. "处理dataset_specific_issues（需要创建新version或标记为特殊）"
  4. "验证量纲转换（需要人工确认原始单位）"
```

#### 1.3 交互式配置修复工具

```bash
# 启动交互式修复
python scripts/config_tools/fix_config_interactive.py \
  --device-model zhipingfang \
  --version dual_arm_no_pose

# 工具会:
# 1. 显示诊断报告
# 2. 对每个issue提供修复建议
# 3. 让用户选择: [A]ccept / [M]odify / [S]kip / [Q]uit
# 4. 生成新的converter_config
# 5. 自动运行测试验证
```

#### 1.4 device_model_annotation 确认工具

**问题**: 有些数据集的 device_model_annotation.yaml 可能写错了

**解决方案**:
```python
# scripts/device_model_annotation/verify_annotation.py
def verify_device_model_annotation(dataset_path: Path) -> VerificationResult:
    """
    1. 读取 device_model_annotation.yaml
    2. 读取实际数据的schema
    3. 与所有已知converter_config匹配
    4. 计算匹配度
    5. 如果当前annotation不是最佳匹配，给出建议
    """
    
    current_annotation = load_yaml(dataset_path / "device_model_annotation.yaml")
    current_model = current_annotation['device_model']
    current_version = current_annotation['device_model_version']
    
    schema = discover_schema(dataset_path)
    
    # 与所有已知配置匹配
    match_scores = {}
    for model, versions in all_configs.items():
        for version, config in versions.items():
            score = calculate_match_score(schema, config)
            match_scores[(model, version)] = score
    
    best_match = max(match_scores.items(), key=lambda x: x[1])
    
    if best_match[0] != (current_model, current_version):
        return VerificationResult(
            status="mismatch",
            current=f"{current_model}/{current_version}",
            suggested=f"{best_match[0][0]}/{best_match[0][1]}",
            confidence=best_match[1],
            reason="实际数据更匹配建议的配置"
        )
    else:
        return VerificationResult(status="ok")
```

---

## 📂 Episode Source Mapping 需求（P0）

### 2.4 跳过Episode的映射文件

**背景**: 
- 由于容错机制，某些episodes会被跳过
- LeRobot格式中的episode索引是连续的（0,1,2,3...）
- 但原始数据的episode索引可能不连续（0,2,4,5...，跳过了1和3）
- **需要记录这个映射关系以便追溯**

**文件位置**: `<output_path>/meta/episode_source_mapping.json`

**文件格式**:
```json
{
  "dataset_info": {
    "dataset_uuid": "xxx-yyy-zzz",
    "dataset_name": "算法采集_PCB",
    "device_model": "zhipingfang",
    "device_model_version": "dual_arm_no_pose",
    "conversion_date": "2025-10-21T18:30:00",
    "total_original_episodes": 100,
    "total_converted_episodes": 95,
    "skipped_episodes": 5,
    "skipped_episode_indices": [12, 34, 56, 78, 90]
  },
  
  "episodes": [
    {
      "lerobot_episode_index": 0,
      "original_task": "pick and place",
      "original_task_episode_index": 0,
      "original_source_name": "episode_0.h5",  // 新增：原始文件名或文件夹名
      "conversion_status": "success",
      "frames_count": 107
    },
    {
      "lerobot_episode_index": 1,
      "original_task": "pick and place",
      "original_task_episode_index": 1,
      "original_source_name": "episode_1.h5",  // 新增：原始文件名或文件夹名
      "conversion_status": "success",
      "frames_count": 98
    },
    {
      "lerobot_episode_index": 2,
      "original_task": "pick and place",
      "original_task_episode_index": 3,  // ⚠️ 注意：跳过了原始episode 2
      "original_source_name": "episode_3.h5",  // 新增：原始文件名或文件夹名
      "conversion_status": "success",
      "frames_count": 105,
      "note": "原始episode 2因数据质量问题被跳过"
    }
    // ... 更多episodes
  ],
  
  "skipped_episodes_details": [
    {
      "original_task": "pick and place",
      "original_task_episode_index": 2,
      "original_source_name": "episode_2.h5",  // 新增：原始文件名或文件夹名
      "skip_reason": "DataQualityError: 帧数不匹配",
      "error_message": "视频帧数107 vs JSON数据105帧"
    },
    {
      "original_task": "pick and place",
      "original_task_episode_index": 12,
      "original_source_name": "episode_12",  // 新增：原始文件夹名（以文件夹为episode的情况）
      "skip_reason": "CriticalDataError: 关键数据缺失",
      "error_message": "缺少action数据"
    }
    // ... 所有被跳过的episodes
  ]
}

/**
 * 说明：
 * - original_source_name: 原始数据的标识
 *   - 如果是H5格式：文件名（如 "episode_0.h5"）
 *   - 如果是文件夹格式：文件夹名（如 "episode_0" 或 "2024-10-21_10-30-45"）
 *   - 如果是MCAP/Rosbag：bag文件名（如 "data_0001.mcap"）
 */
```

**实现要求**:
1. ✅ **必须在所有转换器中实现**
2. ✅ **每次转换都生成此文件**
3. ✅ **记录跳过原因和错误信息**
4. ✅ **保存在meta/目录下**

**代码位置**: 
- 基类方法: `LerobotFormatConverter._save_episode_source_mapping()`
- 调用时机: `convert()` 方法结束前

---

### 2.5 原始数据绝对路径映射文件

**背景**:
- 某些机器人的数据集需要记录**每个episode的原始数据文件绝对路径**
- 用于数据溯源、问题调试、数据审计
- 例如：知道LeRobot的episode_000123对应哪个H5文件、哪个视频文件

**文件位置**: `<output_path>/meta/original_data_paths.json`

**文件格式**:
```json
{
  "dataset_info": {
    "dataset_uuid": "xxx-yyy-zzz",
    "dataset_name": "算法采集_PCB",
    "original_dataset_root": "/mnt/nas/synnas/docker2/外部数据/智平方/...",
    "conversion_date": "2025-10-21T18:30:00"
  },
  
  "episodes": [
    {
      "lerobot_episode_index": 0,
      "original_task": "pick and place",
      "original_task_episode_index": 0,
      
      "source_files": {
        "h5_file": "/mnt/nas/.../task_1/episode_0.h5",
        "videos": {
          "cam_high": "/mnt/nas/.../task_1/episode_0/cam_high.mp4",
          "cam_left_wrist": "/mnt/nas/.../task_1/episode_0/cam_left_wrist.mp4",
          "cam_right_wrist": "/mnt/nas/.../task_1/episode_0/cam_right_wrist.mp4"
        },
        "json_file": null,  // 如果有的话
        "mcap_file": null   // 如果有的话
      },
      
      "file_metadata": {
        "h5_size_mb": 245.6,
        "total_video_size_mb": 1024.3,
        "modification_time": "2025-09-15T10:23:45"
      }
    },
    
    {
      "lerobot_episode_index": 1,
      "original_task": "pick and place",
      "original_task_episode_index": 1,
      
      "source_files": {
        "h5_file": "/mnt/nas/.../task_1/episode_1.h5",
        "videos": {
          "cam_high": "/mnt/nas/.../task_1/episode_1/cam_high.mp4",
          "cam_left_wrist": "/mnt/nas/.../task_1/episode_1/cam_left_wrist.mp4",
          "cam_right_wrist": "/mnt/nas/.../task_1/episode_1/cam_right_wrist.mp4"
        }
      },
      
      "file_metadata": {
        "h5_size_mb": 198.2,
        "total_video_size_mb": 892.1,
        "modification_time": "2025-09-15T10:45:12"
      }
    }
    // ... 所有转换成功的episodes
  ],
  
  "statistics": {
    "total_episodes": 95,
    "total_h5_size_gb": 22.3,
    "total_video_size_gb": 87.6,
    "format_type": "h5_mp4"
  }
}
```

**实现要求**:
1. ✅ **记录所有原始文件的绝对路径**
2. ✅ **区分不同文件类型（H5, MP4, JSON, MCAP等）**
3. ✅ **记录文件大小和修改时间**
4. ✅ **保存在meta/目录下**
5. ✅ **通过converter config控制是否生成此文件**

**配置控制**:
在每个converter config文件中添加可选字段：
```yaml
# converter_config_zhipingfang_dual_arm_no_pose.yaml
fps: 30

# 新增：控制是否保存原始数据绝对路径
save_original_data_paths: true  # true/false，默认false

features:
  observation:
    images:
      # ...
```

**适用范围**:
- 只有设置了 `save_original_data_paths: true` 的device_model才会生成此文件
- 建议对需要严格数据溯源的device_model启用（如关键机器人、特殊数据集）

**代码实现**:
```python
# 在 LerobotFormatConverter 基类中添加
def _save_original_data_paths(self):
    """保存原始数据文件的绝对路径映射（仅当config中启用时）"""
    # 检查配置文件中是否启用此功能
    if not self.converter_config.get('save_original_data_paths', False):
        self.logger.info("跳过保存原始数据路径映射（config中未启用）")
        return
    
    self.logger.info("生成原始数据路径映射文件...")
    mapping = {
        "dataset_info": {...},
        "episodes": [],
        "statistics": {...}
    }
    
    for lerobot_ep_idx in range(self.dataset.total_episodes):
        episode_info = self._get_episode_source_info(lerobot_ep_idx)
        mapping["episodes"].append(episode_info)
    
    output_path = self.output_path / "meta" / "original_data_paths.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
    
    self.logger.info(f"✓ 原始数据路径映射已保存: {output_path}")

# 每个转换器需要实现
@abstractmethod
def _get_episode_source_info(self, lerobot_ep_idx: int) -> dict:
    """
    返回该episode的原始文件信息
    
    Returns:
        {
            "lerobot_episode_index": int,
            "original_task": str,
            "original_task_episode_index": int,
            "source_files": {...},
            "file_metadata": {...}
        }
    """
    raise NotImplementedError
```

**示例实现（H5+MP4转换器）**:
```python
# lerobot_format_converter_h5_mp4.py
def _get_episode_source_info(self, lerobot_ep_idx: int) -> dict:
    # 从内部映射表获取原始task和episode索引
    task_path, task_ep_idx = self._lerobot_to_original_mapping[lerobot_ep_idx]
    
    h5_path = task_path / f"episode_{task_ep_idx}.h5"
    video_dir = task_path / f"episode_{task_ep_idx}"
    
    source_files = {
        "h5_file": str(h5_path.absolute()),
        "videos": {}
    }
    
    # 收集所有视频文件
    for cam_config in self.converter_config['features']['observation']['images']:
        cam_name = cam_config['cam_name']
        video_path = video_dir / f"{cam_name}.mp4"
        if video_path.exists():
            source_files["videos"][cam_name] = str(video_path.absolute())
    
    # 收集文件元数据
    h5_size = h5_path.stat().st_size / (1024**2) if h5_path.exists() else 0
    video_size = sum(
        Path(v).stat().st_size / (1024**2) 
        for v in source_files["videos"].values()
        if Path(v).exists()
    )
    
    return {
        "lerobot_episode_index": lerobot_ep_idx,
        "original_task": task_path.name,
        "original_task_episode_index": task_ep_idx,
        "original_source_name": h5_path.name,  # 新增：原始文件名
        "source_files": source_files,
        "file_metadata": {
            "h5_size_mb": round(h5_size, 2),
            "total_video_size_mb": round(video_size, 2),
            "modification_time": datetime.fromtimestamp(
                h5_path.stat().st_mtime
            ).isoformat() if h5_path.exists() else None
        }
    }

# 对于以文件夹为episode的转换器（如MP4+JSON）:
def _get_episode_source_info(self, lerobot_ep_idx: int) -> dict:
    task_path, task_ep_idx = self._lerobot_to_original_mapping[lerobot_ep_idx]
    episode_dir = task_path / f"episode_{task_ep_idx}"
    
    return {
        "lerobot_episode_index": lerobot_ep_idx,
        "original_task": task_path.name,
        "original_task_episode_index": task_ep_idx,
        "original_source_name": episode_dir.name,  # 新增：原始文件夹名
        "source_files": {...},
        "file_metadata": {...}
    }
```

---

### 2.6 实施计划：Mapping文件生成

**优先级**: 🔴 P0（与容错机制同步实施）

**⚠️ 重要**: **暂缓实施，先完成以下前置工作**:
1. 确认所有技术方案和设计决策
2. 完成性能优化规划
3. 完成Schema Discovery和配置文件修复
4. 然后再统一实施Mapping文件

**实施步骤**（待后续执行）:

1. **阶段0.1: 完善基类方法** (1天)
   - [ ] 在 `LerobotFormatConverter` 中实现 `_save_episode_source_mapping()`
   - [ ] 添加 `original_source_name` 字段支持
   - [ ] 实现 `_save_original_data_paths()`（检查config中的开关）
   - [ ] 定义 `_get_episode_source_info()` 抽象方法
   - [ ] 在 `convert()` 末尾自动调用这两个方法

2. **阶段0.2: 实现各转换器** (2-3天)
   - [ ] `LerobotFormatConverterHdf5`: 实现 `_get_episode_source_info()`
   - [ ] `LerobotFormatConverterMp4Json`: 实现 `_get_episode_source_info()`
   - [ ] `LerobotFormatConverterH5Mp4`: 实现 `_get_episode_source_info()`
   - [ ] `LerobotFormatConverterMcap`: 实现 `_get_episode_source_info()`
   - [ ] `LerobotFormatConverterRosbag`: 实现 `_get_episode_source_info()`
   - [ ] `LerobotFormatConverterJpgJson`: 实现 `_get_episode_source_info()`
   - [ ] `LerobotFormatConverterLejuWaibu`: 实现 `_get_episode_source_info()`
   - [ ] `LerobotFormatConverterG1`: 实现 `_get_episode_source_info()`
   - [ ] `LerobotFormatConverterMmk2`: 实现 `_get_episode_source_info()`

3. **阶段0.3: 更新converter config** (0.5天)
   - [ ] 为需要原始路径映射的device_model添加 `save_original_data_paths: true`

4. **阶段0.4: 测试验证** (1天)
   - [ ] 运行测试转换，验证生成的JSON文件
   - [ ] 检查 `original_source_name` 字段正确性
   - [ ] 验证 `save_original_data_paths` 开关生效
   - [ ] 验证跳过episode的记录

5. **阶段0.5: 编写查询工具** (0.5天)
   ```python
   # scripts/mapping_tools/query_episode_source.py
   def query_by_lerobot_index(dataset_path: Path, episode_index: int):
       """根据LeRobot索引查询原始文件"""
       pass
   
   def query_skipped_episodes(dataset_path: Path):
       """查询所有被跳过的episodes"""
       pass
   
   def verify_source_files_exist(dataset_path: Path):
       """验证所有原始文件是否仍然存在"""
       pass
   ```

---

## ⚡ 性能优化规划（P0 - 几十万Episodes的核心需求）

### 背景
- **数据规模**: 几十万条episodes需要转换
- **时间敏感**: 需要尽快完成转换
- **性能目标**: 最大化转换速度，最小化资源消耗

### 3.1 转换速度瓶颈分析

#### 当前瓶颈（预估）:
1. **视频读取** - 🔴 最大瓶颈
   - 当前：加载整个视频到内存
   - 问题：OOM、慢
   - 影响：每个episode数秒到数十秒

2. **H5文件I/O** - 🟡 中等瓶颈
   - 当前：每次读取都打开关闭文件
   - 问题：频繁I/O
   - 优化：缓存H5 file handle

3. **数据序列化** - 🟡 中等瓶颈
   - LeRobot格式写入parquet
   - 优化：批量写入

4. **网络I/O** - 🟢 较小瓶颈
   - 分布式环境下的client-server通信
   - 优化：减少通信频率

5. **预验证** - 🟢 较小瓶颈
   - `_prevalidate_files()` 可能扫描大量文件
   - 优化：缓存验证结果

### 3.2 性能优化方案

#### 🔥 P0优化（立即实施）

**1. 视频延迟加载**
```python
# 当前（慢）:
videos = [load_all_frames(video_path)]  # 18GB内存，30秒

# 优化后（快）:
videos = LazyVideoReader(video_path)  # <100MB内存，1秒
frame = videos.get_frame(idx)  # 按需读取
```

**预期提升**: 
- 内存: 18GB → <2GB (90%减少)
- 速度: 30秒 → 5秒 (6x加速)
- OOM错误: 完全消除

**2. H5文件句柄缓存**
```python
# 当前:
for frame in frames:
    with h5py.File(h5_path) as f:  # 每帧都打开关闭
        data = f['observations'][frame]

# 优化:
with h5py.File(h5_path) as f:  # 打开一次
    for frame in frames:
        data = f['observations'][frame]
```

**预期提升**: 10-20% 加速

**3. 使用ffprobe获取帧数（已完成✅）**
- 不解码视频，快速获取帧数
- 从30秒 → <1秒

#### 🟡 P1优化（后续实施）

**4. 批量写入优化**
```python
# 当前:
for frame in frames:
    dataset.add_frame(frame)  # 每帧都可能触发I/O

# 优化:
frames_batch = []
for frame in frames:
    frames_batch.append(frame)
    if len(frames_batch) >= 100:
        dataset.add_frames_batch(frames_batch)
        frames_batch = []
```

**预期提升**: 5-10% 加速

**5. 多进程并行转换**
- 当前：8个client并行（已有✅）
- 优化：根据机器资源调整client数量
- 监控CPU、内存、I/O使用率

**6. 预验证结果缓存**
```python
# 当前:
每次转换都运行 _prevalidate_files()

# 优化:
第一次验证后缓存结果到数据库
后续转换跳过验证
```

**预期提升**: 减少启动时间

### 3.3 分布式优化

**7. 任务分配策略优化**
- 按数据集大小分配（大的优先）
- 避免所有client同时处理超大数据集
- 负载均衡

**8. 进度上报优化**
- 减少上报频率（每10 episodes上报一次）
- 异步上报，不阻塞转换

**9. 数据库查询优化**
- 添加必要的索引
- 批量查询，减少数据库访问次数

### 3.4 估算转换时间

**假设**:
- 总episodes: 300,000
- 平均帧数: 100帧/episode
- Client数量: 8

**当前性能（未优化）**:
- 单episode时间: ~30秒（视频加载占大部分）
- 总时间: 300,000 × 30秒 / 8 / 3600 = **312.5小时** (13天)

**优化后性能（视频延迟加载）**:
- 单episode时间: ~5秒
- 总时间: 300,000 × 5秒 / 8 / 3600 = **52小时** (2.2天)

**进一步优化（延迟加载+H5缓存+批量写入）**:
- 单episode时间: ~3秒
- 总时间: 300,000 × 3秒 / 8 / 3600 = **31小时** (1.3天)

**🎯 目标**: **2天内完成30万episodes转换**

### 3.5 实施优先级

```
立即实施（开工前）:
├─ ✅ ffprobe帧数获取（已完成）
├─ 🔥 视频延迟加载（P0，必须）
├─ 🔥 H5文件句柄缓存（P0，简单）
└─ 🔥 监控和调优脚本（P0，观察性能）

转换过程中优化（迭代）:
├─ 批量写入优化（P1）
├─ 预验证缓存（P1）
└─ 任务分配策略（P1）

后续优化（非紧急）:
├─ 进度上报优化（P2）
└─ 数据库查询优化（P2）
```

### 3.6 性能监控

**需要监控的指标**:
- 每个episode的转换时间
- 内存使用峰值
- CPU使用率
- I/O等待时间
- 失败率和重试次数
- Client的任务处理速度

**监控工具**:
```python
# scripts/monitoring/conversion_monitor.py
def monitor_conversion_performance():
    """实时监控转换性能"""
    - 查询数据库统计完成数量
    - 计算平均转换速度
    - 预估剩余时间
    - 检测慢速client
    - 检测异常
```

---

### 阶段2: 分布式系统关键决策

#### 🎯 决策1: 严格模式应该如何处理？

**背景**: 
- 严格模式初衷是快速发现配置错误
- 但在分布式环境下，ConfigError → TASK_FAILED → 需要重新入库，很麻烦
- 更严重的是，前面已成功转换的episodes会丢失

**选项A: 保持现状（严格模式抛ConfigError）**
```python
# 优点:
- 快速失败，节省时间
- 明确指出配置问题

# 缺点:
- 分布式环境下返工成本高
- 已转换的episodes丢失
```

**选项B: 严格模式降级为警告**
```python
# 修改: _convert_episode_with_fault_tolerance
if is_strict:
    # 不抛ConfigError，而是记录警告
    logger.warning(f"严格模式检测到问题: {e}")
    # 仍然跳过episode，但不停止整个转换
    raise CriticalDataError(...) from e

# 优点:
- 不会导致任务失败
- 已转换数据不会丢失

# 缺点:
- 如果真是配置错误，会浪费时间转换整个数据集
- 需要事后分析日志才能发现配置问题
```

**选项C: 分离验证和转换阶段**
```python
# 新增: 快速验证模式
converter.validate_only(num_episodes=3)
  # 只验证前3个episodes，不实际转换
  # 发现问题立即返回
  # 验证通过后再执行实际转换

# Pipeline:
1. Test阶段先运行 validate_only
2. 验证失败 → 标记为配置问题，不进入转换
3. 验证通过 → 再运行完整转换（非严格模式）

# 优点:
- 保留快速失败的好处
- 实际转换阶段不会因配置问题失败
- 即使转换阶段有问题，也是数据问题（可以跳过episode）

# 缺点:
- 需要额外实现validate_only
- Pipeline更复杂
```

**🤔 你倾向于哪个选项？**

#### 🎯 决策2: PROCESSING卡住问题如何解决？

**背景**: 客户端崩溃/断线后，任务永久卡在PROCESSING状态

**方案A: 任务超时机制**
```python
# 在Server中添加定时检查
def reset_stale_tasks():
    """重置超过24小时仍在PROCESSING的任务"""
    with db.session() as session:
        stale_tasks = session.query(LeFormatConvertDB).filter(
            LeFormatConvertDB.convert_status == TaskStatus.PROCESSING,
            LeFormatConvertDB.updated_at < datetime.now() - timedelta(hours=24)
        ).all()
        
        for task in stale_tasks:
            task.convert_status = TaskStatus.PENDING
            task.err_message = "任务超时，自动重置"
            logger.warning(f"重置超时任务: {task.dataset_uuid}")

# 优点: 自动恢复
# 缺点: 24小时太长？或者某些数据集转换真的需要很久？
```

**方案B: 心跳/进度上报机制**
```python
# Client定期上报进度
class LeFormatConverterTaskClient:
    def _sync_process_task(self, task_content):
        converter = create_converter(...)
        total_episodes = converter.get_episodes_num()
        
        for ep_idx, result in enumerate(converter.convert()):
            # 每转换一个episode就上报进度
            self.report_progress({
                "dataset_uuid": task_content['dataset_uuid'],
                "progress": (ep_idx + 1) / total_episodes,
                "current_episode": ep_idx
            })
        
        return {}

# Server记录最后上报时间
# 如果超过1小时没上报 → 认为客户端已死 → 重置任务

# 优点: 更快发现问题，可以看到实时进度
# 缺点: 需要修改通信协议，实现复杂度高
```

**方案C: 手动重置工具**
```python
# scripts/db_tools/reset_stuck_tasks.py
def list_stuck_tasks():
    """列出所有可能卡住的任务"""
    pass

def reset_task(dataset_uuid: str):
    """手动重置指定任务"""
    pass

# 优点: 简单，立即可用
# 缺点: 需要人工介入
```

**方案D: 组合方案（推荐）**
- 实现方案C（手动工具）- 立即可用
- 实现方案A（超时机制）- 自动化，设置合理超时时间（如48小时）
- 方案B作为后续优化

**🤔 你觉得呢？**

---

## 📅 重新规划的实施时间线

### 🎯 阶段划分原则
1. **先讨论决策，后统一实施**
2. **性能优化优先**（几十万episodes，速度至关重要）
3. **配置修复优先**（避免大量数据转换失败）

---

### 阶段-1: 决策和规划（当前，3-5天）

**目标**: 确定所有技术方案，避免返工

- [ ] **Day 1-2: 关键决策讨论**
  - [ ] 严格模式处理方式（选项A/B/C）
  - [ ] PROCESSING卡住问题解决方案（方案A/B/C/D）
  - [ ] 确认需要优先处理的device_model
  - [ ] 确认数据集位置和规模

- [ ] **Day 3-4: Schema Discovery工具**
  - [ ] 实现H5/JSON/MCAP schema发现
  - [ ] 小规模测试（抽样10-20个数据集）
  - [ ] 生成初步报告

- [ ] **Day 5: 分析和规划**
  - [ ] 分析Schema Discovery结果
  - [ ] 评估配置文件修复工作量
  - [ ] 制定详细实施计划

---

### 阶段0: 核心性能优化（紧急，2-3天）

**目标**: 实现关键性能优化，提升6-10倍速度

- [ ] **Day 1: 视频延迟加载**
  - [ ] 重构MP4+JSON converter
  - [ ] 重构H5+MP4 converter
  - [ ] 重构Leju Waibu converter

- [ ] **Day 2: H5缓存优化**
  - [ ] 修改所有H5转换器的文件句柄管理
  - [ ] 测试内存使用和速度提升

- [ ] **Day 3: 监控工具**
  - [ ] 实现转换性能监控脚本
  - [ ] 实现PROCESSING卡住问题的手动重置工具
  - [ ] 测试验证

---

### 阶段1: 配置文件修复（3-5天）

**目标**: 修复配置文件，减少转换失败率

- [ ] **Day 1-2: 配置诊断**
  - [ ] 实现配置诊断工具
  - [ ] 运行诊断，生成修复建议
  - [ ] 优先处理高频device_model

- [ ] **Day 3-4: 交互式修复**
  - [ ] 修复top 5 device_model的配置
  - [ ] 测试验证

- [ ] **Day 5: device_model_annotation确认**
  - [ ] 实现自动验证工具
  - [ ] 批量验证并修正

---

### 阶段2: Mapping文件和分布式优化（2-3天）

**目标**: 实现追溯功能，优化分布式系统

- [ ] **Day 1: Mapping文件实现**
  - [ ] 实现基类方法（含`original_source_name`）
  - [ ] 实现各转换器的`_get_episode_source_info()`
  - [ ] 更新需要的converter config（添加`save_original_data_paths`）

- [ ] **Day 2: 分布式优化**
  - [ ] 实现严格模式优化方案（根据决策）
  - [ ] 实现PROCESSING重置机制（根据决策）
  - [ ] 任务分配策略优化

- [ ] **Day 3: 测试和验证**
  - [ ] 端到端测试
  - [ ] 验证Mapping文件生成
  - [ ] 验证性能提升

---

### 阶段3: 小规模测试（2天）

**目标**: 验证整个流程，发现问题

- [ ] **Day 1: 测试环境准备**
  - [ ] 选择代表性数据集（各device_model）
  - [ ] 填充测试数据库
  - [ ] 启动Server和Clients

- [ ] **Day 2: 运行和分析**
  - [ ] 运行测试转换
  - [ ] 监控性能指标
  - [ ] 收集失败案例
  - [ ] 迭代修复

---

### 阶段4: 大规模转换（持续，2-3天）

**目标**: 转换几十万episodes

- [ ] **启动前检查**
  - [ ] 所有配置文件已修复
  - [ ] 性能优化已生效
  - [ ] 监控工具已就绪
  - [ ] 备份策略已制定

- [ ] **转换执行**
  - [ ] 批量填充正式转换数据库
  - [ ] 启动Server（非test模式）
  - [ ] 启动多个Clients（根据资源调整数量）
  - [ ] 持续监控进度和性能

- [ ] **问题处理**
  - [ ] 实时处理PROCESSING卡住问题
  - [ ] 分析失败案例
  - [ ] 必要时调整策略

---

### 📊 总时间估算

| 阶段 | 天数 | 累计 |
|------|------|------|
| 阶段-1: 决策和规划 | 3-5天 | 3-5天 |
| 阶段0: 核心性能优化 | 2-3天 | 5-8天 |
| 阶段1: 配置文件修复 | 3-5天 | 8-13天 |
| 阶段2: Mapping和分布式优化 | 2-3天 | 10-16天 |
| 阶段3: 小规模测试 | 2天 | 12-18天 |
| 阶段4: 大规模转换 | 2-3天 | 14-21天 |

**总计**: **2-3周**（工作日14-21天）

**🎯 目标**: 
- **第1周**: 完成所有准备工作（决策+优化+修复）
- **第2周**: 测试和开始大规模转换
- **第3周**: 完成转换，处理遗留问题

---

## ❓ 需要你回答的问题

1. **🔥 Mapping文件实施（新增需求）**:
   - 我应该立即开始实现Episode Source Mapping吗？
   - 所有device_model都需要原始数据绝对路径映射，还是只有特定的？
   - 哪些device_model是高优先级？

2. **数据集位置**: 
   - 数据集存储在哪里？（如 `/mnt/nas/...`）
   - 有多少个数据集？
   - 有哪些device_model？

3. **优先级确认**:
   - 哪些device_model需要优先处理？
   - 还是全部一起处理？

4. **分布式系统决策**:
   - 严格模式: 选项A/B/C？
   - PROCESSING卡住: 方案A/B/C/D？

5. **Schema Discovery**:
   - 我现在就开始写Schema Discovery工具吗？
   - 还是先完成Mapping文件？

6. **时间线**:
   - 上面的5周时间线合理吗？（新增Week 0）
   - 需要加速或调整吗？

---

## 📝 总结

### ✅ 已完成
1. Episode级容错机制（跳过整个episode，保持时序连续）
2. 异常类体系（ConfigError, DataQualityError, CriticalDataError）
3. 帧数工具（ffprobe集成，快速获取帧数）
4. 测试脚本（test_fault_tolerance.py）
5. 部分转换器的Episode Source Mapping

### 🔥 关键更新（基于用户反馈）

#### 1. Mapping文件需求明确
- **Episode Source Mapping** (`episode_source_mapping.json`)
  - ✅ **新增**: `original_source_name` 字段（文件名或文件夹名）
  - 记录LeRobot索引到原始索引的映射
  - 记录跳过原因和错误信息
  - **所有转换器必须实现**

- **原始数据绝对路径Mapping** (`original_data_paths.json`)
  - ✅ **配置控制**: 通过 `save_original_data_paths: true/false` 控制
  - 只有特定device_model需要
  - **暂缓实施**，等待所有决策确定

#### 2. 性能优化为最高优先级
- **数据规模**: 几十万episodes
- **时间目标**: 2-3天完成转换
- **核心优化**:
  - 视频延迟加载：6倍加速，消除OOM
  - H5文件句柄缓存：10-20%加速
  - 监控工具：实时追踪性能

**预期提升**: 从13天 → 1.3天（10倍加速）

#### 3. 实施策略调整
- ⚠️ **先讨论决策，后统一实施**
- ⚠️ **暂缓Mapping文件实施**
- ✅ **优先完成**:
  1. 关键决策（严格模式、PROCESSING卡住）
  2. Schema Discovery
  3. 性能优化
  4. 配置文件修复

### 🎯 当前阶段：决策和规划（阶段-1）

#### 需要立即决策的问题
1. **严格模式处理**: 选项A（现状）/ B（警告）/ C（分离验证）？
2. **PROCESSING卡住**: 方案A（超时）/ B（心跳）/ C（手动）/ D（组合）？

#### 需要你提供的信息
1. **数据集位置和规模**
2. **优先处理的device_model**
3. **哪些device_model需要 `save_original_data_paths: true`**
4. **对性能优化目标的确认**（2天内完成30万episodes可行吗？）

### 📅 更新后的时间线

| 阶段 | 内容 | 天数 | 状态 |
|------|------|------|------|
| **阶段-1** | 决策和规划 | 3-5天 | 📍 当前 |
| **阶段0** | 核心性能优化 | 2-3天 | ⏳ 待定 |
| **阶段1** | 配置文件修复 | 3-5天 | ⏳ 待定 |
| **阶段2** | Mapping+分布式优化 | 2-3天 | ⏳ 待定 |
| **阶段3** | 小规模测试 | 2天 | ⏳ 待定 |
| **阶段4** | 大规模转换 | 2-3天 | ⏳ 待定 |

**总计**: 14-21天（2-3周）

### 🚀 下一步行动

**立即（当前对话）**:
1. 回答关键决策问题
2. 提供数据集信息
3. 确认性能目标是否合理

**然后（根据决策）**:
1. 实现Schema Discovery工具
2. 分析配置文件问题
3. 实施核心性能优化

**最后**:
1. 测试验证
2. 大规模转换（几十万episodes）

