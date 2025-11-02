#!/usr/bin/env python3
"""
检查MMK2数据集的action维度 - 更新版（适配实际BSON格式）

MMK2的BSON文件结构：
episode_0.bson:
{
    'data': {
        '/action/left_arm/joint_state': [{'t': ..., 'data': {'pos': [...], 'vel': [...], 'eff': [...]}}, ...],
        '/action/right_arm/joint_state': [...],
        '/action/head/joint_state': [...],
        '/action/spine/joint_state': [...]
    }
}

xhand_control_data.bson:
{
    'frames': [
        {'t': ..., 'action': {'left_hand': [...], 'right_hand': [...]}, 'observation': {...}},
        ...
    ]
}
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
    
    components = {}
    
    try:
        with open(episode_bson, "rb") as f:
            data = bson.decode_all(f.read())
            
            if not data:
                print("❌ episode_0.bson 是空的")
                return
            
            frame = data[0]
            print(f"✅ 成功读取，共 {len(data)} 个BSON记录\n")
            
            if 'data' not in frame:
                print("❌ 没有 'data' 字段")
                print(f"   实际的keys: {list(frame.keys())}")
                return
            
            data_field = frame['data']
            
            # 定义要检查的action路径
            action_paths = {
                'left_arm': '/action/left_arm/joint_state',
                'right_arm': '/action/right_arm/joint_state',
                'head': '/action/head/joint_state',
                'spine': '/action/spine/joint_state'
            }
            
            # 检查每个组件
            for component_name, path in action_paths.items():
                print(f"🔸 {component_name}:")
                
                if path in data_field:
                    frames_list = data_field[path]
                    
                    if frames_list and isinstance(frames_list, list):
                        first_frame = frames_list[0]
                        
                        if 'data' in first_frame and isinstance(first_frame['data'], dict):
                            if 'pos' in first_frame['data']:
                                pos = first_frame['data']['pos']
                                dims = len(pos)
                                components[component_name] = dims
                                print(f"   ✅ {path}: {dims} 维")
                                print(f"   📊 数据示例: {pos[:3] if len(pos) > 3 else pos}...")
                                print(f"   ℹ️  总共 {len(frames_list)} 帧")
                            else:
                                print(f"   ❌ 缺少 pos 字段")
                                components[component_name] = 0
                        else:
                            print(f"   ❌ 帧数据格式不正确")
                            components[component_name] = 0
                    else:
                        print(f"   ❌ 不是列表或为空")
                        components[component_name] = 0
                else:
                    if component_name == 'head':
                        print(f"   ⚠️  没有 head action (这在lite版本中是正常的)")
                        components[component_name] = 0
                    else:
                        print(f"   ❌ 缺少 {path}")
                        components[component_name] = 0
                
                print()
            
            subtotal_1 = sum(components.values())
            print(f"📐 Part 1 小计: {subtotal_1} 维")
            comp_str = " + ".join([f"{name}({dims})" for name, dims in components.items()])
            print(f"   {comp_str}\n")
            
    except Exception as e:
        print(f"❌ 读取 episode_0.bson 失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ========================================
    # Part 2: 检查 xhand_control_data.bson
    # ========================================
    print("-" * 80)
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
            print(f"✅ 成功读取，共 {len(data)} 个BSON记录\n")
            
            if 'frames' not in frame:
                print("❌ 没有 'frames' 字段")
                print(f"   实际的keys: {list(frame.keys())}")
                return
            
            frames = frame['frames']
            print(f"ℹ️  frames 列表长度: {len(frames)}\n")
            
            if not frames:
                print("❌ frames 列表为空")
                return
            
            first_frame = frames[0]
            
            if 'action' not in first_frame:
                print("❌ 第一帧没有 'action' 字段")
                print(f"   实际的keys: {list(first_frame.keys())}")
                return
            
            action = first_frame['action']
            
            # 左手
            print("🔸 左手 (left_hand):")
            if 'left_hand' in action:
                left_hand = action['left_hand']
                if isinstance(left_hand, list):
                    dims = len(left_hand)
                    components['left_hand'] = dims
                    print(f"   ✅ action.left_hand: {dims} 维")
                    print(f"   📊 数据示例: {left_hand[:3]}...")
                else:
                    print(f"   ❌ left_hand 不是列表")
                    components['left_hand'] = 0
            else:
                print(f"   ❌ 缺少 left_hand 字段")
                components['left_hand'] = 0
            
            # 右手
            print("\n🔸 右手 (right_hand):")
            if 'right_hand' in action:
                right_hand = action['right_hand']
                if isinstance(right_hand, list):
                    dims = len(right_hand)
                    components['right_hand'] = dims
                    print(f"   ✅ action.right_hand: {dims} 维")
                    print(f"   📊 数据示例: {right_hand[:3]}...")
                else:
                    print(f"   ❌ right_hand 不是列表")
                    components['right_hand'] = 0
            else:
                print(f"   ❌ 缺少 right_hand 字段")
                components['right_hand'] = 0
            
            subtotal_2 = components.get('left_hand', 0) + components.get('right_hand', 0)
            print(f"\n📐 Part 2 小计: {subtotal_2} 维")
            print(f"   left_hand({components['left_hand']}) + right_hand({components['right_hand']})\n")
            
    except Exception as e:
        print(f"❌ 读取 xhand_control_data.bson 失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ========================================
    # 总结
    # ========================================
    total_dims = sum(components.values())
    
    print("=" * 80)
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
            if components.get('left_hand', 0) == 11 and components.get('right_hand', 0) == 11:
                print("      → 双手各缺1维 (11+11 instead of 12+12)")
            elif components.get('spine', 0) == 0 and (components.get('left_arm', 0) == 5 or components.get('right_arm', 0) == 5):
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
        print('  python check_mmk2_action_dimensions.py "/mnt/nas/.../episode_12"')
        sys.exit(1)
    
    episode_dir = Path(sys.argv[1])
    check_episode_action(episode_dir)
