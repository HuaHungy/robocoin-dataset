#!/usr/bin/env python3
"""手动解析Realman Joint States（绕过rosbags bug）"""

import struct
import numpy as np
from pathlib import Path
from mcap.reader import make_reader

def parse_cdr_joint_state(data):
    """手动解析CDR格式的JointState消息"""
    try:
        offset = 0
        
        # Skip CDR header (4 bytes)
        offset += 4
        
        # Parse Header
        # timestamp (8 bytes sec + 4 bytes nanosec)
        sec = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        nanosec = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        
        # frame_id string length + data
        frame_id_len = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        frame_id = data[offset:offset+frame_id_len].decode('utf-8').rstrip('\x00')
        offset += frame_id_len
        # Align to 4 bytes
        while offset % 4 != 0:
            offset += 1
        
        # Parse name array
        name_count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        names = []
        for _ in range(name_count):
            name_len = struct.unpack_from('<I', data, offset)[0]
            offset += 4
            name = data[offset:offset+name_len].decode('utf-8').rstrip('\x00')
            names.append(name)
            offset += name_len
            # Align to 4 bytes
            while offset % 4 != 0:
                offset += 1
        
        # Parse position array
        pos_count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        positions = []
        for _ in range(pos_count):
            pos = struct.unpack_from('<d', data, offset)[0]  # double (8 bytes)
            positions.append(pos)
            offset += 8
        
        # Parse velocity array
        vel_count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        velocities = []
        for _ in range(vel_count):
            vel = struct.unpack_from('<d', data, offset)[0]  # double (8 bytes)
            velocities.append(vel)
            offset += 8
        
        # Parse effort array
        eff_count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        efforts = []
        for _ in range(eff_count):
            eff = struct.unpack_from('<d', data, offset)[0]  # double (8 bytes)
            efforts.append(eff)
            offset += 8
        
        return {
            'timestamp': sec + nanosec * 1e-9,
            'frame_id': frame_id,
            'names': names,
            'position': positions,
            'velocity': velocities,
            'effort': efforts
        }
    except Exception as e:
        return None

def analyze_joint_states(mcap_path: Path):
    """分析Joint States数据"""
    
    print(f"🔬 手动解析Joint States")
    print("=" * 80)
    
    topics_of_interest = [
        '/left_arm_controller/joint_states',
        '/right_arm_controller/joint_states'
    ]
    
    for topic_name in topics_of_interest:
        print(f"\n📍 {topic_name}")
        print("-" * 80)
        
        positions_list = []
        velocities_list = []
        efforts_list = []
        msg_count = 0
        
        with open(mcap_path, "rb") as f:
            reader = make_reader(f)
            for schema, channel, message in reader.iter_messages():
                if channel.topic == topic_name:
                    result = parse_cdr_joint_state(message.data)
                    if result:
                        msg_count += 1
                        positions_list.append(result['position'])
                        velocities_list.append(result['velocity'])
                        efforts_list.append(result['effort'])
                        
                        if msg_count == 1:
                            print(f"\n✅ 成功解析第1条消息:")
                            print(f"   Joint Names: {result['names']}")
                            print(f"   Position: {result['position']}")
                            print(f"   Velocity: {result['velocity']}")
                            print(f"   Effort: {result['effort']}")
                    
                    if msg_count >= 1000:  # 采样前1000条
                        break
        
        if positions_list:
            positions = np.array(positions_list)
            velocities = np.array(velocities_list)
            efforts = np.array(efforts_list)
            
            print(f"\n📊 数值统计 (基于{msg_count}条消息):")
            
            print(f"\n   Position ({positions.shape}):")
            for i in range(positions.shape[1]):
                col = positions[:, i]
                non_zero = np.count_nonzero(col)
                is_all_zero = (non_zero == 0)
                is_constant = (np.std(col) < 1e-10) and not is_all_zero
                status = "⚠️全零" if is_all_zero else ("⚠️常量" if is_constant else "✅正常")
                print(f"      [{i}] min={col.min():.4f}, max={col.max():.4f}, "
                      f"mean={col.mean():.4f}, std={col.std():.4f}, "
                      f"非零={non_zero}/{len(col)} ({100*non_zero/len(col):.1f}%) {status}")
            
            print(f"\n   Velocity ({velocities.shape}):")
            for i in range(velocities.shape[1]):
                col = velocities[:, i]
                non_zero = np.count_nonzero(col)
                is_all_zero = (non_zero == 0)
                is_constant = (np.std(col) < 1e-10) and not is_all_zero
                status = "⚠️全零" if is_all_zero else ("⚠️常量" if is_constant else "✅正常")
                print(f"      [{i}] min={col.min():.4f}, max={col.max():.4f}, "
                      f"mean={col.mean():.4f}, std={col.std():.4f}, "
                      f"非零={non_zero}/{len(col)} ({100*non_zero/len(col):.1f}%) {status}")
            
            print(f"\n   Effort ({efforts.shape}):")
            for i in range(efforts.shape[1]):
                col = efforts[:, i]
                non_zero = np.count_nonzero(col)
                is_all_zero = (non_zero == 0)
                is_constant = (np.std(col) < 1e-10) and not is_all_zero
                status = "⚠️全零" if is_all_zero else ("⚠️常量" if is_constant else "✅正常")
                print(f"      [{i}] min={col.min():.4f}, max={col.max():.4f}, "
                      f"mean={col.mean():.4f}, std={col.std():.4f}, "
                      f"非零={non_zero}/{len(col)} ({100*non_zero/len(col):.1f}%) {status}")
        else:
            print(f"❌ 未能解析任何消息")

if __name__ == "__main__":
    mcap_path = Path("/home/liu/program/robocoin-dataset/data/realman_rmc_aidal:mcap_version/GroceryStore_Restrocking_Fallen_20251012_104159_192_168_10_124/GroceryStore_Restrocking_Fallen_20251012_104159_192_168_10_124_0.mcap")
    
    if not mcap_path.exists():
        print(f"❌ 文件不存在: {mcap_path}")
        exit(1)
    
    analyze_joint_states(mcap_path)

