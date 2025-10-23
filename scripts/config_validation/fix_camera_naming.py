#!/usr/bin/env python3
"""
批量修复配置文件中的相机命名规范

规范要求：
1. head -> high
2. 格式: cam_{position}_rgb 或 cam_{position}_{type}_rgb
3. 参考realman的标准命名
"""

import yaml
from pathlib import Path
import shutil
from datetime import datetime

# 标准命名映射
STANDARD_MAPPING = {
    # Head/High cameras
    'head_color': 'cam_high_rgb',
    'cam_head': 'cam_high_rgb',
    'cam_head_rgb': 'cam_high_rgb',
    'camera_head_rgb': 'cam_high_rgb',
    'camera_front_head_rgb': 'cam_high_rgb',
    'cam_front': 'cam_high_rgb',
    'cam_front_rgb': 'cam_high_rgb',
    'camera_front_rgb': 'cam_high_rgb',
    
    # Wrist cameras
    'hand_left_color': 'cam_left_wrist_rgb',
    'hand_right_color': 'cam_right_wrist_rgb',
    'camera_left_wrist': 'cam_left_wrist_rgb',
    'camera_right_wrist': 'cam_right_wrist_rgb',
    'camera_left_wrist_rgb': 'cam_left_wrist_rgb',
    'camera_right_wrist_rgb': 'cam_right_wrist_rgb',
    'cam_left_wrist': 'cam_left_wrist_rgb',
    'cam_right_wrist': 'cam_right_wrist_rgb',
    'color_left_wrist': 'cam_left_wrist_rgb',
    'color_right_wrist': 'cam_right_wrist_rgb',
    'camera_left_rgb': 'cam_left_wrist_rgb',
    'camera_right_rgb': 'cam_right_wrist_rgb',
    
    # Fisheye cameras
    'head_center_fisheye_color': 'cam_high_center_fisheye_rgb',
    'back_left_fisheye_color': 'cam_back_left_fisheye_rgb',
    'back_right_fisheye_color': 'cam_back_right_fisheye_rgb',
    'head_left_fisheye_color': 'cam_high_left_fisheye_rgb',
    'head_right_fisheye_color': 'cam_high_right_fisheye_rgb',
}

def fix_camera_names_in_file(file_path: Path, dry_run: bool = False):
    """修复单个配置文件中的相机命名"""
    with open(file_path) as f:
        content = f.read()
    
    original_content = content
    changes = []
    
    # 逐行替换
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'cam_name:' in line and not line.strip().startswith('#'):
            for old_name, new_name in STANDARD_MAPPING.items():
                old_pattern = f'cam_name: {old_name}'
                new_pattern = f'cam_name: {new_name}'
                
                if old_pattern in line:
                    lines[i] = line.replace(old_pattern, new_pattern)
                    changes.append({
                        'line': i + 1,
                        'old': old_name,
                        'new': new_name
                    })
                    break
    
    if not changes:
        return None
    
    new_content = '\n'.join(lines)
    
    if not dry_run:
        # 备份原文件
        backup_path = file_path.with_suffix('.yaml.bak')
        shutil.copy2(file_path, backup_path)
        
        # 写入新内容
        with open(file_path, 'w') as f:
            f.write(new_content)
    
    return changes

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='批量修复相机命名规范')
    parser.add_argument('--dry-run', action='store_true', help='只显示会修改什么，不实际修改')
    parser.add_argument('--config-dir', type=Path, 
                        default=Path('scripts/format_converters/tolerobot/configs'),
                        help='配置文件目录')
    
    args = parser.parse_args()
    
    config_dir = args.config_dir
    if not config_dir.exists():
        print(f"错误：配置目录不存在: {config_dir}")
        return 1
    
    print("="*80)
    print("相机命名规范批量修复工具")
    print("="*80)
    if args.dry_run:
        print("🔍 DRY RUN模式 - 只预览，不实际修改")
    print()
    
    total_files = 0
    total_changes = 0
    
    for config_file in sorted(config_dir.glob('converter_config_*.yaml')):
        if config_file.name == 'converter_factory_config.yaml':
            continue
        
        changes = fix_camera_names_in_file(config_file, dry_run=args.dry_run)
        
        if changes:
            total_files += 1
            total_changes += len(changes)
            
            print(f"📄 {config_file.name}")
            for change in changes:
                print(f"   Line {change['line']}: {change['old']} → {change['new']}")
            print()
    
    print("="*80)
    print(f"总计: {total_files} 个文件, {total_changes} 处修改")
    if not args.dry_run:
        print("✅ 修改已完成，原文件已备份为 .yaml.bak")
    else:
        print("ℹ️  使用 --dry-run=false 执行实际修改")
    print("="*80)
    
    return 0

if __name__ == '__main__':
    exit(main())

