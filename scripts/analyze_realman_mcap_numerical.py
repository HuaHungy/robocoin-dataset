#!/usr/bin/env python3
"""Realman MCAP数值深度分析 - 分析所有字段的min/max/mean/std"""

import numpy as np
from pathlib import Path
from mcap.reader import make_reader
from rosbags.typesys import Stores, get_typestore, get_types_from_msg

def analyze_mcap_numerical(mcap_path: Path):
    """深度数值分析所有topic"""
    
    typestore = get_typestore(Stores.ROS2_FOXY)
    
    # 注册自定义消息
    msg_definitions = {
        'rm_ros_interfaces/msg/Jointposeorientation': """
std_msgs/Header header
geometry_msgs/Pose pose
""",
        'rm_ros_interfaces/msg/Jointspeed': """
std_msgs/Header header
float32[] joint_speed
""",
        'rm_ros_interfaces/msg/Jointacc': """
std_msgs/Header header
float32[] joint_acc
""",
        'rm_ros_interfaces/msg/Sixforce': """
std_msgs/Header header
float32 force_fx
float32 force_fy
float32 force_fz
float32 force_mx
float32 force_my
float32 force_mz
""",
    }
    
    for msg_name, msg_text in msg_definitions.items():
        try:
            msg_types = get_types_from_msg(msg_text, msg_name)
            typestore.register(msg_types)
        except:
            pass
    
    print(f"📊 Realman MCAP深度数值分析")
    print("=" * 80)
    
    # 收集所有消息
    topic_data = {}
    
    print(f"\n🔍 读取MCAP文件: {mcap_path.name}")
    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        for schema, channel, message in reader.iter_messages():
            topic = channel.topic
            if topic not in topic_data:
                topic_data[topic] = {
                    'schema': schema,
                    'messages': []
                }
            topic_data[topic]['messages'].append(message.data)
    
    print(f"✅ 读取完成，共{len(topic_data)}个topic\n")
    
    # 分析数值
    results = {}
    
    # 分析关节状态
    print("=" * 80)
    print("🤖 关节状态数值分析\n")
    
    for topic in ['/right_arm_controller/joint_states', '/left_arm_controller/joint_states']:
        if topic not in topic_data:
            continue
        
        print(f"📍 {topic}")
        schema = topic_data[topic]['schema']
        messages = topic_data[topic]['messages']
        
        # 解析所有消息
        positions = []
        velocities = []
        efforts = []
        
        for msg_data in messages:
            try:
                msg = typestore.deserialize_cdr(msg_data, schema.name)
                if hasattr(msg, 'position') and msg.position:
                    positions.append(list(msg.position))
                if hasattr(msg, 'velocity') and msg.velocity:
                    velocities.append(list(msg.velocity))
                if hasattr(msg, 'effort') and msg.effort:
                    efforts.append(list(msg.effort))
            except:
                pass
        
        # 分析position
        if positions:
            positions = np.array(positions)
            print(f"   Position ({positions.shape}):")
            for i in range(positions.shape[1]):
                col = positions[:, i]
                non_zero = np.count_nonzero(col)
                print(f"      [{i}] min={col.min():.3f}, max={col.max():.3f}, "
                      f"mean={col.mean():.3f}, std={col.std():.3f}, "
                      f"非零={non_zero}/{len(col)} ({100*non_zero/len(col):.1f}%)")
        
        # 分析velocity
        if velocities:
            velocities = np.array(velocities)
            print(f"   Velocity ({velocities.shape}):")
            for i in range(velocities.shape[1]):
                col = velocities[:, i]
                non_zero = np.count_nonzero(col)
                print(f"      [{i}] min={col.min():.3f}, max={col.max():.3f}, "
                      f"mean={col.mean():.3f}, std={col.std():.3f}, "
                      f"非零={non_zero}/{len(col)} ({100*non_zero/len(col):.1f}%)")
        
        # 分析effort
        if efforts:
            efforts = np.array(efforts)
            print(f"   Effort ({efforts.shape}):")
            for i in range(efforts.shape[1]):
                col = efforts[:, i]
                non_zero = np.count_nonzero(col)
                print(f"      [{i}] min={col.min():.3f}, max={col.max():.3f}, "
                      f"mean={col.mean():.3f}, std={col.std():.3f}, "
                      f"非零={non_zero}/{len(col)} ({100*non_zero/len(col):.1f}%)")
        print()
    
    # 分析夹爪
    print("=" * 80)
    print("🤏 夹爪数值分析\n")
    
    for topic in ['/right_arm_controller/rm_driver/gripper_pos', 
                  '/left_arm_controller/rm_driver/gripper_pos']:
        if topic not in topic_data:
            continue
        
        print(f"📍 {topic}")
        schema = topic_data[topic]['schema']
        messages = topic_data[topic]['messages']
        
        positions = []
        for msg_data in messages:
            try:
                msg = typestore.deserialize_cdr(msg_data, schema.name)
                if hasattr(msg, 'position') and msg.position:
                    positions.append(msg.position[0])
            except:
                pass
        
        if positions:
            positions = np.array(positions)
            non_zero = np.count_nonzero(positions)
            print(f"   Gripper Position: min={positions.min():.3f}, max={positions.max():.3f}, "
                  f"mean={positions.mean():.3f}, std={positions.std():.3f}, "
                  f"非零={non_zero}/{len(positions)} ({100*non_zero/len(positions):.1f}%)")
        print()
    
    # 分析末端执行器位姿
    print("=" * 80)
    print("📍 末端执行器位姿数值分析\n")
    
    for topic in ['/right_arm_controller/rm_driver/udp_arm_position',
                  '/left_arm_controller/rm_driver/udp_arm_position']:
        if topic not in topic_data:
            continue
        
        print(f"📍 {topic}")
        schema = topic_data[topic]['schema']
        messages = topic_data[topic]['messages']
        
        positions = []
        orientations = []
        
        for msg_data in messages:
            try:
                msg = typestore.deserialize_cdr(msg_data, schema.name)
                positions.append([msg.pose.position.x, msg.pose.position.y, msg.pose.position.z])
                orientations.append([msg.pose.orientation.x, msg.pose.orientation.y, 
                                    msg.pose.orientation.z, msg.pose.orientation.w])
            except:
                pass
        
        if positions:
            positions = np.array(positions)
            print(f"   Position ({positions.shape}):")
            labels = ['x', 'y', 'z']
            for i in range(3):
                col = positions[:, i]
                print(f"      [{labels[i]}] min={col.min():.3f}, max={col.max():.3f}, "
                      f"mean={col.mean():.3f}, std={col.std():.3f}")
        
        if orientations:
            orientations = np.array(orientations)
            print(f"   Orientation (Quat) ({orientations.shape}):")
            labels = ['x', 'y', 'z', 'w']
            for i in range(4):
                col = orientations[:, i]
                print(f"      [{labels[i]}] min={col.min():.3f}, max={col.max():.3f}, "
                      f"mean={col.mean():.3f}, std={col.std():.3f}")
        print()
    
    # 分析P1字段：速度
    print("=" * 80)
    print("🆕 P1字段：关节速度数值分析\n")
    
    for topic in ['/right_arm_controller/rm_driver/udp_joint_speed',
                  '/left_arm_controller/rm_driver/udp_joint_speed']:
        if topic not in topic_data:
            continue
        
        print(f"📍 {topic}")
        schema = topic_data[topic]['schema']
        messages = topic_data[topic]['messages']
        
        speeds = []
        for msg_data in messages:
            try:
                msg = typestore.deserialize_cdr(msg_data, schema.name)
                if hasattr(msg, 'joint_speed') and msg.joint_speed:
                    speeds.append(list(msg.joint_speed))
            except:
                pass
        
        if speeds:
            speeds = np.array(speeds)
            print(f"   Joint Speed ({speeds.shape}):")
            for i in range(speeds.shape[1]):
                col = speeds[:, i]
                non_zero = np.count_nonzero(col)
                is_all_zero = (non_zero == 0)
                is_constant = (np.std(col) < 1e-10) and not is_all_zero
                status = "全零" if is_all_zero else ("常量" if is_constant else "正常")
                print(f"      [{i}] min={col.min():.3f}, max={col.max():.3f}, "
                      f"mean={col.mean():.3f}, std={col.std():.3f}, "
                      f"非零={non_zero}/{len(col)} ({100*non_zero/len(col):.1f}%) [{status}]")
        print()
    
    # 分析P1字段：加速度
    print("=" * 80)
    print("🆕 P1字段：关节加速度数值分析\n")
    
    for topic in ['/right_arm_controller/rm_driver/udp_joint_acc',
                  '/left_arm_controller/rm_driver/udp_joint_acc']:
        if topic not in topic_data:
            continue
        
        print(f"📍 {topic}")
        schema = topic_data[topic]['schema']
        messages = topic_data[topic]['messages']
        
        accs = []
        for msg_data in messages:
            try:
                msg = typestore.deserialize_cdr(msg_data, schema.name)
                if hasattr(msg, 'joint_acc') and msg.joint_acc:
                    accs.append(list(msg.joint_acc))
            except:
                pass
        
        if accs:
            accs = np.array(accs)
            print(f"   Joint Acceleration ({accs.shape}):")
            for i in range(accs.shape[1]):
                col = accs[:, i]
                non_zero = np.count_nonzero(col)
                is_all_zero = (non_zero == 0)
                is_constant = (np.std(col) < 1e-10) and not is_all_zero
                status = "全零" if is_all_zero else ("常量" if is_constant else "正常")
                print(f"      [{i}] min={col.min():.3f}, max={col.max():.3f}, "
                      f"mean={col.mean():.3f}, std={col.std():.3f}, "
                      f"非零={non_zero}/{len(col)} ({100*non_zero/len(col):.1f}%) [{status}]")
        print()
    
    # 分析P1字段：六维力
    print("=" * 80)
    print("🆕 P1字段：六维力传感器数值分析\n")
    
    for topic in ['/right_arm_controller/rm_driver/udp_six_force',
                  '/left_arm_controller/rm_driver/udp_six_force']:
        if topic not in topic_data:
            continue
        
        print(f"📍 {topic}")
        schema = topic_data[topic]['schema']
        messages = topic_data[topic]['messages']
        
        forces = []
        for msg_data in messages:
            try:
                msg = typestore.deserialize_cdr(msg_data, schema.name)
                forces.append([msg.force_fx, msg.force_fy, msg.force_fz,
                              msg.force_mx, msg.force_my, msg.force_mz])
            except:
                pass
        
        if forces:
            forces = np.array(forces)
            print(f"   Six Force ({forces.shape}):")
            labels = ['fx', 'fy', 'fz', 'mx', 'my', 'mz']
            for i in range(6):
                col = forces[:, i]
                non_zero = np.count_nonzero(col)
                is_all_zero = (non_zero == 0)
                is_constant = (np.std(col) < 1e-10) and not is_all_zero
                status = "全零" if is_all_zero else ("常量" if is_constant else "正常")
                print(f"      [{labels[i]}] min={col.min():.3f}, max={col.max():.3f}, "
                      f"mean={col.mean():.3f}, std={col.std():.3f}, "
                      f"非零={non_zero}/{len(col)} ({100*non_zero/len(col):.1f}%) [{status}]")
        print()
    
    print("=" * 80)
    print("✅ 数值分析完成！")

if __name__ == "__main__":
    mcap_path = Path("/home/liu/program/robocoin-dataset/data/realman_rmc_aidal:mcap_version/GroceryStore_Restrocking_Fallen_20251012_104159_192_168_10_124/GroceryStore_Restrocking_Fallen_20251012_104159_192_168_10_124_0.mcap")
    
    if not mcap_path.exists():
        print(f"❌ 文件不存在: {mcap_path}")
        exit(1)
    
    analyze_mcap_numerical(mcap_path)

