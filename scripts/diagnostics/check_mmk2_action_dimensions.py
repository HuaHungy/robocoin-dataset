#!/usr/bin/env python3
"""
检查MMK2数据集的action维度

直接输出每个组件的维度，方便快速诊断
"""

import sys
import bson
from pathlib import Path

def check_episode_action(episode_dir: Path):
    """检查episode的action维度并输出详细信息"""
    
    print("=" * 80)
    print("🔍 MMK2 Action Dimension Analysis")
    print("=" * 80)
    print(f"\n📁 Episode Directory:\n   {episode_dir}\n")
    
    # 检查目录是否存在
    if not episode_dir.exists():
        print(f"❌ 错误：目录不存在！\n   {episode_dir}")
        return
    
    # ========================================
    # Part 1: 检查 episode_0.bson
    # ========================================
    print("-" * 80)
    print("📄 Part 1: episode_0.bson (arms + head + spine)")
    print("-" * 80)
    
    episode_bson = episode_dir / "episode_0.bson"
    if not episode_bson.exists():
        print("❌ 文件不存在: episode_0.bson")
        return
    
    try:
        with open(episode_bson, "rb") as f:
            data = bson.decode_all(f.read())
            
            if not data:
                print("❌ episode_0.bson 是空的")
                return
            
            # 取第一帧
            frame = data[0]
            print(f"✅ 成功读取，共 {len(data)} 帧\n")
            
            if 'action' not in frame:
                print("❌ 第一帧中没有 'action' 字段")
                return
            
            action = frame['action']
            print(f"📋 action字段的keys: {list(action.keys())}\n")
            
            components = {}
            
            # 左臂
            print("🔸 左臂 (left_arm):")
            if 'left_arm' in action:
                if 'joint_state' in action['left_arm']:
                    if 'pos' in action['left_arm']['joint_state']:
                        left_arm_pos = action['left_arm']['joint_state']['pos']
                        components['left_arm'] = len(left_arm_pos)
                        print(f"   ✅ action/left_arm/joint_state/pos: {len(left_arm_pos)} 维")
                        print(f"   📊 数据示例: {left_arm_pos[:3]}...")
                    else:
                        print("   ❌ 缺少 pos 字段")
                        components['left_arm'] = 0
                else:
                    print("   ❌ 缺少 joint_state 字段")
                    components['left_arm'] = 0
            else:
                print("   ❌ 缺少 left_arm 字段")
                components['left_arm'] = 0
            
            # 右臂
            print("\n🔸 右臂 (right_arm):")
            if 'right_arm' in action:
                if 'joint_state' in action['right_arm']:
                    if 'pos' in action['right_arm']['joint_state']:
                        right_arm_pos = action['right_arm']['joint_state']['pos']
                        components['right_arm'] = len(right_arm_pos)
                        print(f"   ✅ action/right_arm/joint_state/pos: {len(right_arm_pos)} 维")
                        print(f"   📊 数据示例: {right_arm_pos[:3]}...")
                    else:
                        print("   ❌ 缺少 pos 字段")
                        components['right_arm'] = 0
                else:
                    print("   ❌ 缺少 joint_state 字段")
                    components['right_arm'] = 0
            else:
                print("   ❌ 缺少 right_arm 字段")
                components['right_arm'] = 0
            
            # 头部
            print("\n🔸 头部 (head):")
            if 'head' in action:
                if 'joint_state' in action['head']:
                    if 'pos' in action['head']['joint_state']:
                        head_pos = action['head']['joint_state']['pos']
                        components['head'] = len(head_pos)
                        print(f"   ✅ action/head/joint_state/pos: {len(head_pos)} 维")
                        print(f"   📊 数据示例: {head_pos}")
                    else:
                        print("   ❌ 缺少 pos 字段")
                        components['head'] = 0
                else:
                    print("   ❌ 缺少 joint_state 字段")
                    components['head'] = 0
            else:
                print("   ⚠️  没有 head 字段 (这是正常的，lite版本不需要head)")
                components['head'] = 0
            
            # 脊柱
            print("\n🔸 脊柱 (spine):")
            if 'spine' in action:
                if 'joint_state' in action['spine']:
                    if 'pos' in action['spine']['joint_state']:
                        spine_pos = action['spine']['joint_state']['pos']
                        components['spine'] = len(spine_pos)
                        print(f"   ✅ action/spine/joint_state/pos: {len(spine_pos)} 维")
                        print(f"   📊 数据示例: {spine_pos}")
                    else:
                        print("   ❌ 缺少 pos 字段")
                        components['spine'] = 0
                else:
                    print("   ❌ 缺少 joint_state 字段")
                    components['spine'] = 0
            else:
                print("   ❌ 缺少 spine 字段")
                components['spine'] = 0
            
            subtotal_1 = sum(components.values())
            print(f"\n📐 Part 1 小计: {subtotal_1} 维")
            print(f"   left_arm({components['left_arm']}) + right_arm({components['right_arm']}) + head({components['head']}) + spine({components['spine']})")
            
    except Exception as e:
        print(f"❌ 读取 episode_0.bson 失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ========================================
    # Part 2: 检查 xhand_control_data.bson
    # ========================================
    print("\n" + "-" * 80)
    print("📄 Part 2: xhand_control_data.bson (hands)")
    print("-" * 80)
    
    xhand_bson = episode_dir / "xhand_control_data.bson"
    if not xhand_bson.exists():
        print("❌ 文件不存在: xhand_control_data.bson")
        return
    
    try:
        with open(xhand_bson, "rb") as f:
            data = bson.decode_all(f.read())
            
            if not data:
                print("❌ xhand_control_data.bson 是空的")
                return
            
            frame = data[0]
            print(f"✅ 成功读取，共 {len(data)} 帧\n")
            
            if 'action' not in frame:
                print("❌ 第一帧中没有 'action' 字段")
                return
            
            action = frame['action']
            print(f"📋 action字段的keys: {list(action.keys())}\n")
            
            # 左手
            print("🔸 左手 (left_hand):")
            if 'left_hand' in action:
                left_hand_data = action['left_hand']
                components['left_hand'] = len(left_hand_data)
                print(f"   ✅ action.left_hand: {len(left_hand_data)} 维")
                print(f"   📊 数据示例: {left_hand_data[:3]}...")
            else:
                print("   ❌ 缺少 left_hand 字段")
                components['left_hand'] = 0
            
            # 右手
            print("\n🔸 右手 (right_hand):")
            if 'right_hand' in action:
                right_hand_data = action['right_hand']
                components['right_hand'] = len(right_hand_data)
                print(f"   ✅ action.right_hand: {len(right_hand_data)} 维")
                print(f"   📊 数据示例: {right_hand_data[:3]}...")
            else:
                print("   ❌ 缺少 right_hand 字段")
                components['right_hand'] = 0
            
            subtotal_2 = components.get('left_hand', 0) + components.get('right_hand', 0)
            print(f"\n📐 Part 2 小计: {subtotal_2} 维")
            print(f"   left_hand({components['left_hand']}) + right_hand({components['right_hand']})")
            
    except Exception as e:
        print(f"❌ 读取 xhand_control_data.bson 失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ========================================
    # 总结
    # ========================================
    total_dims = sum(components.values())
    
    print("\n" + "=" * 80)
    print("📊 最终统计")
    print("=" * 80)
    
    print("\n🔢 各组件维度:")
    for component, dims in components.items():
        status = "✅" if dims > 0 else "❌"
        print(f"   {status} {component:15s}: {dims:2d} 维")
    
    print(f"\n{'=' * 80}")
    print(f"🎯 总维度: {total_dims} 维")
    print(f"{'=' * 80}\n")
    
    # 对比配置
    print("📋 配置对比:")
    print("-" * 80)
    
    configs = {
        'full': {'dims': 39, 'desc': '包含head (2维)'},
        'lite': {'dims': 37, 'desc': '不含head'},
    }
    
    for config_name, config_info in configs.items():
        config_dims = config_info['dims']
        match = "✅ 匹配" if config_dims == total_dims else "❌ 不匹配"
        diff = config_dims - total_dims
        diff_str = f"(期望比实际多 {diff} 维)" if diff > 0 else f"(实际比期望多 {-diff} 维)" if diff < 0 else ""
        
        print(f"   {config_name:10s}: {config_dims:2d}D  {match:8s}  {diff_str}")
        print(f"              ({config_info['desc']})")
    
    # 给出建议
    print("\n💡 建议:")
    print("-" * 80)
    
    if total_dims == 39:
        print("   ✅ 使用配置: converter_config_discover_robotics_aitbot_mmk2_third_view_full.yaml")
        print("   ✅ 数据库设置: device_model_version = 'third_view_full'")
    elif total_dims == 37:
        print("   ✅ 使用配置: converter_config_discover_robotics_aitbot_mmk2_third_view_lite.yaml")
        print("   ✅ 数据库设置: device_model_version = 'third_view_lite'")
    else:
        print(f"   ⚠️  当前维度 {total_dims}D 不匹配任何现有配置！")
        print(f"   📝 需要创建新配置: converter_config_discover_robotics_aitbot_mmk2_{total_dims}d.yaml")
        
        # 分析缺失的维度
        if total_dims == 35:
            print("\n   🔍 可能的原因（35D = 37D - 2D）:")
            if components['left_hand'] == 11 and components['right_hand'] == 11:
                print("      → 双手各缺1维 (11+11 instead of 12+12)")
            elif components['spine'] == 0 and (components['left_arm'] == 5 or components['right_arm'] == 5):
                print("      → spine缺失(1维) + 某个arm缺1维")
            else:
                print("      → 未知组合，请检查上面的详细数据")
        
        print("\n   📋 下一步:")
        print("      1. 检查多个episode确认这是普遍情况")
        print("      2. 根据实际维度创建新配置文件")
        print("      3. 更新 converter_factory_config.yaml")
        print("      4. 更新数据库 device_model_version")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python check_mmk2_action_dimensions.py <episode_dir>")
        print("\nExample:")
        print('  python check_mmk2_action_dimensions.py "/mnt/nas/synnas/docker/6discover_robotics_aitbot_mmk2/storage_peaches_and_pears/the left hand throws the peach into the left compartment, the right hand throws the pear into the right compartment./0"')
        sys.exit(1)
    
    episode_dir = Path(sys.argv[1])
    check_episode_action(episode_dir)

