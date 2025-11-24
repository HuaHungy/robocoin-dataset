#!/usr/bin/env python3
"""Fix the remaining three files with NaN values."""

from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
import shutil

files_to_fix = [
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_put_the_pen_into_the_pen_holder/data/chunk-000/episode_000055.parquet",
        "episode": 55
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_pour_water/data/chunk-000/episode_000092.parquet",
        "episode": 92
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_cover_the_pot_a/data/chunk-000/episode_000217.parquet",
        "episode": 217
    }
]

def fix_file(file_info):
    """Fix NaN values in a single file."""
    file_path = Path(file_info['path'])
    episode = file_info['episode']
    
    print(f"\n{'='*80}")
    print(f"Processing Episode {episode}")
    print(f"File: {file_path}")
    print('='*80)
    
    try:
        # Read the file
        table = pq.read_table(file_path)
        df = table.to_pandas()
        
        print(f"Rows: {len(df)}, Columns: {len(df.columns)}")
        
        # Check for NaN in arrays
        has_nan = False
        nan_details = {}
        
        for col in ['observation.state', 'action']:
            if col in df.columns:
                nan_count = 0
                rows_with_nan = []
                for idx, arr in enumerate(df[col]):
                    if isinstance(arr, (list, np.ndarray)):
                        arr_nan_count = np.isnan(np.array(arr)).sum()
                        if arr_nan_count > 0:
                            nan_count += arr_nan_count
                            rows_with_nan.append(idx)
                
                if nan_count > 0:
                    has_nan = True
                    nan_details[col] = {
                        'count': nan_count,
                        'rows': len(rows_with_nan)
                    }
                    print(f"  ⚠️ {col}: {nan_count} NaN elements in {len(rows_with_nan)} rows")
        
        if not has_nan:
            print("  ✅ No NaN values found")
            return True
        
        # Create backup
        backup_path = file_path.with_suffix('.parquet.backup')
        print(f"\n  💾 Creating backup: {backup_path.name}")
        shutil.copy2(file_path, backup_path)
        
        # Fix NaN values
        print("  🔧 Fixing NaN values...")
        df_fixed = df.copy()
        for col in nan_details.keys():
            df_fixed[col] = df_fixed[col].apply(
                lambda arr: np.nan_to_num(arr, nan=0.0).tolist() if arr is not None else arr
            )
        
        # Save
        df_fixed.to_parquet(file_path, index=False)
        print("  ✅ Fixed all NaN values")
        
        # Verify
        table_verify = pq.read_table(file_path)
        df_verify = table_verify.to_pandas()
        
        verify_nan = False
        for col in nan_details.keys():
            for arr in df_verify[col]:
                if arr is not None and isinstance(arr, (list, np.ndarray)):
                    if np.isnan(np.array(arr)).any():
                        verify_nan = True
                        break
            if verify_nan:
                break
        
        if verify_nan:
            print("  ⚠️ Warning: Still have NaN values")
            return False
        
        print("  ✓ Verification passed - no NaN values remaining")
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("="*80)
    print("Fixing remaining three files with NaN values")
    print("="*80)
    
    success = 0
    for file_info in files_to_fix:
        if fix_file(file_info):
            success += 1
    
    print(f"\n{'='*80}")
    print(f"Completed: {success}/{len(files_to_fix)} files fixed successfully")
    print("="*80)

if __name__ == "__main__":
    main()
