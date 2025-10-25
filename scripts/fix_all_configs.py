#!/usr/bin/env python3
"""
配置文件批量修正脚本
自动修正所有命名和转换函数问题
"""

import yaml
from pathlib import Path


def fix_config_file(config_path, fixes):
    """应用修正到配置文件"""
    print(f"\n修正: {config_path.name}")
    
    with open(config_path) as f:
        content = f.read()
    
    # 应用所有替换
    for old, new in fixes:
        if old in content:
            content = content.replace(old, new)
            print(f"  ✓ {old} → {new}")
    
    with open(config_path, 'w') as f:
        f.write(content)


def main():
    print("=" * 80)
    print("🔧 批量修正配置文件")
    print("=" * 80)
    
    base_dir = Path("/home/liu/program/robocoin-dataset/scripts/format_converters/tolerobot/configs")
    
    # 1. 修正 Realman: gripper 添加 _rad 后缀
    print("\n1️⃣  Realman: gripper 添加 _rad 后缀")
    fix_config_file(
        base_dir / "converter_config_realman_rmc_aidal.yaml",
        [
            ("- right_gripper_open\n", "- right_gripper_open_rad\n"),
        ]
    )
    
    # 2. 修正 Zhipingfang: gripper_pos → gripper_open_rad
    print("\n2️⃣  Zhipingfang (7个版本): gripper 命名修正")
    zhipingfang_configs = [
        "converter_config_zhipingfang_dual_arm_no_pose.yaml",
        "converter_config_zhipingfang_dual_arm_no_pose_compressed_video.yaml",
        "converter_config_zhipingfang_dual_arm_with_pose.yaml",
        "converter_config_zhipingfang_dual_arm_with_pose_compressed_video.yaml",
        "converter_config_zhipingfang_dual_arm_with_pose_no_left_chest_cam.yaml",
        "converter_config_zhipingfang_left_arm_with_pose.yaml",
        "converter_config_zhipingfang_right_arm_with_pose.yaml",
    ]
    
    for config_file in zhipingfang_configs:
        fix_config_file(
            base_dir / config_file,
            [
                ("- left_gripper_pos\n", "- left_gripper_open_rad\n"),
                ("- right_gripper_pos\n", "- right_gripper_open_rad\n"),
            ]
        )
    
    # 3. 修正 Ruantong default/gt01: 添加转换函数
    print("\n3️⃣  Ruantong (default/gt01): 添加转换函数")
    
    # 这个需要手动处理，因为要在特定位置插入 convert_func
    # 我们生成修正后的配置
    
    for config_name in ["converter_config_ruantong.yaml", "converter_config_ruantong_gt01_no_depth.yaml"]:
        config_path = base_dir / config_name
        print(f"\n修正: {config_name}")
        
        with open(config_path) as f:
            lines = f.readlines()
        
        new_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]
            new_lines.append(line)
            
            # 检查是否是四元数字段的 args 行
            if 'array_index' in line and i + 1 < len(lines):
                # 检查下一行是否是 names 行
                next_line_idx = i + 1
                while next_line_idx < len(lines) and lines[next_line_idx].strip() == '':
                    new_lines.append(lines[next_line_idx])
                    next_line_idx += 1
                    i += 1
                
                if next_line_idx < len(lines) and 'quat' in lines[next_line_idx]:
                    # 找到缩进
                    indent = len(line) - len(line.lstrip())
                    # 添加 convert_func
                    new_lines.append(' ' * indent + 'convert_func: quat_xyzw_2_euler_xyz\n')
                    print(f"  ✓ 添加四元数转换 (行 {i+1})")
            
            # 检查是否是 effector _deg 字段
            if 'effector_open_deg' in line:
                # 检查下一行是否已有 args
                next_idx = i + 1
                while next_idx < len(lines) and lines[next_idx].strip() == '':
                    next_idx += 1
                
                if next_idx < len(lines) and 'args:' in lines[next_idx]:
                    # 找到 args 块的结束
                    args_indent = len(lines[next_idx]) - len(lines[next_idx].lstrip())
                    search_idx = next_idx + 1
                    while search_idx < len(lines):
                        search_line = lines[search_idx]
                        if search_line.strip() and not search_line.startswith(' ' * (args_indent + 2)):
                            # args 块结束
                            break
                        search_idx += 1
                    
                    # 在 args 块后添加 convert_func
                    # 但是先检查是否已经有了
                    has_convert = False
                    for check_idx in range(i, min(search_idx, len(lines))):
                        if 'convert_func' in lines[check_idx]:
                            has_convert = True
                            break
                    
                    if not has_convert:
                        # 计算缩进（与 names 同级）
                        name_indent = len(line) - len(line.lstrip())
                        # 需要在当前位置之后插入，但要先遍历完 args
                        # 这个逻辑比较复杂，我们用简单的字符串替换
                        pass
            
            i += 1
        
        # 简化方案：使用字符串替换
        with open(config_path) as f:
            content = f.read()
        
        # 为四元数字段添加转换函数
        # 模式：args 块后面没有 convert_func 的四元数字段
        import re
        
        # 查找所有四元数字段块
        quat_pattern = r'(- names:\s*\n\s*- \w+_quat_x\s*\n\s*- \w+_quat_y\s*\n\s*- \w+_quat_z\s*\n\s*- \w+_quat_w\s*\n\s*args:\s*\n(?:\s*\w+:.*\n)*)'
        
        def add_convert_func(match):
            block = match.group(1)
            if 'convert_func' not in block:
                # 获取缩进
                lines = block.split('\n')
                for line in lines:
                    if line.strip().startswith('- names:'):
                        indent = len(line) - len(line.lstrip())
                        break
                return block + ' ' * indent + 'convert_func: quat_xyzw_2_euler_xyz\n'
            return block
        
        content = re.sub(quat_pattern, add_convert_func, content)
        
        # 为 _deg 字段添加转换函数
        deg_pattern = r'(- names:\s*\n(?:\s*- \w+_deg\s*\n)+\s*args:\s*\n(?:\s*\w+:.*\n)*)'
        
        def add_degree2rad(match):
            block = match.group(1)
            if 'convert_func' not in block:
                lines = block.split('\n')
                for line in lines:
                    if line.strip().startswith('- names:'):
                        indent = len(line) - len(line.lstrip())
                        break
                return block + ' ' * indent + 'convert_func: degree2rad\n'
            return block
        
        content = re.sub(deg_pattern, add_degree2rad, content)
        
        with open(config_path, 'w') as f:
            f.write(content)
        
        print(f"  ✓ 已添加所有转换函数")
    
    # 4. 修正 Ruantong gt02: 添加 degree2rad
    print("\n4️⃣  Ruantong (gt02): 添加 degree2rad")
    
    config_path = base_dir / "converter_config_ruantong_gt02_new.yaml"
    with open(config_path) as f:
        content = f.read()
    
    # 为 gripper _deg 字段添加转换函数
    import re
    deg_pattern = r'(- names:\s*\n(?:\s*- gripper_\w+_open_deg\s*\n)+\s*args:\s*\n(?:\s*\w+:.*\n)*)'
    
    def add_degree2rad(match):
        block = match.group(1)
        if 'convert_func' not in block:
            lines = block.split('\n')
            for line in lines:
                if line.strip().startswith('- names:'):
                    indent = len(line) - len(line.lstrip())
                    break
            return block + ' ' * indent + 'convert_func: degree2rad\n'
        return block
    
    content = re.sub(deg_pattern, add_degree2rad, content)
    
    with open(config_path, 'w') as f:
        f.write(content)
    
    print(f"  ✓ 已添加 degree2rad 转换")
    
    # 5. 修正 MMK2: 添加四元数转换
    print("\n5️⃣  MMK2: 添加四元数转换")
    
    config_path = base_dir / "converter_config_discover_robotics_aitbot_mmk2_third_view.yaml"
    with open(config_path) as f:
        content = f.read()
    
    quat_pattern = r'(- names:\s*\n\s*- \w+_eef_quat_x\s*\n\s*- \w+_eef_quat_y\s*\n\s*- \w+_eef_quat_z\s*\n\s*- \w+_eef_quat_w\s*\n\s*args:\s*\n(?:\s*\w+:.*\n)*)'
    
    def add_convert_func_mmk2(match):
        block = match.group(1)
        if 'convert_func' not in block:
            lines = block.split('\n')
            for line in lines:
                if line.strip().startswith('- names:'):
                    indent = len(line) - len(line.lstrip())
                    break
            return block + ' ' * indent + 'convert_func: quat_xyzw_2_euler_xyz\n'
        return block
    
    content = re.sub(quat_pattern, add_convert_func_mmk2, content)
    
    with open(config_path, 'w') as f:
        f.write(content)
    
    print(f"  ✓ 已添加四元数转换")
    
    # 6. Leju: IMU 四元数 - 暂时移除（因为可能不需要）
    print("\n6️⃣  Leju: IMU 四元数字段暂不处理（保留原样）")
    
    # 7. Agilex Masterpuppet 需要重新设计字段名 - 稍后处理
    print("\n7️⃣  Agilex Masterpuppet: 需要手动重新设计字段名（暂跳过）")
    
    print("\n" + "=" * 80)
    print("✅ 批量修正完成")
    print("=" * 80)


if __name__ == "__main__":
    main()

