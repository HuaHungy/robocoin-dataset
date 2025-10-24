# Mapping文件生成问题分析与修复方案

**日期**: 2025-10-23  
**状态**: 🔴 发现问题，待修复  
**优先级**: P0 - 高优先级

---

## 📋 问题总结

通过代码审查发现，**两个mapping文件的生成都存在问题**：

1. ❌ **`episode_source_mapping.json`** - 缺少跳过episodes的详细信息
2. ❌ **原始数据绝对路径mapping** - 完全未实现

---

## 🔍 问题1: episode_source_mapping.json 缺失跳过episodes

### 当前实现问题

**问题代码位置**: `lerobot_format_converter.py` 第874-973行

```python
# convert()方法中
for task_ep_idx in range(episodes_num):
    try:
        converted_frames, skipped_frames = self._convert_episode_with_fault_tolerance(...)
        
        # Episode完全为空，跳过
        if converted_frames == 0 and skipped_frames == 0:
            # ❌ 问题：只记录到_conversion_stats，没有记录到episode_source_mapping
            self._conversion_stats['skip_details'].append({...})
            self.logger.info(f"⏭️ 跳过 episode {global_ep_idx}")
            continue  # ⚠️ 这里就跳过了，没有添加到mapping！
        
        # 成功转换才会记录mapping
        source_files = self._get_episode_source_files(task_path, task_ep_idx)
        self.episode_source_mapping[global_ep_idx] = {  # ✅ 只有成功的才记录
            "task": task,
            ...
        }
        
        yield (task, task_ep_idx, global_ep_idx)
        global_ep_idx += 1  # ⚠️ global_ep_idx只对成功的增加
        
    except CriticalDataError as e:
        # ❌ 跳过的episode也没有记录到mapping
        self._conversion_stats['skip_details'].append({...})
        continue  # ⚠️ 又跳过了
```

### 导致的后果

```json
// 当前生成的episode_source_mapping.json
{
  "dataset_info": {
    "total_episodes": 95  // ⚠️ 只包含成功转换的episodes
  },
  "episodes": [
    {
      "global_episode_index": 0,  // LeRobot索引
      "task_episode_index": 0     // ⚠️ 原始索引，但没说中间跳过了谁！
    },
    {
      "global_episode_index": 1,
      "task_episode_index": 1
    },
    {
      "global_episode_index": 2,
      "task_episode_index": 3  // ⚠️ 跳过了原始索引2，但mapping中不知道！
    }
    // ...
  ]
  // ❌ 完全缺失：skipped_episodes_details
}
```

**问题**:
- ✅ 能查到LeRobot索引 → 原始索引
- ❌ **不知道哪些原始索引被跳过了**
- ❌ **不知道为什么被跳过**
- ❌ **无法溯源跳过的episodes**

### 期望的正确格式

根据`COMPLETE_REFACTORING_PLAN.md`的设计（第372-420行）：

```json
{
  "dataset_info": {
    "total_original_episodes": 100,    // ✅ 原始总数
    "total_converted_episodes": 95,     // ✅ 成功转换数
    "skipped_episodes": 5,              // ✅ 跳过数
    "skipped_episode_indices": [2, 12, 34, 56, 78]  // ✅ 跳过的索引列表
  },
  
  "episodes": [
    {
      "lerobot_episode_index": 0,
      "original_task": "pick and place",
      "original_task_episode_index": 0,
      "original_source_name": "episode_0.h5",  // ✅ 源文件名
      "conversion_status": "success",
      "frames_count": 107
    },
    {
      "lerobot_episode_index": 1,
      "original_task_episode_index": 1,
      "original_source_name": "episode_1.h5",
      "conversion_status": "success",
      "frames_count": 98
    },
    {
      "lerobot_episode_index": 2,
      "original_task_episode_index": 3,
      "original_source_name": "episode_3.h5",
      "conversion_status": "success",
      "frames_count": 105,
      "note": "原始episode 2因数据质量问题被跳过"  // ✅ 说明
    }
  ],
  
  "skipped_episodes_details": [  // ✅ 关键：详细的跳过信息
    {
      "original_task": "pick and place",
      "original_task_episode_index": 2,
      "original_source_name": "episode_2.h5",
      "skip_reason": "DataQualityError: 帧数不匹配",
      "error_message": "视频帧数107 vs JSON数据105帧"
    },
    {
      "original_task": "pick and place",
      "original_task_episode_index": 12,
      "original_source_name": "episode_12",
      "skip_reason": "CriticalDataError: 关键数据缺失",
      "error_message": "缺少action数据"
    }
  ]
}
```

---

