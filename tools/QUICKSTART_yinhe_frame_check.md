# 银河数据集帧数检查工具 - 快速指南

## ✨ 核心功能

这个工具会**模拟转换器的验证逻辑**，提前发现会导致转换失败的问题：

1. ✅ **读取配置文件**：只检查配置中实际使用的 JSON 字段
2. ✅ **模拟转换器策略**：计算最小帧数（所有数据源的最小值）
3. ✅ **模拟 _prevalidate_files**：验证视频帧数与预期是否匹配
4. ✅ **区分严重问题和警告**：
   - ❌ 严重问题：会导致转换失败（如最小帧数为 0）
   - ⚠️  警告：可以转换但有风险（如帧数差异大）

## 📦 已创建的文件

1. **check_yinhe_frame_mismatch.py** - 测试版（支持 --test 和 --full 模式）
2. **check_yinhe_frame_mismatch_full.py** - 完整版（仅支持完整扫描）
3. **README_yinhe_frame_check.md** - 详细文档
4. **QUICKSTART_yinhe_frame_check.md** - 本快速指南

## 🚀 快速开始

### 本地测试（推荐先运行）

```bash
cd /home/diy01/dev/robocoin-dataset

# 测试第一个任务（fold_clothe，约3978个episodes）
python tools/check_yinhe_frame_mismatch.py --test

# 输出文件：yinhe_frame_check_results.json
```

### 其他机器完整扫描

```bash
# 方式1：使用测试版的 --full 模式
python tools/check_yinhe_frame_mismatch.py --full

# 方式2：使用专门的完整版
python tools/check_yinhe_frame_mismatch_full.py

# 输出文件：yinhe_frame_check_results_full.json
```

## 📊 测试结果示例

根据测试 fold_clothe 任务的前 100 个 episodes：

### ✅ 好消息
- **100% 可以转换**（0 个严重问题）
- 最小帧数范围：717-1301 帧
- 平均最小帧数：966.8 帧

### ⚠️  警告（不影响转换）
- **100% 有警告**（但都可以安全转换）
- 警告类型：
  1. `unused_fields_zero`: 未使用字段为 0 帧（cmd_body_joint, cmd_head_joint_state）
  2. `large_frame_difference`: 帧数差异大（~738%）

### 📊 数据特征
- 视频帧数：~700-1300 帧（30fps，约 23-43 秒）
- JSON 各字段帧数差异巨大：
  - **使用的字段**（会影响转换）：
    - camera 字段：~700-1300（与视频一致，是瓶颈）
    - state 字段：6000-11000 条
    - cmd 字段：2000-4000 条
    - gripper 字段：1000-1700 条
  - **未使用的字段**（不影响转换）：
    - cmd_body_joint: 0
    - cmd_head_joint_state: 0
    - odom: 1300-2100 条

## 🔍 典型案例分析

### 例子：Episode 20250914_124415_record0

#### 原始数据
```
JSON 字段帧数（全部）：
  - state_front_head_joint: 6628          [使用]
  - state_body_joint_position: 6627       [使用]
  - state_left_arm_joint_position: 6581   [使用]
  - state_left_arm_gripper_width: 1051    [使用]
  - state_right_arm_joint_position: 6581  [使用]
  - state_right_arm_gripper_width: 1050   [使用]
  - camera_front_head_rgb (JSON): 791     [使用] ← 瓶颈
  - camera_left_wrist (JSON): 791         [使用] ← 瓶颈
  - camera_right_wrist (JSON): 791        [使用] ← 瓶颈
  - cmd_left_joint_state: 2651            [使用]
  - cmd_right_joint_state: 2651           [使用]
  - cmd_body_joint: 0                     [未使用]
  - cmd_head_joint_state: 0               [未使用]
  - cmd_action_list: 2632                 [未使用]
  - odom: 1316                            [未使用]

视频实际帧数：
  - camera_front_head_rgb.mp4: 791
  - camera_left_wrist.mp4: 791
  - camera_right_wrist.mp4: 791
```

#### 转换器处理策略
```
配置中使用的字段：11 个
└─ 最小帧数：791（来自 camera 字段和视频）

转换结果：
✅ 生成 791 帧数据
✅ 所有字段都会被截断或采样到 791 帧
✅ 未使用的字段（cmd_body_joint=0）不影响结果
```

#### 关键发现
1. ✅ **视频是瓶颈**：30fps × 26.4秒 = 791 帧
2. ✅ **State 数据采样率更高**：~250Hz（6628条 / 26.4秒）
3. ✅ **转换器会处理好**：自动将高频数据降采样到 791 帧
4. ⚠️  **未使用字段为 0**：不是问题，因为配置没用到它们

## 💡 使用建议

1. **运行顺序**：
   ```bash
   # 1. 先在开发机器上测试（快速验证）
   python tools/check_yinhe_frame_mismatch.py --test
   
   # 2. 如果测试正常，再在生产机器上完整扫描
   python tools/check_yinhe_frame_mismatch_full.py
   ```

2. **理解输出**：
   - ❌ **严重问题**：必须修复，否则转换会失败
   - ⚠️  **警告**：可以转换，但建议了解原因
   - ✅ **正常**：可以安全转换

3. **常见警告的含义**：
   - `unused_fields_zero`: **可忽略**（配置不使用这些字段）
   - `large_frame_difference`: **正常**（不同传感器采样率不同）
   - `video_frame_mismatch`: **预期内**（转换器会截断）

4. **何时需要关注**：
   - ❌ 最小帧数为 0
   - ❌ 视频文件缺失或损坏
   - ❌ JSON 文件格式错误
   - ⚠️  最小帧数异常少（<10 帧）

5. **性能预期**：
   - 测试模式（100个episodes）：~2-5 分钟
   - 完整扫描（3000+episodes）：~30-60 分钟

## 📋 脚本功能对比

| 功能 | 测试版 | 完整版 |
|------|--------|--------|
| 支持 --test 模式 | ✅ | ❌ |
| 支持 --full 模式 | ✅ | ✅（默认） |
| 代码逻辑 | 完全相同 | 完全相同 |
| 输出文件 | yinhe_frame_check_results.json | yinhe_frame_check_results_full.json |
| 推荐场景 | 本地开发测试 | 生产环境批量运行 |

## 🛠️ 依赖检查

确保目标机器上安装了 ffprobe：
```bash
ffprobe -version
```

如果没有：
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# CentOS/RHEL
sudo yum install ffmpeg
```
