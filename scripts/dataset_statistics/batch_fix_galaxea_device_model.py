#!/usr/bin/env python3
"""
批量修改星海图数据集的device_model_annotation.yaml文件

将 device_model: galaxea_rl_lite 改为 device_model: galaxea_r1_lite
以匹配 converter_factory_config.yaml 中的配置

使用方法:
    python3 batch_fix_galaxea_device_model.py --dataset-path /path/to/galaxea/videos/train
    
    # 先预览（不实际修改）
    python3 batch_fix_galaxea_device_model.py --dataset-path /path/to/galaxea/videos/train --dry-run
"""

import argparse
import shutil
import sys
import yaml
from pathlib import Path


def fix_device_model_files(dataset_path: Path, dry_run: bool = False) -> tuple[int, int]:
    """
    批量修改device_model_annotation.yaml文件
    
    Args:
        dataset_path: 数据集根目录（通常是videos/train）
        dry_run: 如果为True，只预览不实际修改
        
    Returns:
        (成功修改数量, 失败数量)
    """
    if not dataset_path.exists():
        print(f"错误: 路径不存在: {dataset_path}")
        return 0, 0
    
    print(f"扫描目录: {dataset_path}")
    print(f"模式: {'预览模式（不会实际修改）' if dry_run else '修改模式'}")
    print("="*80)
    
    success_count = 0
    fail_count = 0
    
    # 遍历所有一级子目录
    for task_folder in dataset_path.iterdir():
        if not task_folder.is_dir():
            continue
        
        yaml_file = task_folder / "device_model_annotation.yaml"
        if not yaml_file.exists():
            continue
        
        try:
            # 读取YAML文件
            with open(yaml_file, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
            
            # 检查是否需要修改
            device_model = content.get('device_model')
            if device_model == 'galaxea_rl_lite':
                print(f"\n找到需要修改的文件: {task_folder.name}/device_model_annotation.yaml")
                print(f"  当前值: device_model: {device_model}")
                print(f"  修改为: device_model: galaxea_r1_lite")
                
                if not dry_run:
                    # 备份原文件
                    backup_file = yaml_file.with_suffix('.yaml.bak')
                    shutil.copy2(yaml_file, backup_file)
                    print(f"  已备份: {backup_file.name}")
                    
                    # 修改并写回
                    content['device_model'] = 'galaxea_r1_lite'
                    with open(yaml_file, 'w', encoding='utf-8') as f:
                        yaml.dump(content, f, allow_unicode=True, default_flow_style=False)
                    
                    # 验证修改
                    with open(yaml_file, 'r', encoding='utf-8') as f:
                        verify = yaml.safe_load(f)
                    if verify.get('device_model') == 'galaxea_r1_lite':
                        print(f"  ✓ 修改成功")
                        success_count += 1
                    else:
                        print(f"  ✗ 验证失败")
                        fail_count += 1
                else:
                    print(f"  [预览] 将会修改")
                    success_count += 1
                    
            elif device_model == 'galaxea_r1_lite':
                print(f"跳过（已是正确值）: {task_folder.name}/device_model_annotation.yaml")
            else:
                print(f"跳过（不同设备）: {task_folder.name}/device_model_annotation.yaml (device_model: {device_model})")
                
        except Exception as e:
            print(f"✗ 处理失败: {task_folder.name}/device_model_annotation.yaml")
            print(f"  错误: {e}")
            fail_count += 1
    
    return success_count, fail_count


def main():
    parser = argparse.ArgumentParser(
        description="批量修改星海图数据集的device_model_annotation.yaml文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 预览模式（推荐先执行）
  %(prog)s --dataset-path /mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train --dry-run
  
  # 实际修改
  %(prog)s --dataset-path /mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train
        """
    )
    
    parser.add_argument(
        '--dataset-path',
        type=str,
        required=True,
        help='数据集根目录路径（通常是videos/train目录）'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='预览模式，不实际修改文件'
    )
    
    args = parser.parse_args()
    
    dataset_path = Path(args.dataset_path)
    
    # 确认操作
    if not args.dry_run:
        print("\n" + "="*80)
        print("⚠️  警告：即将修改文件！")
        print("="*80)
        print(f"目标目录: {dataset_path}")
        print(f"操作内容: 将 device_model: galaxea_rl_lite 改为 device_model: galaxea_r1_lite")
        print(f"备份策略: 每个文件修改前会创建 .yaml.bak 备份")
        print("\n是否继续？(yes/no): ", end='')
        
        confirmation = input().strip().lower()
        if confirmation not in ['yes', 'y']:
            print("操作已取消")
            sys.exit(0)
        print()
    
    # 执行修改
    success, fail = fix_device_model_files(dataset_path, args.dry_run)
    
    # 打印总结
    print("\n" + "="*80)
    print("操作完成")
    print("="*80)
    if args.dry_run:
        print(f"预览结果: 将会修改 {success} 个文件")
    else:
        print(f"成功修改: {success} 个文件")
        print(f"失败: {fail} 个文件")
        if success > 0:
            print(f"\n提示: 备份文件已保存为 *.yaml.bak")
            print(f"如需恢复，可以运行:")
            print(f"  find {dataset_path} -name '*.yaml.bak' -exec sh -c 'mv \"$1\" \"${{1%.bak}}\"' _ {{}} \\;")
    print("="*80)


if __name__ == '__main__':
    main()