## 🔍 问题2: _get_episode_source_files未实现

### 当前实现问题

**代码位置**: `lerobot_format_converter.py` 第133-152行

```python
def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
    """获取 episode 的源文件信息（供子类重写）"""
    return {}  # ❌ 默认返回空字典！
```

**检查子类实现**:

```bash
$ grep -r "def _get_episode_source_files" src/robocoin_dataset/format_converter/tolerobot/

# 结果：
lerobot_format_converter.py:133:    def _get_episode_source_files(...)  # 基类
lerobot_format_converter_h5_jpg.py:XXX: def _get_episode_source_files(...)  # 只有H5+JPG实现了！
```

**结论**: 
- ❌ **H5单文件converter**: 未实现
- ❌ **H5+MP4 converter**: 未实现  
- ❌ **MP4+JSON converter**: 未实现
- ❌ **MCAP converter**: 未实现
- ❌ **ROSbag converter**: 未实现
- ✅ **H5+JPG converter**: 已实现（仅1个）
- ❌ **其他converters**: 未实现

### 导致的后果

```json
// 实际生成的mapping
{
  "episodes": [
    {
      "global_episode_index": 0,
      "source_files": {}  // ❌ 空的！无法溯源！
    }
  ]
}
```

**问题**:
- ❌ 无法知道LeRobot episode对应的原始文件路径
- ❌ 无法通过文件系统验证原始数据
- ❌ 数据溯源功能完全失效

---

## 🔍 问题3: 原始数据绝对路径mapping完全未实现

### 当前状态

**检查代码**:
```bash
$ grep -r "original_data_paths" src/robocoin_dataset/

# 结果：空！完全没有实现！
```

**结论**: 
- ❌ 没有`_save_original_data_paths()`方法
- ❌ 没有`_get_episode_source_info()`方法
- ❌ 没有配置开关`save_original_data_paths`的处理
- ❌ 完全未实现

### 期望的实现

根据`COMPLETE_REFACTORING_PLAN.md`的设计（第442-646行），应该有：

1. **配置文件中的开关**:
```yaml
# converter_config_zhipingfang_dual_arm_no_pose.yaml
save_original_data_paths: true  # ❌ 现在没有这个字段
```

2. **生成的文件**: `<output_path>/meta/original_data_paths.json`
```json
{
  "episodes": [
    {
      "lerobot_episode_index": 0,
      "source_files": {
        "h5_file": "/mnt/nas/.../episode_0.h5",  // ❌ 完全没有！
        "videos": {
          "cam_high": "/mnt/nas/.../cam_high.mp4"
        }
      },
      "file_metadata": {
        "h5_size_mb": 245.6,
        "total_video_size_mb": 1024.3
      }
    }
  ]
}
```

---

## 🔧 修复方案

### 修复1: 完善episode_source_mapping.json

#### 1.1 修改convert()方法 - 记录所有episodes

```python
# lerobot_format_converter.py
def convert(self, is_test: bool = False) -> Iterable[tuple[str, int, int]]:
    """转换数据集"""
    dataset = self._create_lerobot_dataset() if not is_test else None
    
    global_ep_idx = 0
    original_ep_counter = 0  # 🆕 原始episode计数器（包括跳过的）
    
    for task_path, task in self.path_task_dict.items():
        episodes_num = self._get_task_episodes_num(task_path)
        if is_test:
            episodes_num = 1
        
        for task_ep_idx in range(episodes_num):
            original_ep_counter += 1  # 🆕 每个原始episode都计数
            
            try:
                converted_frames, skipped_frames = self._convert_episode_with_fault_tolerance(...)
                
                # Episode完全为空，跳过
                if converted_frames == 0 and skipped_frames == 0:
                    # 🆕 记录跳过的episode到mapping
                    source_files = self._get_episode_source_files(task_path, task_ep_idx)
                    self.episode_source_mapping[f"skipped_{task_ep_idx}"] = {
                        "conversion_status": "skipped",
                        "task": task,
                        "task_path": str(task_path),
                        "task_ep_idx": task_ep_idx,
                        "original_ep_counter": original_ep_counter,
                        "source_files": source_files,
                        "skip_reason": "Empty episode or data quality issue",
                        "error_message": None,
                    }
                    continue
                
                # 成功转换的episode
                source_files = self._get_episode_source_files(task_path, task_ep_idx)
                self.episode_source_mapping[global_ep_idx] = {
                    "conversion_status": "success",  # 🆕 明确状态
                    "task": task,
                    "task_path": str(task_path),
                    "task_ep_idx": task_ep_idx,
                    "global_ep_idx": global_ep_idx,
                    "original_ep_counter": original_ep_counter,  # 🆕
                    "source_files": source_files,
                    "converted_frames": converted_frames,
                    "skipped_frames": skipped_frames,
                }
                
                yield (task, task_ep_idx, global_ep_idx)
                global_ep_idx += 1
                
            except CriticalDataError as e:
                # 🆕 记录跳过的episode
                source_files = self._get_episode_source_files(task_path, task_ep_idx)
                self.episode_source_mapping[f"skipped_{task_ep_idx}"] = {
                    "conversion_status": "skipped",
                    "task": task,
                    "task_path": str(task_path),
                    "task_ep_idx": task_ep_idx,
                    "original_ep_counter": original_ep_counter,
                    "source_files": source_files,
                    "skip_reason": "CriticalDataError",
                    "error_message": str(e),
                }
                continue
```

