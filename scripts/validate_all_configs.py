#!/usr/bin/env python3
"""
配置文件规范性检查器
检查所有配置文件的命名规范和单位转换
"""

import re
import yaml
from pathlib import Path
from collections import defaultdict


def check_field_naming(field_name):
    """检查字段命名规范"""
    issues = []
    
    # 检查1: Joint索引应该从1开始（不能是_0）
    if re.search(r'joint_0(?:_|$)', field_name):
        issues.append(f"❌ Joint索引从0开始: {field_name} (应该从1开始)")
    
    # 检查2: 单位后缀检查
    # 允许的后缀: _rad, _m, _rad_s, _m_s, _m_s2, _nm (Newton-meter for effort)
    # 不允许: _deg, _pct, 无后缀（对于数值字段）
    
    # 如果包含数值相关的关键词，必须有单位
    if any(keyword in field_name for keyword in [
        'joint', 'gripper', 'position', 'pos', 'velocity', 'vel', 
        'rotation', 'rot', 'orientation', 'angle', 'effort', 'eff',
        'accel', 'gyro', 'distance', 'wheel', 'torso', 'chassis'
    ]):
        # 检查是否有允许的单位后缀
        allowed_suffixes = [
            '_rad', '_m', '_rad_s', '_m_s', '_m_s2', '_nm',
            '_deg',  # degree 暂时允许，但必须有转换函数
        ]
        
        has_unit_suffix = any(field_name.endswith(suffix) for suffix in allowed_suffixes)
        
        # 特殊情况：gripper_open, gripper_position 等需要单位
        if not has_unit_suffix:
            # 排除一些特殊字段（如 camera 名称）
            if not any(exclude in field_name for exclude in ['cam_', 'camera_', 'image_']):
                issues.append(f"⚠️  缺少单位后缀: {field_name} (应该是 _rad 或 _m)")
    
    # 检查3: degree 单位应该转换为 rad
    if '_deg' in field_name:
        issues.append(f"⚠️  使用 _deg 后缀: {field_name} (需要 convert_func: degree2rad)")
    
    # 检查4: 百分比单位应该转换
    if '_pct' in field_name or '_percent' in field_name:
        issues.append(f"⚠️  使用 _pct 后缀: {field_name} (需要转换为 _rad 或 _m)")
    
    return issues


def check_convert_func(field_names, convert_func):
    """检查转换函数是否与字段名匹配"""
    issues = []
    
    # 如果字段包含 _deg，必须有 degree2rad 转换
    has_deg = any('_deg' in name for name in field_names)
    if has_deg and convert_func != 'degree2rad':
        issues.append(f"❌ 字段包含 _deg 但缺少 degree2rad 转换: {field_names}")
    
    # 如果字段包含 quat，必须有 quat_xyzw_2_euler_xyz 转换
    has_quat = any('quat' in name for name in field_names)
    if has_quat and convert_func != 'quat_xyzw_2_euler_xyz':
        issues.append(f"❌ 字段包含 quat 但缺少转换: {field_names}")
    
    # 如果有 degree2rad，字段应该以 _rad 结尾（转换后）
    if convert_func == 'degree2rad':
        if not all(name.endswith('_rad') for name in field_names):
            issues.append(f"⚠️  degree2rad 转换但字段名不是 _rad: {field_names}")
    
    return issues


def check_sub_state_or_action(sub_items, section_name):
    """检查 sub_state 或 sub_action 配置"""
    issues = []
    
    for idx, item in enumerate(sub_items):
        names = item.get('names', [])
        convert_func = item.get('convert_func')
        
        # 检查每个字段名
        for field_name in names:
            field_issues = check_field_naming(field_name)
            if field_issues:
                issues.append(f"{section_name}[{idx}]: {', '.join(field_issues)}")
        
        # 检查转换函数
        if convert_func:
            func_issues = check_convert_func(names, convert_func)
            if func_issues:
                issues.extend([f"{section_name}[{idx}]: {issue}" for issue in func_issues])
        else:
            # 没有转换函数，但可能需要
            func_issues = check_convert_func(names, None)
            if func_issues:
                issues.extend([f"{section_name}[{idx}]: {issue}" for issue in func_issues])
    
    return issues


