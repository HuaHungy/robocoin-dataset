# 银河数据集帧数一致性检查工具

## 概述

这些工具用于检查银河通用数据集中 JSON 数据和 MP4 视频的帧数是否一致。

## 文件说明

### 1. `check_yinhe_frame_mismatch.py` - 测试版

用于快速测试脚本功能，只检查第一个任务。

**用法：**
```bash
# 测试模式（只检查第一个任务）
python tools/check_yinhe_frame_mismatch.py --test

# 完整模式（检查所有任务，与完整版功能相同）
python tools/check_yinhe_frame_mismatch.py --full

# 自定义数据集路径
python tools/check_yinhe_frame_mismatch.py --test --base-path /path/to/dataset
```

### 2. `check_yinhe_frame_mismatch_full.py` - 完整版

用于生产环境的批量检查，扫描所有任务和 episodes。

**用法：**
```bash
# 默认路径检查
python tools/check_yinhe_frame_mismatch_full.py

# 自定义路径和输出文件
python tools/check_yinhe_frame_mismatch_full.py \
    --base-path /mnt/nas/synnas/docker/外部数据/银河通用 \
    --output my_results.json
```

## 检查内容

对每个 episode，脚本会：

1. **读取 data.json**：获取所有字段的数据长度
   - `state_body_joint_position`
   - `state_front_head_joint`
   - `state_left_arm_joint_position`
   - `state_left_arm_gripper_width`
   - `state_right_arm_joint_position`
   - `state_right_arm_gripper_width`
   - `cmd_*` 系列
   - `camera_*` 系列
   - `odom`

2. **检测视频帧数**：使用 ffprobe 读取所有 MP4 文件的实际帧数
   - `camera_front_head_rgb.mp4`
   - `camera_left_wrist.mp4`
   - `camera_right_wrist.mp4`

3. **比较一致性**：
   - JSON 内部各字段是否一致
   - 视频之间是否一致
   - JSON 和视频之间是否匹配

## 输出格式

### 控制台输出

实时显示：
```
🔍 开始检查银河数据集: /mnt/nas/synnas/docker/外部数据/银河通用
📦 模式: 测试模式 (1个任务)
📂 找到 3978 个 episodes

[1/3978] ❌ /path/to/episode
     JSON fields have different frame counts: {...}
     
[2/3978] ✅ 正常

================================================================================
📊 汇总统计
================================================================================
总 Episode 数: 3978
有帧数不一致问题: 3978 (100.0%)

问题类型分布:
  - json_internal_mismatch: 3978
  - json_video_mismatch: 2145
```

### JSON 输出文件

详细的结构化数据：
```json
[
  {
    "episode_path": "/path/to/episode",
    "has_mismatch": true,
    "json_frames": {
      "state_body_joint_position": 6627,
      "camera_front_head_rgb": 791,
      "camera_left_wrist": 791,
      "camera_right_wrist": 791
    },
    "video_frames": {
      "camera_front_head_rgb.mp4": 791,
      "camera_left_wrist.mp4": 791,
      "camera_right_wrist.mp4": 791
    },
    "mismatches": [
      {
        "type": "json_internal_mismatch",
        "details": "JSON fields have different frame counts: {...}"
      },
      {
        "type": "json_video_mismatch",
        "details": "JSON frames: 6627, Video frames: 791, Diff: 5836"
      }
    ]
  }
]
```

## 问题类型说明

- **json_internal_mismatch**: JSON 内部不同字段的帧数不一致
- **video_internal_mismatch**: 不同视频文件的帧数不一致  
- **json_video_mismatch**: JSON 数据帧数与视频帧数不匹配

## 依赖

- Python 3.7+
- ffprobe (来自 ffmpeg 套件)

安装 ffmpeg：
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# CentOS/RHEL
sudo yum install ffmpeg

# macOS
brew install ffmpeg
```

## 性能估算

- **测试模式**：约 1-5 分钟（1 个任务，几千个 episodes）
- **完整模式**：约 10-60 分钟（取决于数据集大小和磁盘速度）

建议先在本地运行测试模式验证脚本功能，然后在服务器上运行完整版。

## 注意事项

1. 脚本会自动跳过以下目录：
   - 隐藏目录（`.` 开头）
   - 系统目录（`@` 开头）
   - `System Volume Information`
   - `error` 目录

2. 支持两种数据集结构：
   - 三层：`task/batch/episode`
   - 四层：`task/subtask/batch/episode`

3. ffprobe 超时设置为 10 秒，对于超大视频文件可能需要调整

## 示例工作流

```bash
# 1. 在开发机器上测试
cd /home/diy01/dev/robocoin-dataset
python tools/check_yinhe_frame_mismatch.py --test

# 2. 将脚本复制到生产服务器
scp tools/check_yinhe_frame_mismatch_full.py user@server:/path/to/

# 3. 在生产服务器上运行完整检查
ssh user@server
cd /path/to/
python check_yinhe_frame_mismatch_full.py

# 4. 下载结果分析
scp user@server:/path/to/yinhe_frame_check_results_full.json ./
```

## 故障排查

**问题：未找到任何 episode**
- 检查数据集路径是否正确
- 确认 data.json 文件存在
- 查看控制台输出的扫描任务列表

**问题：ffprobe 错误**
- 确认 ffmpeg 已安装：`ffprobe -version`
- 检查视频文件权限
- 尝试手动运行 ffprobe 命令

**问题：处理速度慢**
- 正常现象，视频帧数检测需要时间
- 可以增加进度显示频率（修改代码中的 `i % 100`）
- 考虑并行处理（需修改代码使用多进程）
