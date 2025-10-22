#!/usr/bin/env python3
"""
Ruantong A2D 配置验证器
验证三个版本的配置是否与实际数据匹配
"""

import h5py
import yaml
import numpy as np
from pathlib import Path


def load_config(config_path):
    """加载配置文件"""
    with open(config_path) as f:
        return yaml.safe_load(f)


def validate_gt02(h5_path, config):
    """验证 GT02 配置"""
    print(f"\n{'='*80}")
    print("📂 GT02 验证")
    print(f"{'='*80}")
    
    errors = []
    warnings = []
    
    with h5py.File(h5_path, 'r') as f:
        # 1. 验证 state sub_states
        print("\n1️⃣  验证 State 配置:")
        sub_states = config['features']['observation']['state']['sub_state']
        
        total_dims = 0
        for i, sub_state in enumerate(sub_states):
            names = sub_state.get('names', [])
            args = sub_state.get('args', {})
            h5_path_str = args.get('h5_path')
            range_from = args.get('range_from', 0)
            range_to = args.get('range_to', 0)
            
            # 检查 H5 路径存在
            if h5_path_str not in f:
                errors.append(f"  ❌ sub_state[{i}]: H5路径不存在: {h5_path_str}")
                continue
            
            dataset = f[h5_path_str]
            
            # 检查维度
            expected_dims = range_to - range_from
            actual_dims = len(names)
            
            if expected_dims != actual_dims:
                errors.append(
                    f"  ❌ sub_state[{i}]: 维度不匹配\n"
                    f"     range: [{range_from}:{range_to}] = {expected_dims}\n"
                    f"     names: {actual_dims}"
                )
            
            # 检查是否超出数据集范围
            if range_to > dataset.shape[1]:
                errors.append(
                    f"  ❌ sub_state[{i}]: range_to={range_to} 超出数据集维度 {dataset.shape[1]}"
                )
            else:
                # 检查数据质量
                data_slice = dataset[:, range_from:range_to]
                for j in range(data_slice.shape[1]):
                    col = data_slice[:, j]
                    if np.isnan(col).all():
                        warnings.append(
                            f"  ⚠️  sub_state[{i}], dim[{j}] ({names[j] if j < len(names) else 'unknown'}): 全是NaN"
                        )
                
                print(f"  ✅ sub_state[{i}]: {h5_path_str}[{range_from}:{range_to}] - {len(names)}维")
                total_dims += len(names)
        
        print(f"\n  📊 State 总维度: {total_dims}")
    
    return errors, warnings


def validate_default_gt01(h5_path, config, version_name):
    """验证 default/gt01 配置"""
    print(f"\n{'='*80}")
    print(f"📂 {version_name} 验证")
    print(f"{'='*80}")
    
    errors = []
    warnings = []
    
    with h5py.File(h5_path, 'r') as f:
        # 验证 state sub_states
        print("\n1️⃣  验证 State 配置:")
        sub_states = config['features']['observation']['state']['sub_state']
        
        total_dims = 0
        for i, sub_state in enumerate(sub_states):
            names = sub_state.get('names', [])
            args = sub_state.get('args', {})
            h5_path_str = args.get('h5_path')
            range_from = args.get('range_from', 0)
            range_to = args.get('range_to', 0)
            array_index = args.get('array_index')
            
            # 检查 H5 路径存在
            if h5_path_str not in f:
                errors.append(f"  ❌ sub_state[{i}]: H5路径不存在: {h5_path_str}")
                continue
            
            dataset = f[h5_path_str]
            
            # 检查维度
            expected_dims = range_to - range_from
            actual_dims = len(names)
            
            if expected_dims != actual_dims:
                errors.append(
                    f"  ❌ sub_state[{i}]: 维度不匹配\n"
                    f"     range: [{range_from}:{range_to}] = {expected_dims}\n"
                    f"     names: {actual_dims}"
                )
            
            # 检查 array_index
            if array_index is not None:
                if len(dataset.shape) < 3:
                    errors.append(
                        f"  ❌ sub_state[{i}]: 指定了array_index={array_index}，但数据集维度不足: {dataset.shape}"
                    )
                elif array_index >= dataset.shape[1]:
                    errors.append(
                        f"  ❌ sub_state[{i}]: array_index={array_index} 超出范围 {dataset.shape[1]}"
                    )
                else:
                    print(f"  ✅ sub_state[{i}]: {h5_path_str}[{array_index}, {range_from}:{range_to}] - {len(names)}维")
            else:
                if range_to > dataset.shape[1]:
                    errors.append(
                        f"  ❌ sub_state[{i}]: range_to={range_to} 超出数据集维度 {dataset.shape[1]}"
                    )
                else:
                    print(f"  ✅ sub_state[{i}]: {h5_path_str}[{range_from}:{range_to}] - {len(names)}维")
            
            total_dims += len(names)
        
        print(f"\n  📊 State 总维度: {total_dims}")
    
    return errors, warnings


