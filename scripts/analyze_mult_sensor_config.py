#!/usr/bin/env python3
"""
Agilex Mult_Sensor 配置检测器
验证配置文件与实际数据的匹配情况
"""

import json
import yaml
import numpy as np
from pathlib import Path
from collections import defaultdict


def load_config(config_path):
    """加载配置文件"""
    with open(config_path) as f:
        return yaml.safe_load(f)


def analyze_episode_structure(ep_dir):
    """分析episode的数据结构"""
    print(f"\n{'='*80}")
    print(f"📂 分析 Episode: {ep_dir.name}")
    print(f"{'='*80}")
    
    structure = {
        'joint_state': {},
        'localization': {},
        'cameras': {}
    }
    
    # 1. 分析 joint state 数据
    joint_dir = ep_dir / "arm" / "jointState"
    if joint_dir.exists():
        for joint_type in ['puppetLeft', 'puppetRight', 'masterLeft', 'masterRight']:
            type_dir = joint_dir / joint_type
            if type_dir.exists():
                json_files = sorted(type_dir.glob("*.json"))
                if json_files:
                    # 读取第一个文件分析结构
                    with open(json_files[0]) as f:
                        sample = json.load(f)
                    
                    structure['joint_state'][joint_type] = {
                        'file_count': len(json_files),
                        'fields': list(sample.keys()),
                        'dimensions': {}
                    }
                    
                    # 分析每个字段的维度
                    for field, value in sample.items():
                        if isinstance(value, list):
                            structure['joint_state'][joint_type]['dimensions'][field] = len(value)
                    
                    print(f"\n  ✅ {joint_type}: {len(json_files)} 文件")
                    print(f"     Fields: {list(sample.keys())}")
                    print(f"     Dimensions: {structure['joint_state'][joint_type]['dimensions']}")
    
    # 2. 分析 localization 数据
    loc_dir = ep_dir / "localization" / "pose"
    if loc_dir.exists():
        for loc_side in ['puppetLeft', 'puppetRight', 'pika_l', 'pika_r']:
            side_dir = loc_dir / loc_side
            if side_dir.exists():
                json_files = sorted(side_dir.glob("*.json"))
                if json_files:
                    with open(json_files[0]) as f:
                        sample = json.load(f)
                    
                    structure['localization'][loc_side] = {
                        'file_count': len(json_files),
                        'fields': list(sample.keys())
                    }
                    
                    print(f"\n  ✅ Localization {loc_side}: {len(json_files)} 文件")
                    print(f"     Fields: {list(sample.keys())}")
    
    # 3. 分析相机数据
    camera_base = ep_dir / "camera"
    if camera_base.exists():
        for cam_type in ['color', 'depth']:
            cam_type_dir = camera_base / cam_type
            if cam_type_dir.exists():
                for cam_folder in cam_type_dir.iterdir():
                    if cam_folder.is_dir():
                        images = list(cam_folder.glob("*.jpg")) + list(cam_folder.glob("*.png"))
                        if images:
                            structure['cameras'][f'{cam_type}/{cam_folder.name}'] = {
                                'image_count': len(images),
                                'format': images[0].suffix
                            }
                            print(f"\n  ✅ Camera {cam_type}/{cam_folder.name}: {len(images)} images")
    
    return structure


