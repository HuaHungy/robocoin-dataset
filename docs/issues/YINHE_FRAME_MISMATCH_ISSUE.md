# Yinhe数据集帧数不匹配问题详细说明

**数据集**: `yinhe:default_version`  
**格式**: MP4+JSON  
**发现时间**: 2025-10-23  
**问题状态**: ❌ 数据完整性问题（非Episode定位问题）

---

## 📋 问题概述

在配置验证过程中，`yinhe:default_version` 数据集在Converter实例化阶段失败，报错为**视频帧数与JSON数据帧数不匹配**。

### 错误信息

```
❌ Converter实例化失败: 无法创建converter实例 'LerobotFormatConverterMp4Json': 
❌ MP4+JSON帧数不匹配
❌ Video frame count mismatch
```

---

## 🔍 问题分析

### 1. 数据格式

**Yinhe数据集结构** (MP4+JSON格式):
```
yinhe:default_version/
├── local_dataset_info.yaml
└── [task_directory]/
    ├── local_task_info.yaml
    └── episode_xxx/
        ├── camera_video.mp4    # 视频文件
        ├── actions.json        # 动作数据
        └── observations.json   # 观测数据
```

### 2. 帧数不匹配具体表现

**MP4+JSON格式的帧数验证逻辑** (在`_prevalidate_files`中):

```python
class LerobotFormatConverterMp4Json(LerobotFormatConverter):
    def _prevalidate_files(self) -> None:
        """验证文件完整性，包括帧数一致性"""
        for task_path in self.path_task_dict.keys():
            for episode_dir in self._get_all_episode_dirs(task_path):
                # 1. 获取视频帧数（使用ffprobe）
                video_frames = self._get_video_frame_count(episode_dir / "camera_video.mp4")
                
                # 2. 获取JSON数据帧数
                with open(episode_dir / "actions.json") as f:
                    actions_data = json.load(f)
                    json_frames = len(actions_data)
                
                # 3. 验证一致性
                if video_frames != json_frames:
                    raise DataQualityError(
                        f"❌ MP4+JSON帧数不匹配\n"
                        f"   视频帧数: {video_frames}\n"
                        f"   JSON帧数: {json_frames}\n"
                        f"   Episode: {episode_dir}"
                    )
```

### 3. 可能的原因

#### 原因1: 数据录制过程中断
- **场景**: 机器人录制过程中崩溃或中断
- **结果**: 视频录制完整，但JSON数据写入未完成
- **表现**: `video_frames > json_frames`

#### 原因2: 数据同步问题
- **场景**: 视频录制和JSON数据保存不同步
- **结果**: 两者帧数不一致
- **表现**: 可能是 `video_frames ≠ json_frames`

#### 原因3: 数据传输损坏
- **场景**: 从机器人传输数据到NAS时部分丢失
- **结果**: JSON文件不完整
- **表现**: JSON解析可能成功但数据条目缺失

#### 原因4: 后处理错误
- **场景**: 数据后处理（剪辑、过滤）时操作不一致
- **结果**: 视频和JSON处理结果不同步
- **表现**: 帧数差异

---

## 🧪 诊断步骤

### 步骤1: 确认ffprobe正常工作

```bash
# 检查ffprobe是否安装
which ffprobe

# 测试视频帧数获取
ffprobe -v error -select_streams v:0 \
  -count_packets -show_entries stream=nb_read_packets \
  -of csv=p=0 /path/to/yinhe/episode_xxx/camera_video.mp4
```

**验证结果**: ✅ ffprobe已安装且工作正常（v4.4.2）

### 步骤2: 手动检查具体episode

```bash
# 进入数据集目录
cd /home/liu/program/robocoin-dataset/data/yinhe:default_version

# 找到task目录
ls -la

# 检查具体episode
cd [task_directory]/episode_xxx

# 1. 检查视频帧数
ffprobe -v error -select_streams v:0 \
  -count_packets -show_entries stream=nb_read_packets \
  -of csv=p=0 camera_video.mp4

# 2. 检查JSON数据条目数
python3 -c "
import json
with open('actions.json') as f:
    data = json.load(f)
    print(f'Actions frames: {len(data)}')

with open('observations.json') as f:
    data = json.load(f)
    print(f'Observations frames: {len(data)}')
"
```

