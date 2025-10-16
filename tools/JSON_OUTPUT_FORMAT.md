# JSON 输出格式说明

## 📋 更新内容 (2025-10-16)

**重要变更**: JSON 输出文件现在**只包含有严重问题的 episodes**，不再保存所有 episodes 的完整数据。

### ✨ 优势

1. **文件大小显著减小**: 如果只有 0.1% 的 episodes 有问题，文件大小从 100MB+ 减少到几 KB
2. **更易定位问题**: 直接查看需要修复的数据，无需过滤
3. **更快的文件读写**: 减少 I/O 开销

### 📊 新的 JSON 结构

```json
{
  "summary": {
    "total_episodes": 3978,
    "episodes_with_problems": 3,
    "problem_rate": "0.08%",
    "test_mode": false,
    "full_mode": true
  },
  "problem_episodes": [
    {
      "episode_path": "/path/to/episode1",
      "has_problem": true,
      "json_frames": {
        "state_front_head_joint": 0,
        "camera_front_head_rgb": 791
      },
      "video_frames": {
        "camera_front_head_rgb.mp4": 791
      },
      "min_frames": 0,
      "problems": [
        {
          "type": "zero_frames",
          "severity": "error",
          "details": "Minimum frame count is 0, will cause conversion failure. Bottleneck: JSON:state_front_head_joint"
        }
      ],
      "warnings": []
    },
    {
      "episode_path": "/path/to/episode2",
      "has_problem": true,
      "problems": [
        {
          "type": "missing_videos",
          "severity": "error",
          "details": "Missing expected video files: camera_left_wrist.mp4"
        }
      ]
    }
  ]
}
```

### 🔍 字段说明

#### summary 部分
- `total_episodes`: 扫描的总 episode 数
- `episodes_with_problems`: 有严重问题的 episode 数
- `problem_rate`: 问题比例（百分比）
- `test_mode`: 是否为测试模式
- `full_mode`: 是否为完整扫描模式

#### problem_episodes 部分
**只包含 `has_problem: true` 的 episodes**

每个 problem episode 包含：
- `episode_path`: Episode 完整路径
- `has_problem`: 总是为 `true`
- `json_frames`: 各 JSON 字段的帧数
- `video_frames`: 各视频文件的帧数
- `min_frames`: 计算出的最小帧数
- `problems`: 严重问题列表（会导致转换失败）
  - `type`: 问题类型（zero_frames, missing_videos, video_read_error, etc.）
  - `severity`: 严重程度（error）
  - `details`: 问题详细描述
- `warnings`: 警告列表（不影响转换，可选）

### 📝 使用示例

#### Python 读取

```python
import json

# 读取结果
with open('yinhe_frame_check_results_full.json', 'r') as f:
    data = json.load(f)

# 查看汇总
summary = data['summary']
print(f"总共扫描: {summary['total_episodes']} episodes")
print(f"发现问题: {summary['episodes_with_problems']} episodes ({summary['problem_rate']})")

# 处理每个问题 episode
for episode in data['problem_episodes']:
    print(f"\n问题 Episode: {episode['episode_path']}")
    print(f"最小帧数: {episode['min_frames']}")
    
    # 查看具体问题
    for problem in episode['problems']:
        print(f"  ❌ [{problem['type']}] {problem['details']}")
```

#### 命令行快速查看

```bash
# 查看汇总信息
jq '.summary' yinhe_frame_check_results_full.json

# 查看问题数量
jq '.problem_episodes | length' yinhe_frame_check_results_full.json

# 查看所有问题 episode 的路径
jq '.problem_episodes[].episode_path' yinhe_frame_check_results_full.json

# 按问题类型统计
jq '.problem_episodes[].problems[].type' yinhe_frame_check_results_full.json | sort | uniq -c
```

### 🔄 旧版本兼容性

如果你需要旧版本的完整输出（包含所有 episodes），可以：

1. **手动修改脚本**: 注释掉过滤逻辑
2. **使用 Git 历史版本**: 回退到修改前的版本

但通常情况下，**只保存问题数据是更好的选择**，因为：
- ✅ 文件更小，更容易传输和存储
- ✅ 更快定位问题
- ✅ 正常的 episodes 不需要保存（它们可以安全转换）

### 📊 实际效果对比

以银河数据集为例（假设 3978 个 episodes，3 个有问题）：

| 项目 | 旧格式（全部保存） | 新格式（只保存问题） | 改进 |
|------|-----------------|-------------------|------|
| 文件大小 | ~150 MB | ~15 KB | **99.99%** ↓ |
| 加载时间 | ~5 秒 | <0.1 秒 | **50x** ↑ |
| 可读性 | 需要过滤查找 | 直接查看 | ✅ |
| 磁盘占用 | 高 | 极低 | ✅ |

### ⚠️  注意事项

1. **警告信息仍会保留**: `warnings` 字段会保留在问题 episodes 中（可选）
2. **正常 episodes 不保存**: 如果需要验证某个正常 episode，需要重新运行检查
3. **问题定义**: 只有 `has_problem: true` 的才会保存
   - ❌ 最小帧数为 0
   - ❌ 视频文件缺失
   - ❌ 视频读取失败
   - ❌ JSON 格式错误

### 🎯 建议工作流

1. **运行完整扫描**: 
   ```bash
   python check_yinhe_frame_mismatch_full.py
   ```

2. **查看问题数量**:
   ```bash
   jq '.summary' yinhe_frame_check_results_full.json
   ```

3. **如果有问题，导出列表**:
   ```bash
   jq -r '.problem_episodes[].episode_path' yinhe_frame_check_results_full.json > problem_episodes.txt
   ```

4. **修复问题后重新扫描验证**:
   ```bash
   python check_yinhe_frame_mismatch_full.py
   # 应该看到 episodes_with_problems 减少
   ```

### 📧 反馈

如果你需要其他格式或功能，欢迎提出需求！
