#!/usr/bin/env python3
"""
MMK2数据集维度诊断工具

快速检查MMK2数据集的action维度，找出与配置不匹配的原因。

Usage:
    python scripts/diagnostics/diagnose_mmk2_dimensions.py \
        --episode-dir /path/to/episode/dir
"""

import argparse
import bson
from pathlib import Path
from typing import Dict, Any


def analyze_episode_action(episode_dir: Path) -> Dict[str, Any]:
    """分析episode的action维度"""
    
    result = {
        'episode_dir': str(episode_dir),
        'components': {},
        'total_dims': 0,
        'errors': []
    }
    
    # 检查episode_0.bson
    episode_bson = episode_dir / "episode_0.bson"
    if not episode_bson.exists():
        result['errors'].append(f"❌ episode_0.bson not found")
        return result
    
    try:
        with open(episode_bson, "rb") as f:
            data = bson.decode_all(f.read())
            
            if not data:
                result['errors'].append("❌ episode_0.bson is empty")
                return result
            
            # 分析第一帧的action
            frame = data[0]
            if 'action' not in frame:
                result['errors'].append("❌ No 'action' field in first frame")
                return result
            
            action = frame['action']
            
            # 检查各个组件
            components = {}
            
            # 左臂
            if 'left_arm' in action and 'joint_state' in action['left_arm']:
                left_arm_pos = action['left_arm']['joint_state'].get('pos', [])
                components['left_arm'] = len(left_arm_pos)
            else:
                components['left_arm'] = 0
                result['errors'].append("⚠️  Missing: action/left_arm/joint_state/pos")
            
            # 右臂
            if 'right_arm' in action and 'joint_state' in action['right_arm']:
                right_arm_pos = action['right_arm']['joint_state'].get('pos', [])
                components['right_arm'] = len(right_arm_pos)
            else:
                components['right_arm'] = 0
                result['errors'].append("⚠️  Missing: action/right_arm/joint_state/pos")
            
            # 头部
            if 'head' in action and 'joint_state' in action['head']:
                head_pos = action['head']['joint_state'].get('pos', [])
                components['head'] = len(head_pos)
            else:
                components['head'] = 0
                result['errors'].append("ℹ️  Missing: action/head/joint_state/pos (可能是lite版本)")
            
            # 脊柱
            if 'spine' in action and 'joint_state' in action['spine']:
                spine_pos = action['spine']['joint_state'].get('pos', [])
                components['spine'] = len(spine_pos)
            else:
                components['spine'] = 0
                result['errors'].append("⚠️  Missing: action/spine/joint_state/pos")
            
            result['components'].update(components)
            
    except Exception as e:
        result['errors'].append(f"❌ Error reading episode_0.bson: {e}")
        return result
    
    # 检查xhand_control_data.bson
    xhand_bson = episode_dir / "xhand_control_data.bson"
    if not xhand_bson.exists():
        result['errors'].append("❌ xhand_control_data.bson not found")
        return result
    
    try:
        with open(xhand_bson, "rb") as f:
            data = bson.decode_all(f.read())
            
            if not data:
                result['errors'].append("❌ xhand_control_data.bson is empty")
                return result
            
            # 分析第一帧
            frame = data[0]
            if 'action' not in frame:
                result['errors'].append("❌ No 'action' field in xhand_control_data")
                return result
            
            action = frame['action']
            
            # 左手
            if 'left_hand' in action:
                result['components']['left_hand'] = len(action['left_hand'])
            else:
                result['components']['left_hand'] = 0
                result['errors'].append("⚠️  Missing: action.left_hand")
            
            # 右手
            if 'right_hand' in action:
                result['components']['right_hand'] = len(action['right_hand'])
            else:
                result['components']['right_hand'] = 0
                result['errors'].append("⚠️  Missing: action.right_hand")
            
    except Exception as e:
        result['errors'].append(f"❌ Error reading xhand_control_data.bson: {e}")
        return result
    
    # 计算总维度
    result['total_dims'] = sum(result['components'].values())
    
    return result


