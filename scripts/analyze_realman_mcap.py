#!/usr/bin/env python3
"""Realman RMC Aidal MCAP数据深度分析脚本"""

import numpy as np
from pathlib import Path
from mcap.reader import make_reader
from rosbags.typesys import Stores, get_typestore, get_types_from_msg

def analyze_mcap_file(mcap_path: Path):
    """分析MCAP文件内容"""
    
    # 初始化typestore
    typestore = get_typestore(Stores.ROS2_FOXY)
    
    # 注册自定义消息类型
    msg_definitions = {
        'rm_ros_interfaces/msg/Jointposeorientation': """
std_msgs/Header header
geometry_msgs/Pose pose
""",
    }
    
    for msg_name, msg_text in msg_definitions.items():
        try:
            msg_types = get_types_from_msg(msg_text, msg_name)
            typestore.register(msg_types)
        except:
            pass
    
    print(f"📊 分析MCAP文件: {mcap_path.name}")
    print("=" * 80)
    
    # 统计信息
    topic_stats = {}
    
    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        
        # 获取摘要信息
        summary = reader.get_summary()
        if summary:
            print(f"\n📈 文件摘要:")
            if summary.statistics:
                print(f"   总消息数: {summary.statistics.message_count}")
                print(f"   开始时间: {summary.statistics.message_start_time}")
                print(f"   结束时间: {summary.statistics.message_end_time}")
                duration = (summary.statistics.message_end_time - summary.statistics.message_start_time) / 1e9
                print(f"   持续时间: {duration:.2f} 秒")
            
            if summary.channels:
                print(f"\n📡 通道信息 (共{len(summary.channels)}个):")
                for channel_id, channel in summary.channels.items():
                    print(f"   - {channel.topic}")
                    print(f"     类型: {channel.message_encoding}")
                    print(f"     Schema ID: {channel.schema_id}")
        
        # 统计每个topic的消息
        print(f"\n🔍 详细分析每个topic...")
        for schema, channel, message in reader.iter_messages():
            topic = channel.topic
            
            if topic not in topic_stats:
                topic_stats[topic] = {
                    'count': 0,
                    'msg_type': schema.name if schema else 'unknown',
                    'samples': [],
                    'first_msg': None,
                }
            
            topic_stats[topic]['count'] += 1
            
            # 保存前几条消息样本
            if topic_stats[topic]['count'] <= 3:
                try:
                    # 尝试反序列化
                    if schema:
                        if 'CompressedImage' in schema.name:
                            # 图像消息只记录大小
                            topic_stats[topic]['samples'].append(f"[Image data: {len(message.data)} bytes]")
                        elif 'JointState' in schema.name:
                            msg_obj = typestore.deserialize_cdr(message.data, schema.name)
                            topic_stats[topic]['samples'].append({
                                'position': list(msg_obj.position) if hasattr(msg_obj, 'position') else None,
                                'velocity': list(msg_obj.velocity) if hasattr(msg_obj, 'velocity') else None,
                                'effort': list(msg_obj.effort) if hasattr(msg_obj, 'effort') else None,
                            })
                        elif 'Jointposeorientation' in schema.name:
                            msg_obj = typestore.deserialize_cdr(message.data, schema.name)
                            topic_stats[topic]['samples'].append({
                                'position': [msg_obj.pose.position.x, msg_obj.pose.position.y, msg_obj.pose.position.z],
                                'orientation': [msg_obj.pose.orientation.x, msg_obj.pose.orientation.y, 
                                               msg_obj.pose.orientation.z, msg_obj.pose.orientation.w],
                            })
                        else:
                            topic_stats[topic]['samples'].append(f"[未解析类型: {schema.name}]")
                except Exception as e:
                    topic_stats[topic]['samples'].append(f"[解析失败: {str(e)}]")
    
    # 打印统计信息
    print(f"\n" + "=" * 80)
    print(f"📋 Topic统计 (共{len(topic_stats)}个topic):\n")
    
    # 按类别分组
    image_topics = {}
    joint_topics = {}
    pose_topics = {}
    gripper_topics = {}
    other_topics = {}
    
    for topic, stats in topic_stats.items():
        if 'image' in topic.lower() or 'compressed' in stats['msg_type'].lower():
            image_topics[topic] = stats
        elif 'joint_states' in topic:
            joint_topics[topic] = stats
        elif 'udp_arm_position' in topic:
            pose_topics[topic] = stats
        elif 'gripper' in topic:
            gripper_topics[topic] = stats
        else:
            other_topics[topic] = stats
    
    # 打印图像topics
    if image_topics:
        print("🖼️  图像Topics:")
        for topic, stats in sorted(image_topics.items()):
            print(f"   {topic}")
            print(f"      类型: {stats['msg_type']}")
            print(f"      消息数: {stats['count']}")
            if stats['samples']:
                print(f"      样本: {stats['samples'][0]}")
        print()
    
    # 打印关节topics
    if joint_topics:
        print("🤖 关节状态Topics:")
        for topic, stats in sorted(joint_topics.items()):
            print(f"   {topic}")
            print(f"      类型: {stats['msg_type']}")
            print(f"      消息数: {stats['count']}")
            if stats['samples'] and isinstance(stats['samples'][0], dict):
                sample = stats['samples'][0]
                if sample.get('position'):
                    print(f"      维度: {len(sample['position'])}")
                    print(f"      位置范围: [{min(sample['position']):.3f}, {max(sample['position']):.3f}]")
        print()
    
    # 打印末端执行器topics
    if pose_topics:
        print("📍 末端执行器姿态Topics:")
        for topic, stats in sorted(pose_topics.items()):
            print(f"   {topic}")
            print(f"      类型: {stats['msg_type']}")
            print(f"      消息数: {stats['count']}")
            if stats['samples'] and isinstance(stats['samples'][0], dict):
                sample = stats['samples'][0]
                if sample.get('position'):
                    print(f"      位置: {sample['position']}")
                if sample.get('orientation'):
                    print(f"      姿态(quat): {sample['orientation']}")
        print()
    
    # 打印夹爪topics
    if gripper_topics:
        print("🤏 夹爪Topics:")
        for topic, stats in sorted(gripper_topics.items()):
            print(f"   {topic}")
            print(f"      类型: {stats['msg_type']}")
            print(f"      消息数: {stats['count']}")
            if stats['samples']:
                print(f"      样本: {stats['samples'][0]}")
        print()
    
    # 打印其他topics
    if other_topics:
        print("📦 其他Topics:")
        for topic, stats in sorted(other_topics.items()):
            print(f"   {topic}")
            print(f"      类型: {stats['msg_type']}")
            print(f"      消息数: {stats['count']}")
        print()
    
    # 生成配置检查报告
    print("=" * 80)
    print("🔍 配置验证:\n")
    
    expected_topics = {
        '/camera_head/color/image_raw/compressed': 'cam_high_rgb',
        '/camera_left/color/image_raw/compressed': 'cam_left_wrist_rgb',
        '/camera_right/color/image_raw/compressed': 'cam_right_wrist_rgb',
        '/right_arm_controller/joint_states': 'right_arm joints',
        '/right_arm_controller/rm_driver/gripper_pos': 'right gripper',
        '/right_arm_controller/rm_driver/udp_arm_position': 'right eef pose',
        '/left_arm_controller/joint_states': 'left_arm joints',
        '/left_arm_controller/rm_driver/gripper_pos': 'left gripper',
        '/left_arm_controller/rm_driver/udp_arm_position': 'left eef pose',
    }
    
    print("✅ 配置字段验证:")
    for topic, desc in expected_topics.items():
        if topic in topic_stats:
            print(f"   ✅ {desc}: {topic} (消息数: {topic_stats[topic]['count']})")
        else:
            print(f"   ❌ {desc}: {topic} [未找到]")
    
    print("\n⚠️  配置中未使用的topics:")
    for topic in topic_stats.keys():
        if topic not in expected_topics:
            print(f"   - {topic} ({topic_stats[topic]['count']} 消息)")
    
    return topic_stats

if __name__ == "__main__":
    mcap_path = Path("/home/liu/program/robocoin-dataset/data/realman_rmc_aidal:mcap_version/GroceryStore_Restrocking_Fallen_20251012_104159_192_168_10_124/GroceryStore_Restrocking_Fallen_20251012_104159_192_168_10_124_0.mcap")
    
    if not mcap_path.exists():
        print(f"❌ 文件不存在: {mcap_path}")
        exit(1)
    
    stats = analyze_mcap_file(mcap_path)
    
    print(f"\n✅ 分析完成！")