def main():
    print("=" * 80)
    print("🔍 Ruantong A2D 配置验证")
    print("=" * 80)
    
    # 配置路径
    base_dir = Path("/home/liu/program/robocoin-dataset")
    
    versions = [
        {
            "name": "default",
            "h5_path": base_dir / "data/ruantong_a2d:default_version/138914/aligned_joints.h5",
            "config_path": base_dir / "scripts/format_converters/tolerobot/configs/converter_config_ruantong.yaml",
            "validator": validate_default_gt01
        },
        {
            "name": "gt01_no_depth",
            "h5_path": base_dir / "data/ruantong_a2d:gt01_no_depth/27783/aligned_joints.h5",
            "config_path": base_dir / "scripts/format_converters/tolerobot/configs/converter_config_ruantong_gt01_no_depth.yaml",
            "validator": validate_default_gt01
        },
        {
            "name": "gt02_new",
            "h5_path": base_dir / "data/ruantong_a2d:gt02_new_version/16123/aligned_joints.h5",
            "config_path": base_dir / "scripts/format_converters/tolerobot/configs/converter_config_ruantong_gt02_new.yaml",
            "validator": validate_gt02
        },
    ]
    
    all_errors = []
    all_warnings = []
    
    for version_info in versions:
        name = version_info['name']
        h5_path = version_info['h5_path']
        config_path = version_info['config_path']
        validator = version_info['validator']
        
        if not h5_path.exists():
            print(f"\n⚠️  {name}: H5文件不存在: {h5_path}")
            continue
        
        if not config_path.exists():
            print(f"\n⚠️  {name}: 配置文件不存在: {config_path}")
            continue
        
        # 加载配置
        config = load_config(config_path)
        
        # 验证
        if validator == validate_default_gt01:
            errors, warnings = validator(h5_path, config, name)
        else:
            errors, warnings = validator(h5_path, config)
        
        all_errors.extend([(name, e) for e in errors])
        all_warnings.extend([(name, w) for w in warnings])
    
    # 输出汇总
    print("\n" + "=" * 80)
    print("📊 验证结果汇总")
    print("=" * 80)
    
    if all_errors:
        print(f"\n❌ 发现 {len(all_errors)} 个错误:")
        for version, error in all_errors:
            print(f"\n[{version}]")
            print(error)
    else:
        print("\n✅ 未发现错误")
    
    if all_warnings:
        print(f"\n⚠️  发现 {len(all_warnings)} 个警告:")
        for version, warning in all_warnings:
            print(f"\n[{version}]")
            print(warning)
    else:
        print("\n✅ 未发现警告")
    
    print("\n" + "=" * 80)
    if not all_errors:
        print("🎉 配置验证通过！")
    else:
        print("❌ 配置验证失败，请修正上述错误")
    print("=" * 80)
    
    return 0 if not all_errors else 1


if __name__ == "__main__":
    exit(main())