#### 1.2 修改save_episode_source_mapping() - 分离成功和跳过

```python
def save_episode_source_mapping(self, mapping_filename: str = "episode_source_mapping.json") -> None:
    """保存 episode 源文件映射到 JSON 文件"""
    import json
    from datetime import datetime
    
    if not self.episode_source_mapping:
        self.logger.warning("没有 episode 映射信息可保存")
        return
    
    # 🆕 分离成功和跳过的episodes
    successful_episodes = []
    skipped_episodes = []
    
    for key, episode_info in self.episode_source_mapping.items():
        if episode_info.get("conversion_status") == "success":
            successful_episodes.append(episode_info)
        elif episode_info.get("conversion_status") == "skipped":
            skipped_episodes.append(episode_info)
    
    # 🆕 按索引排序
    successful_episodes.sort(key=lambda x: x["global_ep_idx"])
    skipped_episodes.sort(key=lambda x: x["task_ep_idx"])
    
    # 构建映射文件数据
    mapping_data = {
        "dataset_info": {
            "source_dataset_path": str(self.dataset_path),
            "output_dataset_path": str(self.output_path),
            "repo_id": self.repo_id,
            "device_model": self.device_model or "unknown",
            "conversion_date": datetime.now().isoformat(),
            
            # 🆕 详细统计
            "total_original_episodes": len(self.episode_source_mapping),
            "total_converted_episodes": len(successful_episodes),
            "skipped_episodes": len(skipped_episodes),
            "skipped_episode_indices": [ep["task_ep_idx"] for ep in skipped_episodes],
            
            "fps": self.fps,
        },
        
        # 🆕 成功转换的episodes
        "episodes": [
            {
                "lerobot_episode_index": ep["global_ep_idx"],
                "original_task": ep["task"],
                "original_task_path": ep["task_path"],
                "original_task_episode_index": ep["task_ep_idx"],
                "original_source_name": self._extract_source_name(ep["source_files"]),  # 🆕
                "conversion_status": "success",
                "frames_count": ep["converted_frames"],
                "skipped_frames_count": ep["skipped_frames"],
                "source_files": ep["source_files"],
            }
            for ep in successful_episodes
        ],
        
        # 🆕 跳过的episodes详情
        "skipped_episodes_details": [
            {
                "original_task": ep["task"],
                "original_task_path": ep["task_path"],
                "original_task_episode_index": ep["task_ep_idx"],
                "original_source_name": self._extract_source_name(ep["source_files"]),  # 🆕
                "skip_reason": ep.get("skip_reason", "Unknown"),
                "error_message": ep.get("error_message"),
                "source_files": ep["source_files"],
            }
            for ep in skipped_episodes
        ]
    }
    
    # 保存到文件
    mapping_file_path = self.output_path / mapping_filename
    with open(mapping_file_path, 'w', encoding='utf-8') as f:
        json.dump(mapping_data, f, indent=2, ensure_ascii=False)
    
    self.logger.info(f"✅ Episode 源文件映射已保存: {mapping_file_path}")
    self.logger.info(f"   - 成功episodes: {len(successful_episodes)}")
    self.logger.info(f"   - 跳过episodes: {len(skipped_episodes)}")


def _extract_source_name(self, source_files: dict) -> str:
    """从source_files中提取主要的源文件名"""
    if "h5_file" in source_files:
        return Path(source_files["h5_file"]).name
    elif "mcap_file" in source_files:
        return Path(source_files["mcap_file"]).name
    elif "episode_directory" in source_files:
        return Path(source_files["episode_directory"]).name
    else:
        return "unknown"
```

### 修复2: 实现_get_episode_source_files()在所有converters

#### 2.1 H5单文件converter

