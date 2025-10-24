# 数据集转换测试命令完整清单

**更新日期**: 2025-10-24  
**本地数据集总数**: 21个  
**已成功转换**: 3个 (ruantong系列)

---

## 📋 目录

1. [快速开始](#快速开始)
2. [单个数据集转换命令](#单个数据集转换命令)
3. [批量转换命令](#批量转换命令)
4. [转换后检查命令](#转换后检查命令)
5. [常见问题处理](#常见问题处理)

---

## 🚀 快速开始

### ⚠️ 重要说明：容错机制

**2025-10-24 更新**：已实现完整的初始化阶段容错机制！

- ✅ **修复前问题**：如果第一个episode损坏，整个converter无法初始化
- ✅ **修复后**：会尝试多个episode（最多前5个），找到第一个可用的即可成功初始化
- 💡 **效果**：即使部分episode有问题，也能成功转换其他正常的episode

### 前提条件

```bash
cd /home/liu/program/robocoin-dataset
export PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH
```

### 最简单的测试命令

```bash
# 测试已验证的数据集（最稳定，推荐首选）
PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/ruantong_a2d:default_version \
    --output_path outputs/ruantong_default_full \
    --device_model ruantong_a2d \
    --device_model_version default_version \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/ruantong_default
```

---

## 📦 单个数据集转换命令

### 按数据格式分类

#### 1️⃣ H5+JPG 格式（软通机器人）

**特点**: H5文件存储关节数据，JPG图像按帧存储  
**容错机制**: ✅ 已实现（必需相机检查 + 上一帧复制）

##### 1.1 ruantong_a2d:default_version ✅ (已验证)

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/ruantong_a2d:default_version \
    --output_path outputs/ruantong_default_full \
    --device_model ruantong_a2d \
    --device_model_version default_version \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/ruantong_default \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

**预期结果**:
- Episodes: ~1-5个
- 包含8个相机（3必需 + 5可选）
- 转换时间: 5-15分钟/episode

##### 1.2 ruantong_a2d:gt02_new_version ✅ (已成功)

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/ruantong_a2d:gt02_new_version \
    --output_path outputs/ruantong_gt02_full \
    --device_model ruantong_a2d \
    --device_model_version gt02_new_version \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/ruantong_gt02 \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

**已验证结果**: 1 episode, 615帧, 100%成功

##### 1.3 ruantong_a2d:gt01_no_depth ✅ (配置已修复)

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/ruantong_a2d:gt01_no_depth \
    --output_path outputs/ruantong_gt01_full \
    --device_model ruantong_a2d \
    --device_model_version gt01_no_depth \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/ruantong_gt01 \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

---

#### 2️⃣ JPG+JSON 格式（志平方双臂机器人）

**特点**: JSON存储动作/状态，JPG按帧存储图像  
**Episode定位**: ✅ 已修复（支持扁平和嵌套结构）

##### 2.1 zhipingfang:dual_arm_no_pose

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/zhipingfang:dual_arm_no_pose \
    --output_path outputs/zhipingfang_dual_arm_no_pose_full \
    --device_model zhipingfang \
    --device_model_version dual_arm_no_pose \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/zhipingfang_dual_arm_no_pose \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

##### 2.2 zhipingfang:dual_arm_with_pose

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/zhipingfang:dual_arm_with_pose \
    --output_path outputs/zhipingfang_dual_arm_with_pose_full \
    --device_model zhipingfang \
    --device_model_version dual_arm_with_pose \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/zhipingfang_dual_arm_with_pose \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

##### 2.3 zhipingfang:dual_arm_no_pose_compressed_video

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/zhipingfang:dual_arm_no_pose_compressed_video \
    --output_path outputs/zhipingfang_dual_arm_no_pose_compressed_full \
    --device_model zhipingfang \
    --device_model_version dual_arm_no_pose_compressed_video \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/zhipingfang_dual_arm_no_pose_compressed \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

##### 2.4 zhipingfang:dual_arm_with_pose_compressed_video

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/zhipingfang:dual_arm_with_pose_compressed_video \
    --output_path outputs/zhipingfang_dual_arm_with_pose_compressed_full \
    --device_model zhipingfang \
    --device_model_version dual_arm_with_pose_compressed_video \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/zhipingfang_dual_arm_with_pose_compressed \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

##### 2.5 zhipingfang:dual_arm_with_pose_no_left_chest_cam

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/zhipingfang:dual_arm_with_pose_no_left_chest_cam \
    --output_path outputs/zhipingfang_dual_arm_no_left_chest_full \
    --device_model zhipingfang \
    --device_model_version dual_arm_with_pose_no_left_chest_cam \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/zhipingfang_dual_arm_no_left_chest \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

##### 2.6 zhipingfang:left_arm_with_pose

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/zhipingfang:left_arm_with_pose \
    --output_path outputs/zhipingfang_left_arm_full \
    --device_model zhipingfang \
    --device_model_version left_arm_with_pose \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/zhipingfang_left_arm \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

##### 2.7 zhipingfang:right_arm_with_pose

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/zhipingfang:right_arm_with_pose \
    --output_path outputs/zhipingfang_right_arm_full \
    --device_model zhipingfang \
    --device_model_version right_arm_with_pose \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/zhipingfang_right_arm \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

##### 2.8 agilex_cobot_decoupled_magic:mult_sensor

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/agilex_cobot_decoupled_magic:mult_sensor \
    --output_path outputs/agilex_mult_sensor_full \
    --device_model agilex_cobot_decoupled_magic \
    --device_model_version mult_sensor \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/agilex_mult_sensor \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

---

#### 3️⃣ H5 格式（纯H5文件）

**特点**: 所有数据（图像+动作+状态）都在H5文件中  
**Episode定位**: ✅ 已修复（递归搜索 + 目录过滤）

##### 3.1 agilex_cobot_decoupled_magic:masterpuppet_version

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/agilex_cobot_decoupled_magic:masterpuppet_version \
    --output_path outputs/agilex_masterpuppet_full \
    --device_model agilex_cobot_decoupled_magic \
    --device_model_version masterpuppet_version \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/agilex_masterpuppet \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

##### 3.2 galaxea_r1_lite:default_version

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/galaxea_r1_lite:default_version \
    --output_path outputs/galaxea_default_full \
    --device_model galaxea_r1_lite \
    --device_model_version default_version \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/galaxea_default \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

---

#### 4️⃣ H5+MP4 格式

**特点**: H5存储动作/状态，MP4存储视频  
**LazyVideoReader**: ✅ 已修复（`num_frames`属性）

##### 4.1 agilex_cobot_decoupled_magic:h5_mp4

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/agilex_cobot_decoupled_magic:h5_mp4 \
    --output_path outputs/agilex_h5_mp4_full \
    --device_model agilex_cobot_decoupled_magic \
    --device_model_version h5_mp4 \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/agilex_h5_mp4 \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

##### 4.2 agilex_cobot_decoupled_magic:h5_mp4_new

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/agilex_cobot_decoupled_magic:h5_mp4_new \
    --output_path outputs/agilex_h5_mp4_new_full \
    --device_model agilex_cobot_decoupled_magic \
    --device_model_version h5_mp4_new \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/agilex_h5_mp4_new \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

##### 4.3 galaxea_r1_lite:h5_mp4_version ⚠️ (AV1编解码器不兼容)

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/galaxea_r1_lite:h5_mp4_version \
    --output_path outputs/galaxea_h5_mp4_full \
    --device_model galaxea_r1_lite \
    --device_model_version h5_mp4_version \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/galaxea_h5_mp4 \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

**⚠️ 已知问题**: 
- **问题**: 视频使用AV1编码，平台不支持硬件加速解码
- **现象**: PyAV能识别视频（2226帧），但无法解码（Missing Sequence Header）
- **解决方案**: 
  1. 重新编码视频为H.264/H.265格式
  2. 或在生产环境重新生成此数据集
  3. 或安装支持AV1的软解码器
- **注意**: 容错机制会尝试初始化，但因只有1个episode且无法解码，最终会正确报错

---

#### 5️⃣ MCAP 格式（ROS2 数据格式）

**特点**: MCAP是ROS2的新格式，高性能  
**Episode定位**: ✅ 已修复（统一glob/rglob + 目录过滤）

##### 5.1 realman_rmc_aidal:mcap_version

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/realman_rmc_aidal:mcap_version \
    --output_path outputs/realman_mcap_full \
    --device_model realman_rmc_aidal \
    --device_model_version mcap_version \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/realman_mcap \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

---

#### 6️⃣ ROS Bag 格式（ROS1 数据格式）

**特点**: ROS1的标准bag格式  

##### 6.1 realman_rmc_aidal:default_version

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/realman_rmc_aidal:default_version \
    --output_path outputs/realman_default_full \
    --device_model realman_rmc_aidal \
    --device_model_version default_version \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/realman_default \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

---

#### 7️⃣ MP4+JSON 格式

**特点**: MP4视频 + JSON元数据  
**FFprobe依赖**: ⚠️ 需要安装ffmpeg

##### 7.1 yinhe:default_version ⚠️ (帧数不匹配)

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/yinhe:default_version \
    --output_path outputs/yinhe_default_full \
    --device_model yinhe \
    --device_model_version default_version \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/yinhe_default \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

**⚠️ 注意**: 此数据集已知视频与JSON帧数不匹配，可能转换失败

---

#### 8️⃣ MMK2 格式

**特点**: discover_robotics专用格式  
**Episode定位**: ✅ 已修复（支持扁平结构）

##### 8.1 discover_robotics_aitbot_mmk2:third_view

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/discover_robotics_aitbot_mmk2:third_view \
    --output_path outputs/mmk2_third_view_full \
    --device_model discover_robotics_aitbot_mmk2 \
    --device_model_version third_view \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/mmk2_third_view \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

---

#### 9️⃣ Leju Waibu 格式

**特点**: 乐聚机器人专用格式  
**Episode定位**: ✅ 已修复（支持扁平subtask结构）

##### 9.1 leju_robot:waibu_version

```bash
cd /home/liu/program/robocoin-dataset

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --dataset_path data/leju_robot:waibu_version \
    --output_path outputs/leju_waibu_full \
    --device_model leju_robot \
    --device_model_version waibu_version \
    --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
    --repo_id test/leju_waibu \
    --log_dir outputs/conversion_logs \
    --image_writer_processes 4 \
    --image_writer_threads 4 \
    --video_backend pyav
```

---

## 🔄 批量转换命令

### 方案A: 自动批量转换所有数据集

```bash
cd /home/liu/program/robocoin-dataset

# 一键转换所有数据集（按优先级顺序）
bash scripts/batch_convert_local_datasets.sh
```

**特点**:
- ✅ 自动跳过已存在的输出目录
- ✅ 按优先级顺序（high → medium → low）
- ✅ 详细日志记录
- ✅ 自动生成汇总报告
- ⏱️ 预计耗时: 几小时到一天（取决于数据集大小）

**日志位置**:
- 批量日志: `outputs/batch_conversion_logs/batch_conversion_YYYYMMDD_HHMMSS.log`
- 单个转换日志: `outputs/batch_conversion_logs/convert_DEVICE_VERSION_YYYYMMDD_HHMMSS.log`
- 汇总报告: `outputs/batch_conversion_summary_YYYYMMDD_HHMMSS.txt`

### 方案B: 后台运行批量转换

```bash
cd /home/liu/program/robocoin-dataset

# 后台运行，并将输出重定向到日志
nohup bash scripts/batch_convert_local_datasets.sh > outputs/batch_conversion_nohup.log 2>&1 &

# 查看进程
ps aux | grep batch_convert

# 查看实时日志
tail -f outputs/batch_conversion_nohup.log
```

### 方案C: 选择性批量转换

编辑批量脚本，注释掉不想转换的数据集：

```bash
vim scripts/batch_convert_local_datasets.sh

# 找到DATASETS数组，注释掉不需要的数据集
# 例如:
# "yinhe:default_version|MP4+JSON|skip"  # 跳过此数据集
```

---

## 🔍 转换后检查命令

### 基本检查

```bash
cd /home/liu/program/robocoin-dataset

# 1. 列出所有转换结果
ls -lh outputs/converted_*/
ls -lh outputs/*_full/

# 2. 统计成功转换的数据集数量
ls -d outputs/converted_*/ outputs/*_full/ 2>/dev/null | wc -l

# 3. 检查每个数据集的输出结构
for dir in outputs/converted_*/ outputs/*_full/; do
    echo "=== $(basename $dir) ==="
    ls -lh "$dir"
    echo ""
done
```

### 检查Mapping文件

```bash
cd /home/liu/program/robocoin-dataset

# 1. 查看episode_source_mapping.json的摘要信息
for dir in outputs/converted_*/ outputs/*_full/; do
    if [ -f "$dir/episode_source_mapping.json" ]; then
        echo "=== $(basename $dir) ==="
        cat "$dir/episode_source_mapping.json" | jq '.dataset_info'
        echo ""
    fi
done

# 2. 查看original_data_paths.json
for dir in outputs/converted_*/ outputs/*_full/; do
    if [ -f "$dir/original_data_paths.json" ]; then
        echo "=== $(basename $dir) ==="
        cat "$dir/original_data_paths.json" | jq '.dataset_info'
        echo ""
    fi
done

# 3. 检查是否有跳过的episodes
for dir in outputs/converted_*/ outputs/*_full/; do
    if [ -f "$dir/episode_source_mapping.json" ]; then
        skipped=$(cat "$dir/episode_source_mapping.json" | jq '.dataset_info.total_skipped_episodes')
        if [ "$skipped" != "0" ]; then
            echo "⚠️  $(basename $dir) 有 $skipped 个跳过的episodes"
            cat "$dir/episode_source_mapping.json" | jq '.skipped_episodes'
        fi
    fi
done
```

### 详细检查单个数据集

```bash
# 替换 DATASET_NAME 为实际的输出目录名
DATASET_NAME="ruantong_default_full"

cd /home/liu/program/robocoin-dataset/outputs/$DATASET_NAME

echo "📊 数据集: $DATASET_NAME"
echo ""

# 1. 目录结构
echo "=== 目录结构 ==="
ls -lh
echo ""

# 2. Episode统计
echo "=== Episode统计 ==="
cat episode_source_mapping.json | jq '{
    total_original: .dataset_info.total_original_episodes,
    total_converted: .dataset_info.total_converted_episodes,
    total_skipped: .dataset_info.total_skipped_episodes
}'
echo ""

# 3. 转换的episodes详情
echo "=== 转换的Episodes ==="
cat episode_source_mapping.json | jq '.converted_episodes[] | {
    original_idx: .original_episode_index,
    global_idx: .global_episode_index,
    task: .task,
    converted_frames: .converted_frames,
    skipped_frames: .skipped_frames
}'
echo ""

# 4. 跳过的episodes（如果有）
echo "=== 跳过的Episodes ==="
cat episode_source_mapping.json | jq '.skipped_episodes'
echo ""

# 5. 绝对路径映射
echo "=== 绝对路径映射 ==="
cat original_data_paths.json | jq '.episode_paths[0]'
echo ""

# 6. 视频文件统计
echo "=== 视频文件 ==="
find videos/ -name "*.mp4" | wc -l
echo "个视频文件"
echo ""

# 7. Parquet数据文件
echo "=== Parquet数据文件 ==="
ls -lh data/chunk-*/
```

### 验证数据完整性

```bash
cd /home/liu/program/robocoin-dataset

# 检查所有数据集的完整性
for dir in outputs/converted_*/ outputs/*_full/; do
    if [ -d "$dir" ]; then
        echo "=== $(basename $dir) ==="
        
        # 检查必需文件
        if [ -f "$dir/episode_source_mapping.json" ]; then
            echo "✅ episode_source_mapping.json"
        else
            echo "❌ episode_source_mapping.json 缺失"
        fi
        
        if [ -f "$dir/original_data_paths.json" ]; then
            echo "✅ original_data_paths.json"
        else
            echo "❌ original_data_paths.json 缺失"
        fi
        
        if [ -d "$dir/videos" ]; then
            video_count=$(find "$dir/videos" -name "*.mp4" 2>/dev/null | wc -l)
            echo "✅ videos/ ($video_count 个视频)"
        else
            echo "⚠️  videos/ 目录不存在"
        fi
        
        if [ -d "$dir/data" ]; then
            echo "✅ data/ (Parquet数据)"
        else
            echo "❌ data/ 目录缺失"
        fi
        
        echo ""
    fi
done
```

---

## 🛠️ 常见问题处理

### 问题1: 输出目录已存在

**错误信息**: `FileExistsError: [Errno 17] File exists`

**解决方法**:
```bash
# 删除旧的输出目录
rm -rf outputs/DATASET_NAME_full

# 或者使用新的输出目录名
--output_path outputs/DATASET_NAME_full_v2
```

### 问题2: 模块导入错误

**错误信息**: `ModuleNotFoundError: No module named 'robocoin_dataset'`

**解决方法**:
```bash
# 确保设置了PYTHONPATH
export PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH

# 或在命令前添加
PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH python ...
```

### 问题3: ffprobe未找到

**错误信息**: `FileNotFoundError: [Errno 2] No such file or directory: 'ffprobe'`

**解决方法**:
```bash
# 安装ffmpeg（包含ffprobe）
sudo apt-get update
sudo apt-get install ffmpeg

# 验证安装
ffprobe -version
```

### 问题4: 视频编码时间过长

**现象**: 转换一个episode需要很长时间（>30分钟）

**说明**: 这是正常的，特别是对于：
- 高分辨率相机（1920x1536鱼眼）
- 多个相机（8个相机同时编码）
- 长时间录制（>1000帧）

**优化建议**:
```bash
# 减少并发进程（降低内存占用，但可能更慢）
--image_writer_processes 2 \
--image_writer_threads 2

# 使用更快的视频编码器（如果可用）
--video_backend opencv  # 或 imageio
```

### 问题5: 内存不足

**错误信息**: `MemoryError` 或系统变慢

**解决方法**:
```bash
# 1. 减少并发数
--image_writer_processes 2 \
--image_writer_threads 2

# 2. 限制并发转换的数据集数量
# 编辑批量脚本，一次只转换2-3个数据集

# 3. 监控内存使用
watch -n 1 free -h
```

### 问题6: 检查转换日志

**查看详细日志**:
```bash
# 查看最新的转换日志
ls -lt outputs/conversion_logs/LEROBOT_CONVERTER_*.log | head -1 | xargs cat

# 查看批量转换日志
cat outputs/batch_conversion_logs/batch_conversion_*.log

# 查看特定数据集的转换日志
cat outputs/batch_conversion_logs/convert_DEVICE_VERSION_*.log
```

---

## 📈 转换进度追踪

### 创建转换追踪表

```bash
cd /home/liu/program/robocoin-dataset

cat > outputs/conversion_progress.txt << 'EOF'
数据集转换进度追踪
==================

格式: [状态] 数据集名称 | 格式 | 备注

✅ = 成功
🔄 = 进行中
⏸️ = 暂停
❌ = 失败
⏭️ = 跳过

H5+JPG格式:
✅ ruantong_a2d:default_version      | H5+JPG | 已验证
✅ ruantong_a2d:gt02_new_version     | H5+JPG | 615帧，100%成功
✅ ruantong_a2d:gt01_no_depth        | H5+JPG | 配置已修复

JPG+JSON格式:
⬜ zhipingfang:dual_arm_no_pose      | JPG+JSON |
⬜ zhipingfang:dual_arm_with_pose    | JPG+JSON |
⬜ agilex_cobot_decoupled_magic:mult_sensor | JPG+JSON |

H5格式:
⬜ agilex_cobot_decoupled_magic:masterpuppet_version | H5 |
⬜ galaxea_r1_lite:default_version   | H5 |

H5+MP4格式:
⬜ agilex_cobot_decoupled_magic:h5_mp4 | H5+MP4 |
⬜ agilex_cobot_decoupled_magic:h5_mp4_new | H5+MP4 |
⚠️ galaxea_r1_lite:h5_mp4_version   | H5+MP4 | AV1编解码器不兼容

MCAP格式:
⬜ realman_rmc_aidal:mcap_version    | MCAP |

ROS Bag格式:
⬜ realman_rmc_aidal:default_version | ROSBAG |

MP4+JSON格式:
⚠️ yinhe:default_version            | MP4+JSON | 帧数不匹配

MMK2格式:
⬜ discover_robotics_aitbot_mmk2:third_view | MMK2 |

Leju Waibu格式:
⬜ leju_robot:waibu_version          | LEJU_WAIBU |

其他志平方版本:
⬜ zhipingfang:dual_arm_no_pose_compressed_video | JPG+JSON |
⬜ zhipingfang:dual_arm_with_pose_compressed_video | JPG+JSON |
⬜ zhipingfang:dual_arm_with_pose_no_left_chest_cam | JPG+JSON |
⬜ zhipingfang:left_arm_with_pose    | JPG+JSON |
⬜ zhipingfang:right_arm_with_pose   | JPG+JSON |

EOF

cat outputs/conversion_progress.txt
```

---

## 🎯 推荐转换顺序

按优先级和风险从高到低排序：

### 第一批（高优先级，已验证）
1. ✅ ruantong_a2d:default_version - 已成功
2. ✅ ruantong_a2d:gt02_new_version - 已成功
3. ✅ ruantong_a2d:gt01_no_depth - 已成功

### 第二批（高优先级，配置已验证）
4. zhipingfang:dual_arm_no_pose
5. zhipingfang:dual_arm_with_pose
6. agilex_cobot_decoupled_magic:mult_sensor
7. agilex_cobot_decoupled_magic:masterpuppet_version

### 第三批（中等优先级）
8. realman_rmc_aidal:mcap_version
9. realman_rmc_aidal:default_version
10. leju_robot:waibu_version
11. discover_robotics_aitbot_mmk2:third_view

### 第四批（低优先级）
12-18. 其他志平方版本
19-20. agilex H5+MP4版本
21. galaxea_r1_lite:default_version

### 第五批（已知问题，最后尝试）
22. yinhe:default_version (帧数不匹配)
23. galaxea_r1_lite:h5_mp4_version (AV1编解码器不兼容，需重新编码)

---

## 📞 获取帮助

如果遇到任何问题：

1. **查看日志**: `outputs/conversion_logs/`
2. **检查mapping文件**: 查看是否有跳过的episodes
3. **报告错误**: 将完整的错误信息和日志提供给开发团队

---

**文档版本**: v1.0  
**最后更新**: 2025-10-24  
**维护者**: robocoin-dataset team