### 步骤3: 统计所有episode的帧数差异

```python
# scripts/diagnostics/check_yinhe_frame_consistency.py
import json
from pathlib import Path
from subprocess import run, PIPE

def check_episode_consistency(episode_dir: Path) -> dict:
    """检查单个episode的帧数一致性"""
    result = {
        "episode": episode_dir.name,
        "video_frames": None,
        "actions_frames": None,
        "observations_frames": None,
        "is_consistent": False,
        "error": None
    }
    
    try:
        # 获取视频帧数
        video_file = episode_dir / "camera_video.mp4"
        if video_file.exists():
            proc = run([
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-count_packets", "-show_entries", "stream=nb_read_packets",
                "-of", "csv=p=0", str(video_file)
            ], capture_output=True, text=True)
            result["video_frames"] = int(proc.stdout.strip())
        
        # 获取actions帧数
        actions_file = episode_dir / "actions.json"
        if actions_file.exists():
            with open(actions_file) as f:
                data = json.load(f)
                result["actions_frames"] = len(data)
        
        # 获取observations帧数
        obs_file = episode_dir / "observations.json"
        if obs_file.exists():
            with open(obs_file) as f:
                data = json.load(f)
                result["observations_frames"] = len(data)
        
        # 检查一致性
        frames = [result["video_frames"], result["actions_frames"], result["observations_frames"]]
        frames = [f for f in frames if f is not None]
        result["is_consistent"] = len(set(frames)) == 1
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

def check_all_episodes(dataset_path: Path):
    """检查所有episodes"""
    results = []
    
    for episode_dir in dataset_path.rglob("episode_*"):
        if episode_dir.is_dir():
            result = check_episode_consistency(episode_dir)
            results.append(result)
    
    # 统计
    total = len(results)
    consistent = sum(1 for r in results if r["is_consistent"])
    
    print(f"总episodes: {total}")
    print(f"一致: {consistent}")
    print(f"不一致: {total - consistent}")
    print(f"一致率: {consistent/total*100:.1f}%")
    
    # 显示不一致的episodes
    print("\n不一致的episodes:")
    for r in results:
        if not r["is_consistent"]:
            print(f"  {r['episode']}: video={r['video_frames']}, "
                  f"actions={r['actions_frames']}, obs={r['observations_frames']}")
    
    return results

if __name__ == "__main__":
    dataset_path = Path("/home/liu/program/robocoin-dataset/data/yinhe:default_version")
    results = check_all_episodes(dataset_path)
    
    # 保存详细报告
    import json
    with open("yinhe_frame_consistency_report.json", "w") as f:
        json.dump(results, f, indent=2)
```

---

## 💡 解决方案

### 方案1: 数据修复（推荐）

**适用场景**: 帧数差异较小（1-2帧），可以通过截断或补齐修复

#### 1.1 截断策略（保守）
```python
# 取最小帧数，截断较长的数据
min_frames = min(video_frames, json_frames)

# 截断视频
ffmpeg -i input.mp4 -vf "select='lt(n,{min_frames})'" -vsync 0 output.mp4

# 截断JSON
with open('actions.json') as f:
    data = json.load(f)
    data = data[:min_frames]
with open('actions_fixed.json', 'w') as f:
    json.dump(data, f)
```

#### 1.2 补齐策略（风险较高）
```python
# 如果JSON缺失帧，复制最后一帧
if json_frames < video_frames:
    with open('actions.json') as f:
        data = json.load(f)
        last_frame = data[-1]
        # 补齐
        data.extend([last_frame] * (video_frames - json_frames))
    with open('actions_fixed.json', 'w') as f:
        json.dump(data, f)
```

**注意**: 补齐策略会改变数据语义，需要谨慎评估！

### 方案2: 数据重新录制

