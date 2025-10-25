#!/usr/bin/env python3
"""
快速修复 Agilex Masterpuppet 配置文件
将 eef_pose 字段拆分为位置(3维)和旋转(3维，转换自四元数)
"""

import re
from pathlib import Path

config_path = Path("/home/liu/program/robocoin-dataset/scripts/format_converters/tolerobot/configs/converter_config_agilex_cobot_decoupled_magic_masterpuppet.yaml")

print("=" * 80)
print("🔧 修复 Agilex Masterpuppet 配置")
print("=" * 80)

with open(config_path) as f:
    lines = f.readlines()

new_lines = []
i = 0
replaced_count = 0

while i < len(lines):
    line = lines[i]
    
    # 检查是否是 puppet_left_eef_pose 或 puppet_right_eef_pose 块的开始
    if 'puppet_left_eef_pose_1' in line or 'puppet_right_eef_pose_1' in line:
        arm = 'left' if 'left' in line else 'right'
        range_from = 0 if arm == 'left' else 7
        
        print(f"\n✓ 修复 puppet_{arm}_eef_pose")
        
        # 找到这个块的缩进
        indent = len(line) - len(line.lstrip())
        base_indent = ' ' * indent
        
        # 跳过当前的7个字段名
        i += 1
        while i < len(lines) and (lines[i].strip().startswith('- puppet_') or lines[i].strip() == ''):
            i += 1
        
        # 找到 args 块并跳过
        if i < len(lines) and 'args:' in lines[i]:
            i += 1
            while i < len(lines) and (lines[i].startswith(' ' * (indent + 2)) or lines[i].strip() == ''):
                i += 1
        
        # 插入新的配置
        # 位置 (3维)
        new_lines.append(f"{base_indent}# {arm.capitalize()}臂末端执行器位置 (3维)\n")
        new_lines.append(f"{base_indent}- names:\n")
        new_lines.append(f"{base_indent}    - puppet_{arm}_eef_pos_x_m\n")
        new_lines.append(f"{base_indent}    - puppet_{arm}_eef_pos_y_m\n")
        new_lines.append(f"{base_indent}    - puppet_{arm}_eef_pos_z_m\n")
        new_lines.append(f"{base_indent}  args:\n")
        new_lines.append(f"{base_indent}    h5_path: puppet/eef_pose\n")
        new_lines.append(f"{base_indent}    range_from: {range_from}\n")
        new_lines.append(f"{base_indent}    range_to: {range_from + 3}\n")
        new_lines.append(f"\n")
        
        # 姿态 (4维四元数 → 3维欧拉角)
        new_lines.append(f"{base_indent}# {arm.capitalize()}臂末端执行器姿态 (四元数→欧拉角)\n")
        new_lines.append(f"{base_indent}- names:\n")
        new_lines.append(f"{base_indent}    - puppet_{arm}_eef_rot_euler_x_rad\n")
        new_lines.append(f"{base_indent}    - puppet_{arm}_eef_rot_euler_y_rad\n")
        new_lines.append(f"{base_indent}    - puppet_{arm}_eef_rot_euler_z_rad\n")
        new_lines.append(f"{base_indent}  args:\n")
        new_lines.append(f"{base_indent}    h5_path: puppet/eef_pose\n")
        new_lines.append(f"{base_indent}    range_from: {range_from + 3}\n")
        new_lines.append(f"{base_indent}    range_to: {range_from + 7}\n")
        new_lines.append(f"{base_indent}  convert_func: quat_xyzw_2_euler_xyz\n")
        new_lines.append(f"\n")
        
        replaced_count += 1
        continue
    
    new_lines.append(line)
    i += 1

# 写回文件
with open(config_path, 'w') as f:
    f.writelines(new_lines)

print(f"\n✅ 修复完成!")
print(f"   - 替换了 {replaced_count} 处末端执行器配置")
print(f"   - 位置字段: *_eef_pos_x/y/z_m (3维)")
print(f"   - 姿态字段: *_eef_rot_euler_x/y/z_rad (3维，从四元数转换)")

print("\n" + "=" * 80)