```python
# lerobot_format_converter_hdf5.py
def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
    """获取H5单文件episode的源文件信息"""
    h5_files = self.task_episode_h5file_paths.get(task_path, [])
    
    if ep_idx < len(h5_files):
        h5_file = h5_files[ep_idx]
        return {
            "h5_file": str(h5_file.relative_to(self.dataset_path)),
            "absolute_h5_file": str(h5_file.absolute()),
        }
    
    return {}
```

#### 2.2 H5+MP4 converter

```python
# lerobot_format_converter_h5_mp4.py
def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
    """获取H5+MP4 episode的源文件信息"""
    h5_files = self._get_all_episode_h5_files(task_path)
    
    if ep_idx >= len(h5_files):
        return {}
    
    h5_file = h5_files[ep_idx]
    episode_dir = h5_file.parent / h5_file.stem  # episode_0.h5 -> episode_0/
    
    source_files = {
        "h5_file": str(h5_file.relative_to(self.dataset_path)),
        "absolute_h5_file": str(h5_file.absolute()),
        "videos": {}
    }
    
    # 收集所有视频文件
    for cam_config in self.converter_config['features']['observation']['images']:
        cam_name = cam_config['cam_name']
        video_file = episode_dir / f"{cam_name}.mp4"
        
        if video_file.exists():
            source_files["videos"][cam_name] = str(video_file.relative_to(self.dataset_path))
    
    return source_files
```

#### 2.3 MP4+JSON converter

```python
# lerobot_format_converter_mp4_json.py
def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
    """获取MP4+JSON episode的源文件信息"""
    episode_dirs = self._get_all_episode_dirs(task_path)
    
    if ep_idx >= len(episode_dirs):
        return {}
    
    episode_dir = episode_dirs[ep_idx]
    
    return {
        "episode_directory": str(episode_dir.relative_to(self.dataset_path)),
        "absolute_episode_directory": str(episode_dir.absolute()),
        "video_files": [str(f.relative_to(self.dataset_path)) for f in episode_dir.glob("*.mp4")],
        "json_files": [str(f.relative_to(self.dataset_path)) for f in episode_dir.glob("*.json")],
    }
```

#### 2.4 其他converters

类似地实现：
- MCAP converter
- ROSbag converter
- JPG+JSON converter
- Leju Waibu converter
- MMK2 converter
- G1 converter

### 修复3: 实现original_data_paths.json（可选）

#### 3.1 添加配置支持

```python
# lerobot_format_converter.py
def __init__(self, ...):
    # ...
    # 🆕 读取配置中的开关
    self.save_original_paths = self.converter_config.get('save_original_data_paths', False)
```

#### 3.2 实现保存方法

```python
def _save_original_data_paths(self, filename: str = "original_data_paths.json") -> None:
    """保存原始数据绝对路径映射（仅当config中启用时）"""
    if not self.save_original_paths:
        self.logger.info("跳过保存原始数据路径映射（config中未启用）")
        return
    
    self.logger.info("生成原始数据路径映射文件...")
    
    episodes_data = []
    total_size = 0
    
    for ep_info in self.episode_source_mapping.values():
        if ep_info.get("conversion_status") != "success":
            continue
        
        source_files = ep_info["source_files"]
        
        # 计算文件大小
        file_metadata = self._get_file_metadata(source_files)
        total_size += file_metadata.get("total_size_mb", 0)
        
        episodes_data.append({
            "lerobot_episode_index": ep_info["global_ep_idx"],
            "original_task": ep_info["task"],
            "original_task_episode_index": ep_info["task_ep_idx"],
            "source_files": source_files,
            "file_metadata": file_metadata,
        })
    
    mapping = {
        "dataset_info": {
            "source_dataset_path": str(self.dataset_path.absolute()),
            "output_dataset_path": str(self.output_path.absolute()),
            "conversion_date": datetime.now().isoformat(),
        },
        "episodes": episodes_data,
        "statistics": {
            "total_episodes": len(episodes_data),
            "total_size_gb": round(total_size / 1024, 2),
        }
    }
    
    output_path = self.output_path / "meta" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
    
    self.logger.info(f"✓ 原始数据路径映射已保存: {output_path}")


def _get_file_metadata(self, source_files: dict) -> dict:
    """获取源文件的元数据（大小、修改时间等）"""
    total_size = 0
    
    for key, value in source_files.items():
        if key.startswith("absolute_"):
            file_path = Path(value)
            if file_path.exists():
                total_size += file_path.stat().st_size / (1024**2)  # MB
    
    return {
        "total_size_mb": round(total_size, 2),
    }
```

#### 3.3 在convert()结束时调用

```python
# 在client.py中，convert()后调用
converter.save_episode_source_mapping()
converter._save_original_data_paths()  # 🆕
```

