#!/usr/bin/env python3
"""
通用的parquet文件NaN修复脚本
支持命令行参数指定数据集路径和episode编号

用法:
    python scripts/fix_episode_nan.py <dataset_path> <episode_number>

例子:
    python scripts/fix_episode_nan.py /mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_put_the_pen_into_the_pen_holder 59
"""

import argparse
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


def count_nan_in_array_column(df, col_name):
    """统计数组列中的NaN数量"""
    nan_count = 0
    nan_rows = []
    for idx, val in enumerate(df[col_name]):
        if isinstance(val, (list, np.ndarray)):
            arr = np.array(val)
            if np.any(np.isnan(arr)):
                nan_count += np.sum(np.isnan(arr))
                nan_rows.append(idx)
    return nan_count, nan_rows


def fix_nan_in_dataframe(df, col_name):
    """修复DataFrame中指定列的NaN值"""
    fixed_data = []
    for val in df[col_name]:
        if isinstance(val, (list, np.ndarray)):
            arr = np.array(val, dtype=float)
            if np.any(np.isnan(arr)):
                arr = np.nan_to_num(arr, nan=0.0)
            fixed_data.append(arr.tolist())
        else:
            fixed_data.append(val)
    return fixed_data


def process_parquet_file(file_path: Path):
    """处理单个parquet文件"""
    print(f"\n{'='*80}")
    print(f"File: {file_path}")
    print(f"{'='*80}")
    
    # 读取文件 - 优先使用pandas，因为它对某些parquet文件的兼容性更好
    try:
        df = pd.read_parquet(file_path)
    except Exception as e:
        print(f"  ❌ Error reading file with pandas: {e}")
        # 如果pandas失败，尝试pyarrow
        try:
            table = pq.read_table(file_path)
            df = table.to_pandas()
        except Exception as e2:
            print(f"  ❌ Error reading file with pyarrow: {e2}")
            return False
    
    print(f"Rows: {len(df)}, Columns: {list(df.columns)}")
    
    # 检查NaN
    has_nan = False
    columns_to_fix = []
    
    for col in df.columns:
        nan_count, nan_rows = count_nan_in_array_column(df, col)
        if nan_count > 0:
            has_nan = True
            columns_to_fix.append(col)
            print(f"  ⚠️ {col}: {nan_count} NaN elements in {len(nan_rows)} rows")
    
    if not has_nan:
        print("  ✅ No NaN found")
        return True
    
    # 创建备份
    backup_path = file_path.with_suffix('.parquet.backup')
    if not backup_path.exists():
        print(f"  💾 Creating backup: {backup_path.name}")
        shutil.copy2(file_path, backup_path)
    else:
        print(f"  📦 Backup already exists: {backup_path.name}")
    
    # 修复NaN
    print(f"  🔧 Fixing NaN values...")
    for col in columns_to_fix:
        df[col] = fix_nan_in_dataframe(df, col)
    
    # 保存修复后的文件
    df.to_parquet(file_path, index=False)
    print(f"  ✅ Fixed all NaN values")
    
    # 验证
    table_verify = pq.read_table(file_path)
    df_verify = table_verify.to_pandas()
    
    verification_passed = True
    for col in columns_to_fix:
        nan_count, _ = count_nan_in_array_column(df_verify, col)
        if nan_count > 0:
            print(f"  ❌ Verification failed: {col} still has {nan_count} NaN")
            verification_passed = False
    
    if verification_passed:
        print(f"  ✓ Verification passed")
    
    return verification_passed


def main():
    parser = argparse.ArgumentParser(
        description='修复指定数据集中特定episode的NaN值',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/fix_episode_nan.py /mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_put_the_pen_into_the_pen_holder 59
  python scripts/fix_episode_nan.py /path/to/dataset 106
        """
    )
    
    parser.add_argument(
        'dataset_path',
        type=str,
        help='数据集的完整路径'
    )
    
    parser.add_argument(
        'episode_number',
        type=int,
        help='要修复的episode编号'
    )
    
    parser.add_argument(
        '--data-dirs',
        nargs='+',
        default=['data', 'state_action_data', 'scene_annotation_data', 'subtask_annotation_data', 'motion_annotation_data'],
        help='要检查的数据目录列表 (默认: data state_action_data scene_annotation_data subtask_annotation_data motion_annotation_data)'
    )
    
    args = parser.parse_args()
    
    dataset_path = Path(args.dataset_path)
    episode_num = args.episode_number
    
    if not dataset_path.exists():
        print(f"❌ 错误: 数据集路径不存在: {dataset_path}")
        return 1
    
    print("="*80)
    print(f"修复 Episode {episode_num} 的NaN值")
    print(f"数据集: {dataset_path}")
    print("="*80)
    
    episode_file = f"episode_{episode_num:06d}.parquet"
    success_count = 0
    total_count = 0
    
    for data_dir in args.data_dirs:
        file_path = dataset_path / data_dir / "chunk-000" / episode_file
        
        if not file_path.exists():
            print(f"\n⏭️ Skipping: {data_dir}/chunk-000/{episode_file} (不存在)")
            continue
        
        total_count += 1
        print(f"\n{'='*80}")
        print(f"处理目录: {data_dir}")
        print(f"{'='*80}")
        
        if process_parquet_file(file_path):
            success_count += 1
    
    print(f"\n{'='*80}")
    print(f"完成: {success_count}/{total_count} 文件处理成功")
    print(f"{'='*80}")
    
    return 0 if success_count == total_count else 1


if __name__ == "__main__":
    exit(main())