def print_diagnosis(result: Dict[str, Any]):
    """打印诊断结果"""
    
    print("=" * 80)
    print("🔍 MMK2 Action Dimension Diagnosis")
    print("=" * 80)
    print(f"\n📁 Episode Directory: {result['episode_dir']}\n")
    
    # 打印组件维度
    print("📊 Action Components:")
    print("-" * 80)
    
    components = result['components']
    if components:
        for component, dims in components.items():
            status = "✅" if dims > 0 else "❌"
            print(f"  {status} {component:20s}: {dims:2d} dimensions")
        
        print("-" * 80)
        print(f"  📐 Total Dimensions: {result['total_dims']}")
    else:
        print("  ❌ No components found")
    
    # 对比配置
    print("\n📋 Configuration Comparison:")
    print("-" * 80)
    
    configs = {
        'full': {
            'left_arm': 6, 'right_arm': 6, 'head': 2, 'spine': 1,
            'left_hand': 12, 'right_hand': 12, 'total': 39
        },
        'lite': {
            'left_arm': 6, 'right_arm': 6, 'head': 0, 'spine': 1,
            'left_hand': 12, 'right_hand': 12, 'total': 37
        }
    }
    
    actual_total = result['total_dims']
    
    for config_name, config_dims in configs.items():
        match = "✅ MATCH" if config_dims['total'] == actual_total else "❌ MISMATCH"
        diff = config_dims['total'] - actual_total
        diff_str = f"({diff:+d})" if diff != 0 else ""
        
        print(f"  {config_name:10s}: {config_dims['total']:2d}D  {match} {diff_str}")
    
    # 打印错误和警告
    if result['errors']:
        print("\n⚠️  Issues Found:")
        print("-" * 80)
        for error in result['errors']:
            print(f"  {error}")
    
    # 提供建议
    print("\n💡 Recommendations:")
    print("-" * 80)
    
    if actual_total == 39:
        print("  ✅ Use config: converter_config_discover_robotics_aitbot_mmk2_third_view_full.yaml")
        print("  ✅ Set device_model_version: third_view_full")
    elif actual_total == 37:
        print("  ✅ Use config: converter_config_discover_robotics_aitbot_mmk2_third_view_lite.yaml")
        print("  ✅ Set device_model_version: third_view_lite")
    elif actual_total == 35:
        print("  ⚠️  Custom 35D version detected!")
        print("  📝 Create new config: converter_config_discover_robotics_aitbot_mmk2_35d.yaml")
        print("  🔧 Likely causes:")
        
        # 分析可能的原因
        if components.get('left_hand', 0) == 11 and components.get('right_hand', 0) == 11:
            print("     - Both hands have 11D (missing 1D each)")
        elif components.get('left_hand', 0) == 10 and components.get('right_hand', 0) == 10:
            print("     - Both hands have 10D (missing 2D each)")
        elif components.get('spine', 0) == 0:
            print("     - Spine action missing")
        else:
            print("     - Unknown combination - check component details above")
        
        print("\n  📋 Next Steps:")
        print("     1. Verify this pattern across multiple episodes")
        print("     2. Create config based on actual dimensions")
        print("     3. Update converter_factory_config.yaml")
        print("     4. Update database device_model_version")
    else:
        print(f"  ⚠️  Unexpected dimension count: {actual_total}D")
        print("  🔍 Manual investigation required")
        print("     1. Check if data is corrupted")
        print("     2. Verify data collection process")
        print("     3. Contact data provider for clarification")
    
    print("\n" + "=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose MMK2 action dimensions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Diagnose a single episode
    python scripts/diagnostics/diagnose_mmk2_dimensions.py \\
        --episode-dir /path/to/task/0

    # Diagnose the problematic dataset
    python scripts/diagnostics/diagnose_mmk2_dimensions.py \\
        --episode-dir "/mnt/nas/synnas/docker/6discover_robotics_aitbot_mmk2/storage_peaches_and_pears/the left hand throws the peach into the left compartment, the right hand throws the pear into the right compartment./0"
        """
    )
    
    parser.add_argument(
        '--episode-dir',
        type=Path,
        required=True,
        help='Path to episode directory (containing episode_0.bson and xhand_control_data.bson)'
    )
    
    args = parser.parse_args()
    
    # 验证目录存在
    if not args.episode_dir.exists():
        print(f"❌ Error: Episode directory not found: {args.episode_dir}")
        return 1
    
    if not args.episode_dir.is_dir():
        print(f"❌ Error: Not a directory: {args.episode_dir}")
        return 1
    
    # 运行诊断
    result = analyze_episode_action(args.episode_dir)
    
    # 打印结果
    print_diagnosis(result)
    
    # 返回状态码
    if result['total_dims'] in [37, 39]:
        return 0  # 匹配已知配置
    else:
        return 1  # 需要创建新配置


if __name__ == "__main__":
    exit(main())