---

## 📅 修复实施计划

### Phase 1: 修复episode_source_mapping.json (高优先级, 1天)

**Day 1**:
- [ ] 修改`convert()`方法，记录所有episodes（包括跳过的）
- [ ] 修改`save_episode_source_mapping()`，分离成功和跳过episodes
- [ ] 添加`_extract_source_name()`辅助方法
- [ ] 测试验证

### Phase 2: 实现_get_episode_source_files() (高优先级, 1天)

**Day 2**:
- [ ] H5单文件converter实现
- [ ] H5+MP4 converter实现
- [ ] MP4+JSON converter实现
- [ ] MCAP converter实现
- [ ] ROSbag converter实现
- [ ] JPG+JSON converter实现（或检查现有实现）
- [ ] 其他converters实现
- [ ] 测试验证

### Phase 3: 实现original_data_paths.json (中优先级, 0.5天)

**Day 3**:
- [ ] 添加配置开关支持
- [ ] 实现`_save_original_data_paths()`
- [ ] 实现`_get_file_metadata()`
- [ ] 在converter config中添加开关
- [ ] 测试验证

### Phase 4: 全面测试 (0.5天)

**Day 4**:
- [ ] 测试所有converter的mapping文件生成
- [ ] 验证跳过episodes的记录
- [ ] 验证文件大小计算
- [ ] 端到端测试

---

## 🎯 修复后的效果

### 修复前（当前状态）

```json
// episode_source_mapping.json
{
  "dataset_info": {
    "total_episodes": 95  // ❌ 不知道原始有多少
  },
  "episodes": [
    {"global_episode_index": 0, "source_files": {}}  // ❌ 空的
    // ❌ 缺失skipped_episodes_details
  ]
}

// original_data_paths.json  ❌ 完全不存在
```

### 修复后（期望状态）

```json
// episode_source_mapping.json
{
  "dataset_info": {
    "total_original_episodes": 100,     // ✅ 原始总数
    "total_converted_episodes": 95,      // ✅ 成功数
    "skipped_episodes": 5,               // ✅ 跳过数
    "skipped_episode_indices": [2, 12, ...] // ✅ 明确列表
  },
  "episodes": [
    {
      "lerobot_episode_index": 0,
      "original_task_episode_index": 0,
      "original_source_name": "episode_0.h5",  // ✅ 源文件名
      "conversion_status": "success",
      "source_files": {                       // ✅ 详细信息
        "h5_file": "task_1/episode_0.h5",
        "videos": {...}
      }
    }
  ],
  "skipped_episodes_details": [  // ✅ 完整的跳过信息
    {
      "original_task_episode_index": 2,
      "original_source_name": "episode_2.h5",
      "skip_reason": "DataQualityError",
      "error_message": "帧数不匹配"
    }
  ]
}

// original_data_paths.json（启用时）
{
  "episodes": [
    {
      "lerobot_episode_index": 0,
      "source_files": {
        "absolute_h5_file": "/mnt/nas/.../episode_0.h5",  // ✅ 绝对路径
        "videos": {...}
      },
      "file_metadata": {  // ✅ 文件元数据
        "total_size_mb": 1269.9
      }
    }
  ],
  "statistics": {
    "total_size_gb": 120.5  // ✅ 统计信息
  }
}
```

---

## 📝 总结

### 发现的问题

1. ❌ **episode_source_mapping.json缺失跳过episodes**: 无法溯源被跳过的episodes
2. ❌ **_get_episode_source_files未实现**: 8/9的converters未实现，source_files为空
3. ❌ **original_data_paths.json未实现**: 完全缺失绝对路径映射

### 影响

- ❌ 数据溯源功能不完整
- ❌ 无法审计跳过的episodes
- ❌ 无法验证原始文件是否存在
- ❌ 不符合设计文档的要求

### 修复优先级

| 修复项 | 优先级 | 工作量 | 原因 |
|--------|--------|--------|------|
| episode_source_mapping.json跳过episodes | P0 | 0.5天 | 核心功能缺失 |
| _get_episode_source_files实现 | P0 | 1天 | 所有converters必需 |
| original_data_paths.json | P1 | 0.5天 | 可选功能，但很有用 |

### 建议

**立即执行**:
1. ✅ 修复episode_source_mapping.json（添加skipped_episodes_details）
2. ✅ 在所有converters中实现_get_episode_source_files()
3. 🔶 根据需求决定是否实现original_data_paths.json

**总工作量**: 1.5-2天

---

**文档版本**: v1.0  
**状态**: 问题分析完成，待修复  
**建议**: 优先修复P0问题，P1可后续实施

