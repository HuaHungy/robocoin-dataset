#!/usr/bin/env python3
"""Fix NaN values in state_action_data directory for all 7 episodes."""

from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
import shutil

datasets = [
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_put_the_pen_into_the_pen_holder",
        "episode": 55
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_take_out_a_pen_from_the_pen_holder",
        "episode": 106
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_pour_water",
        "episode": 92
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_place_the_test_tube",
        "episode": 244
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_five_in_one_board_storage",
        "episode": 110
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_cover_the_pot_a",
        "episode": 217
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_building_block_classification",
        "episode": 162
    }
]

def fix_state_action_file(dataset_path: str, episode_num: int):
    """Fix NaN values in state_action_data file."""
    dataset_path = Path(dataset_path)
    episode_filename = f"episode_{episode_num:06d}.parquet"
    
    # state_action_data path
    file_path = dataset_path / "state_action_data" / "chunk-000" / episode_filename
    
    if not file_path.exists():
        print(f"  ⚠️ File not found: {file_path}")
        return True  # Skip if doesn't exist
    
    print(f"\n{'='*80}")
    print(f"Processing Episode {episode_num}")
    print(f"File: {file_path}")
    print('='*80)
    
    try:
        # Read file
        table = pq.read_table(file_path)
        df = table.to_pandas()
        
        print(f"Rows: {len(df)}, Columns: {df.columns.tolist()}")
        
        # Check for NaN
        has_nan = False
        nan_details = {}
        
        for col in df.columns:
            col_data = df[col]
            
            if len(col_data) > 0 and isinstance(col_data.iloc[0], (list, np.ndarray)):
                nan_count = 0
                rows_with_nan = []
                for idx, arr in enumerate(col_data):
                    if arr is not None and isinstance(arr, (list, np.ndarray)):
                        arr_np = np.array(arr)
                        if np.isnan(arr_np).any():
                            nan_count += np.isnan(arr_np).sum()
                            rows_with_nan.append(idx)
                
                if nan_count > 0:
                    has_nan = True
                    nan_details[col] = {
                        'count': nan_count,
                        'rows': len(rows_with_nan)
                    }
                    print(f"  ⚠️ {col}: {nan_count} NaN elements in {len(rows_with_nan)} rows")
        
        if not has_nan:
            print("  ✅ No NaN values")
            return True
        
        # Create backup
        backup_path = file_path.with_suffix('.parquet.backup')
        print(f"\n  💾 Creating backup: {backup_path.name}")
        shutil.copy2(file_path, backup_path)
        
        # Fix NaN
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
        
        print("  ✓ Verification passed")
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("="*80)
    print("Fixing NaN in state_action_data for all 7 episodes")
    print("="*80)
    
    success = 0
    for dataset in datasets:
        if fix_state_action_file(dataset['path'], dataset['episode']):
            success += 1
    
    print(f"\n{'='*80}")
    print(f"Completed: {success}/{len(datasets)} files processed successfully")
    print("="*80)

if __name__ == "__main__":
    main()