def validate_config(config, structure):
    """验证配置与实际数据的匹配"""
    print(f"\n{'='*80}")
    print("🔍 配置验证")
    print(f"{'='*80}")
    
    errors = []
    warnings = []
    
    # 1. 验证 observation.state 配置
    print("\n1️⃣  验证 Observation State 配置:")
    
    obs_state = config['features']['observation']['state']['sub_state']
    
    for i, sub_state in enumerate(obs_state):
        names = sub_state.get('names', [])
        args = sub_state.get('args', {})
        
        # 检查 joint data
        if 'joint_type' in args:
            joint_type = args['joint_type']
            field_name = args.get('field_name', 'position')
            range_from = args.get('range_from', 0)
            range_to = args.get('range_to', 0)
            
            # 验证joint_type存在
            if joint_type not in structure['joint_state']:
                errors.append(
                    f"  ❌ sub_state[{i}]: joint_type '{joint_type}' 不存在\n"
                    f"     可用: {list(structure['joint_state'].keys())}"
                )
            else:
                # 验证field_name
                joint_info = structure['joint_state'][joint_type]
                if field_name not in joint_info['fields']:
                    errors.append(
                        f"  ❌ sub_state[{i}]: field '{field_name}' 不存在于 {joint_type}\n"
                        f"     可用: {joint_info['fields']}"
                    )
                else:
                    # 验证维度范围
                    actual_dim = joint_info['dimensions'].get(field_name, 0)
                    expected_dim = range_to - range_from
                    config_dim = len(names)
                    
                    if expected_dim != config_dim:
                        errors.append(
                            f"  ❌ sub_state[{i}]: 字段数量不匹配\n"
                            f"     配置: {config_dim} 个字段\n"
                            f"     range: {range_from}~{range_to} = {expected_dim}"
                        )
                    
                    if range_to > actual_dim:
                        errors.append(
                            f"  ❌ sub_state[{i}]: 维度超出范围\n"
                            f"     配置range_to: {range_to}\n"
                            f"     实际维度: {actual_dim}"
                        )
                    else:
                        print(f"  ✅ sub_state[{i}]: {joint_type}.{field_name}[{range_from}:{range_to}] - OK")
        
        # 检查 localization data
        elif args.get('data_type') == 'localization':
            loc_side = args.get('localization_side')
            field_names = args.get('field_names', [])
            
            if loc_side not in structure['localization']:
                errors.append(
                    f"  ❌ sub_state[{i}]: localization_side '{loc_side}' 不存在\n"
                    f"     可用: {list(structure['localization'].keys())}"
                )
            else:
                loc_info = structure['localization'][loc_side]
                for field in field_names:
                    if field not in loc_info['fields']:
                        errors.append(
                            f"  ❌ sub_state[{i}]: field '{field}' 不存在于 localization/{loc_side}\n"
                            f"     可用: {loc_info['fields']}"
                        )
                
                if len(field_names) != len(names):
                    errors.append(
                        f"  ❌ sub_state[{i}]: 字段数量不匹配\n"
                        f"     配置: {len(names)} 个字段名\n"
                        f"     field_names: {len(field_names)} 个"
                    )
                else:
                    print(f"  ✅ sub_state[{i}]: localization/{loc_side}.{field_names} - OK")
    
    # 2. 验证 observation.images 配置
    print("\n2️⃣  验证 Observation Images 配置:")
    
    obs_images = config['features']['observation']['images']
    
    for i, img_config in enumerate(obs_images):
        cam_name = img_config.get('cam_name')
        args = img_config.get('args', {})
        camera_folder = args.get('camera_folder')
        is_depth = args.get('is_depth', False)
        
        # 构建预期路径
        cam_type = 'depth' if is_depth else 'color'
        expected_path = f'{cam_type}/{camera_folder}'
        
        if expected_path not in structure['cameras']:
            errors.append(
                f"  ❌ image[{i}] '{cam_name}': 相机路径 '{expected_path}' 不存在\n"
                f"     可用: {list(structure['cameras'].keys())}"
            )
        else:
            print(f"  ✅ image[{i}] '{cam_name}': {expected_path} - OK")
    
    # 3. 验证 action 配置（应与observation一致）
    print("\n3️⃣  验证 Action 配置:")
    
    action_sub = config['features']['action']['sub_action']
    
    # 检查action与observation的sub_action数量是否一致
    if len(action_sub) != len(obs_state):
        warnings.append(
            f"  ⚠️  action.sub_action 数量 ({len(action_sub)}) != observation.state.sub_state 数量 ({len(obs_state)})"
        )
    else:
        print(f"  ✅ action.sub_action 数量与 observation 一致: {len(action_sub)}")
    
    # 输出结果
    print(f"\n{'='*80}")
    print("📊 验证结果")
    print(f"{'='*80}")
    
    if errors:
        print(f"\n❌ 发现 {len(errors)} 个错误:\n")
        for error in errors:
            print(error)
    else:
        print("\n✅ 未发现配置错误")
    
    if warnings:
        print(f"\n⚠️  发现 {len(warnings)} 个警告:\n")
        for warning in warnings:
            print(warning)
    else:
        print("\n✅ 未发现警告")
    
    return len(errors) == 0


def main():
    # 路径配置
    dataset_path = Path("/home/liu/program/robocoin-dataset/data/agilex_cobot_decoupled_magic:mult_sensor")
    config_path = Path("/home/liu/program/robocoin-dataset/scripts/format_converters/tolerobot/configs/converter_config_agilex_cobot_decoupled_magic_mult_sensor.yaml")
    
    print("=" * 80)
    print("🎯 Agilex Mult_Sensor 配置检测器")
    print("=" * 80)
    
    # 1. 加载配置
    print(f"\n📄 配置文件: {config_path.name}")
    config = load_config(config_path)
    
    # 2. 分析episode
    ep_dir = dataset_path / "episode1"
    if not ep_dir.exists():
        print(f"\n❌ Episode 不存在: {ep_dir}")
        return
    
    structure = analyze_episode_structure(ep_dir)
    
    # 3. 验证配置
    success = validate_config(config, structure)
    
    # 4. 总结
    print(f"\n{'='*80}")
    if success:
        print("🎉 配置检测通过！")
    else:
        print("❌ 配置检测失败，请修正上述错误")
    print(f"{'='*80}")
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())

