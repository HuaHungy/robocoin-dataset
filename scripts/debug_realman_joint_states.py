#!/usr/bin/env python3
"""调试Realman Joint States反序列化问题"""

import numpy as np
from pathlib import Path
from mcap.reader import make_reader
from rosbags.typesys import Stores, get_typestore

def debug_joint_states(mcap_path: Path):
    """调试joint_states topic"""
    
    typestore = get_typestore(Stores.ROS2_FOXY)
    
    print(f"🔍 调试Joint States反序列化")
    print("=" * 80)
    
    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        summary = reader.get_summary()
        
        # 找到joint_states相关的channels
        joint_state_channels = []
        for channel_id, channel in summary.channels.items():
            if 'joint_states' in channel.topic.lower():
                joint_state_channels.append((channel_id, channel))
                print(f"\n📍 找到Joint States Topic:")
                print(f"   Topic: {channel.topic}")
                print(f"   Message Type: {channel.message_encoding}")
                print(f"   Schema ID: {channel.schema_id}")
        
        if not joint_state_channels:
            print("❌ 未找到joint_states相关topic")
            return
        
        # 尝试读取和解析消息
        for channel_id, channel in joint_state_channels:
            print(f"\n{'='*80}")
            print(f"🔬 分析 {channel.topic}")
            print("=" * 80)
            
            # 获取该channel的schema
            schema = summary.schemas.get(channel.schema_id)
            if schema:
                print(f"\n📋 Schema信息:")
                print(f"   Name: {schema.name}")
                print(f"   Encoding: {schema.encoding}")
                print(f"   Data (前500字符):\n{schema.data[:500].decode('utf-8', errors='ignore')}")
            
            # 读取前10条消息
            msg_count = 0
            positions_list = []
            velocities_list = []
            efforts_list = []
            
            reader_iter = make_reader(open(mcap_path, "rb"))
            for schema_msg, channel_msg, message in reader_iter.iter_messages():
                if channel_msg.topic == channel.topic:
                    msg_count += 1
                    
                    # 尝试多种反序列化方法
                    try:
                        # 方法1: 使用typestore
                        msg = typestore.deserialize_cdr(message.data, schema.name)
                        
                        if hasattr(msg, 'position') and msg.position:
                            positions_list.append(list(msg.position))
                        if hasattr(msg, 'velocity') and msg.velocity:
                            velocities_list.append(list(msg.velocity))
                        if hasattr(msg, 'effort') and msg.effort:
                            efforts_list.append(list(msg.effort))
                        
                        if msg_count == 1:
                            print(f"\n✅ 成功解析第1条消息:")
                            print(f"   Position: {msg.position if hasattr(msg, 'position') else 'N/A'}")
                            print(f"   Velocity: {msg.velocity if hasattr(msg, 'velocity') else 'N/A'}")
                            print(f"   Effort: {msg.effort if hasattr(msg, 'effort') else 'N/A'}")
                            if hasattr(msg, 'name'):
                                print(f"   Joint Names: {msg.name}")
                    
                    except Exception as e:
                        if msg_count == 1:
                            print(f"\n❌ 反序列化失败: {e}")
                            print(f"   Schema Name: {schema.name}")
                            print(f"   Message Data (前100字节): {message.data[:100]}")
                    
                    if msg_count >= 10:
                        break
            
            print(f"\n📊 统计:")
            print(f"   总消息数: {msg_count}")
            print(f"   Position样本数: {len(positions_list)}")
            print(f"   Velocity样本数: {len(velocities_list)}")
            print(f"   Effort样本数: {len(efforts_list)}")
            
            if positions_list:
                positions = np.array(positions_list)
                print(f"\n✅ Position数据 ({positions.shape}):")
                print(f"   示例值: {positions[0]}")
                print(f"   Min: {positions.min(axis=0)}")
                print(f"   Max: {positions.max(axis=0)}")
            
            if velocities_list:
                velocities = np.array(velocities_list)
                print(f"\n✅ Velocity数据 ({velocities.shape}):")
                print(f"   示例值: {velocities[0]}")
                print(f"   Min: {velocities.min(axis=0)}")
                print(f"   Max: {velocities.max(axis=0)}")
            
            if efforts_list:
                efforts = np.array(efforts_list)
                print(f"\n✅ Effort数据 ({efforts.shape}):")
                print(f"   示例值: {efforts[0]}")
                print(f"   Min: {efforts.min(axis=0)}")
                print(f"   Max: {efforts.max(axis=0)}")

if __name__ == "__main__":
    mcap_path = Path("/home/liu/program/robocoin-dataset/data/realman_rmc_aidal:mcap_version/GroceryStore_Restrocking_Fallen_20251012_104159_192_168_10_124/GroceryStore_Restrocking_Fallen_20251012_104159_192_168_10_124_0.mcap")
    
    if not mcap_path.exists():
        print(f"❌ 文件不存在: {mcap_path}")
        exit(1)
    
    debug_joint_states(mcap_path)