def validate_config_file(config_path):
    """验证单个配置文件"""
    print(f"\n{'='*80}")
    print(f"📄 {config_path.name}")
    print(f"{'='*80}")
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    all_issues = []
    
    # 检查 observation.state
    if 'features' in config and 'observation' in config['features']:
        observation = config['features']['observation']
        
        if 'state' in observation and 'sub_state' in observation['state']:
            issues = check_sub_state_or_action(
                observation['state']['sub_state'],
                'observation.state.sub_state'
            )
            all_issues.extend(issues)
    
    # 检查 action.sub_action
    if 'features' in config and 'action' in config['features']:
        action = config['features']['action']
        
        if 'sub_action' in action:
            issues = check_sub_state_or_action(
                action['sub_action'],
                'action.sub_action'
            )
            all_issues.extend(issues)
    
    # 输出结果
    if all_issues:
        print(f"\n❌ 发现 {len(all_issues)} 个问题:")
        for issue in all_issues:
            print(f"  {issue}")
        return False
    else:
        print("\n✅ 通过所有检查")
        return True


def main():
    print("=" * 80)
    print("🔍 配置文件规范性批量检查")
    print("=" * 80)
    
    base_dir = Path("/home/liu/program/robocoin-dataset/scripts/format_converters/tolerobot/configs")
    
    # 需要检查的配置文件
    config_files = [
        # Galaxea
        "converter_config_galaxea_r1_lite_h5_mp4.yaml",
        "converter_config_galaxea_r1_lite.yaml",
        
        # Agilex
        "converter_config_agilex_cobot.yaml",
        "converter_config_agilex_cobot_decoupled_magic_masterpuppet.yaml",
        "converter_config_agilex_cobot_decoupled_magic_mult_sensor.yaml",
        
        # MMK2
        "converter_config_discover_robotics_aitbot_mmk2_third_view.yaml",
        
        # Leju
        "converter_config_leju_waibu.yaml",
        
        # Realman
        "converter_config_realman_rmc_aidal.yaml",
        "converter_config_realman_rmc_aidal_mcap.yaml",
        
        # Yinhe
        "converter_config_yinhe.yaml",
        
        # Zhipingfang
        "converter_config_zhipingfang_dual_arm_no_pose.yaml",
        "converter_config_zhipingfang_dual_arm_no_pose_compressed_video.yaml",
        "converter_config_zhipingfang_dual_arm_with_pose.yaml",
        "converter_config_zhipingfang_dual_arm_with_pose_compressed_video.yaml",
        "converter_config_zhipingfang_dual_arm_with_pose_no_left_chest_cam.yaml",
        "converter_config_zhipingfang_left_arm_with_pose.yaml",
        "converter_config_zhipingfang_right_arm_with_pose.yaml",
        
        # Ruantong
        "converter_config_ruantong.yaml",
        "converter_config_ruantong_gt01_no_depth.yaml",
        "converter_config_ruantong_gt02_new.yaml",
    ]
    
    results = {}
    
    for config_file in config_files:
        config_path = base_dir / config_file
        if config_path.exists():
            passed = validate_config_file(config_path)
            results[config_file] = passed
        else:
            print(f"\n⚠️  配置文件不存在: {config_file}")
            results[config_file] = None
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("📊 检查结果汇总")
    print("=" * 80)
    
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    missing = sum(1 for v in results.values() if v is None)
    
    print(f"\n✅ 通过: {passed}/{len(config_files)}")
    print(f"❌ 失败: {failed}/{len(config_files)}")
    print(f"⚠️  缺失: {missing}/{len(config_files)}")
    
    if failed > 0:
        print(f"\n❌ 失败的配置文件:")
        for name, result in results.items():
            if result is False:
                print(f"  - {name}")
    
    print("\n" + "=" * 80)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())