**适用场景**: 帧数差异较大，或者数据质量要求严格

**步骤**:
1. 联系数据提供方（银河机器人团队）
2. 说明帧数不匹配问题
3. 请求重新录制或提供正确的数据

### 方案3: 跳过不一致的Episodes（临时）

**适用场景**: 需要快速完成转换，可以容忍部分数据丢失

**实施**:
- 容错机制已支持跳过单个episode
- 在 `episode_source_mapping.json` 中会记录跳过原因
- 不影响其他正常episodes的转换

```python
# LerobotFormatConverterMp4Json 已实现容错
# 帧数不匹配会被捕获为 DataQualityError
# 自动跳过该episode，记录到skipped_episodes_details
```

### 方案4: 配置宽松验证（不推荐）

**仅用于紧急情况，数据质量无法保证！**

```yaml
# converter_config_yinhe.yaml
# 添加配置项
features:
  validation:
    allow_frame_mismatch: true        # 允许帧数不匹配
    max_frame_difference: 2           # 最大允许差异2帧
    frame_mismatch_strategy: "truncate"  # 或 "skip"
```

---

## 📊 影响评估

### 数据损失

如果使用方案3（跳过）:
- **当前状态**: 1个dataset完全失败
- **使用容错后**: 只跳过不一致的episodes，保留其他正常episodes
- **数据保留率**: 取决于不一致episodes的比例

### 转换成功率影响

- **当前**: 0% (converter实例化即失败)
- **修复后**: 
  - 方案1/2: 100% (数据修复后)
  - 方案3: 50%-95% (取决于实际不一致比例)

---

## 🔧 后续行动

### 立即执行（必须）

1. **运行诊断脚本**
   ```bash
   cd /home/liu/program/robocoin-dataset
   python scripts/diagnostics/check_yinhe_frame_consistency.py
   ```

2. **分析诊断报告**
   - 查看不一致episodes的数量和分布
   - 评估帧数差异的大小
   - 决定采用哪种修复方案

### 短期行动（1-2天）

3. **数据修复或决策**
   - 如果差异小且数量少 → 方案1（截断修复）
   - 如果差异大或数量多 → 方案2（联系重新录制）
   - 如果时间紧急 → 方案3（跳过不一致episodes）

4. **重新验证**
   ```bash
   python scripts/config_validation/validate_local_datasets.py \
     --data-dir /home/liu/program/robocoin-dataset/data \
     --config-dir /home/liu/program/robocoin-dataset/scripts/format_converters/tolerobot/configs \
     --output-dir /home/liu/program/robocoin-dataset/outputs/yinhe_validation \
     --num-episodes 1 \
     --device-model yinhe
   ```

### 长期改进

5. **改进数据录制流程**
   - 添加实时帧数一致性检查
   - 录制完成后自动验证
   - 防止产生不一致数据

6. **增强验证机制**
   - 在converter config中添加宽松度配置
   - 支持自动修复小幅差异
   - 详细记录所有修复操作

---

## 📝 总结

### 问题性质
- ✅ **不是Episode定位问题** - episode能正确找到
- ✅ **不是配置文件问题** - converter配置正确
- ❌ **是数据完整性问题** - 原始数据本身帧数不一致

### 根本原因
- 数据录制、传输或后处理过程中的同步问题
- 需要从数据源头解决

### 推荐方案
1. **诊断优先**: 先运行检查脚本，了解问题规模
2. **数据修复**: 如果可行，截断到最小帧数
3. **容错处理**: 利用现有容错机制跳过问题episodes
4. **源头改进**: 改进数据录制流程，防止再次发生

### 关键文件
- **诊断脚本**: `scripts/diagnostics/check_yinhe_frame_consistency.py`
- **Converter**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_mp4_json.py`
- **配置文件**: `scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml`
- **数据路径**: `/home/liu/program/robocoin-dataset/data/yinhe:default_version`

---

**文档版本**: v1.0  
**最后更新**: 2025-10-23  
**负责人**: AI Assistant  
**状态**: 待诊断和修复

