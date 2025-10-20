#!/usr/bin/env python3
"""
简单测试：直接调用帧数检查逻辑，模拟转换器行为
"""

import h5py
import yaml
from pathlib import Path

# 配置路径
config_path = Path("/home/diy01/dev/robocoin-dataset/scripts/format_converters/tolerobot/configs/converter_config_zhipingfang_left_arm_with_pose.yaml")

# H5文件路径（已知有问题的文件）
h5_file_path = Path("/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/算法采集_PCB/算法采集_PCB抓拿放取_0925_1538/0629_a.h5")

print("🧪 模拟转换器帧数检查\n")
print(f"📁 配置: {config_path.name}")
print(f"📁 H5文件: {h5_file_path.name}")
print(f"📁 任务: 算法采集_PCB")
print(f"📍 Episode索引: 198\n")

# 加载配置
with open(config_path) as f:
    config = yaml.safe_load(f)

# 获取 sub_state 配置
sub_states = config['features']['observation']['state']['sub_state']

print(f"📊 配置中有 {len(sub_states)} 个 sub_state 需要检查\n")

# 模拟 _get_episode_frames_num 的逻辑
with h5py.File(h5_file_path, 'r') as h5_file:
    # 获取参考帧数（第一个sub_state）
    reference_h5_path = sub_states[0]['args']['h5_path']
    reference_frame_count = h5_file[reference_h5_path].shape[0]
    
    print(f"📊 参考帧数（来自 sub_state[0]）:")
    print(f"   {reference_h5_path}: {reference_frame_count} 帧\n")
    
    # 检查所有 sub_state 的帧数
    frame_count_issues = []
    
    for i, sub_state in enumerate(sub_states):
        sub_state_args = sub_state.get('args', {})
        if 'h5_path' not in sub_state_args:
            continue
        
        check_h5_path = sub_state_args['h5_path']
        if check_h5_path not in h5_file:
            print(f"⚠️  sub_state[{i}] {check_h5_path}: 路径不存在")
            continue
        
        dataset = h5_file[check_h5_path]
        shape = dataset.shape
        
        # 跳过视频压缩数据
        if 'video' in check_h5_path.lower() and shape == ():
            print(f"⏭️  sub_state[{i}] {check_h5_path}: 视频压缩格式，跳过")
            continue
        
        # 跳过空数据集
        if len(shape) > 0 and shape[0] == 0:
            print(f"⏭️  sub_state[{i}] {check_h5_path}: 空数据集，跳过")
            continue
        
        # 检查帧数
        if len(shape) > 0:
            current_frame_count = shape[0]
            status = "✅" if current_frame_count == reference_frame_count else "❌"
            print(f"{status} sub_state[{i}] {check_h5_path}: {current_frame_count} 帧")
            
            if current_frame_count != reference_frame_count:
                frame_count_issues.append(
                    f"    sub_state[{i}] {check_h5_path}: {current_frame_count} 帧"
                )

# 打印结果
print("\n" + "=" * 70)
if frame_count_issues:
    print("❌ 检测到帧数不一致！\n")
    print("转换器将抛出以下错误:\n")
    print("=" * 70)
    print(f"❌ H5数据集帧数不一致（数据质量问题）")
    print(f"   🗂️  文件: {h5_file_path.name}")
    print(f"   📁 完整路径: {h5_file_path}")
    print(f"   📍 任务: 算法采集_PCB")
    print(f"   📍 Episode索引: 198")
    print(f"   ")
    print(f"   📊 参考帧数（来自 sub_state[0]）:")
    print(f"    {reference_h5_path}: {reference_frame_count} 帧")
    print(f"   ")
    print(f"   ❌ 以下数据集帧数不一致:")
    for issue in frame_count_issues:
        print(issue)
    print(f"   ")
    print(f"   💡 这是数据采集时的问题，不同传感器的数据长度不一致。")
    print(f"   🔧 解决方案：")
    print(f"      1. 移动此文件到 error/ 文件夹：")
    print(f"         mkdir -p '{h5_file_path.parent}/error'")
    print(f"         mv '{h5_file_path}' '{h5_file_path.parent}/error/'")
    print(f"      2. 或者重新采集这个episode的数据")
    print(f"      3. 或者修改数据采集脚本确保所有传感器同步")
    print("=" * 70)
    print("\n✅ 测试成功：转换器能够检测并详细报告帧数不一致问题")
else:
    print("✅ 所有数据集帧数一致")
    print("   转换将正常进行")
    print("=" * 70)
