#!/usr/bin/env python3
"""Fix NaN values inside list/array columns in parquet files.

This script specifically handles NaN values that appear inside list-type columns,
such as observation.state and action columns which contain arrays of floats.
"""

from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pyarrow as pa

# Define the datasets and their problematic episode indices
datasets = [
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_put_the_pen_into_the_pen_holder",
        "episode": 55  # episode_000055.parquet
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_take_out_a_pen_from_the_pen_holder",
        "episode": 106  # episode_000106.parquet
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_pour_water",
        "episode": 92  # episode_000092.parquet
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_place_the_test_tube",
        "episode": 244  # episode_000244.parquet
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_five_in_one_board_storage",
        "episode": 110  # episode_000110.parquet
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_cover_the_pot_a",
        "episode": 217  # episode_000217.parquet
    },
    {
        "path": "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_building_block_classification",
        "episode": 162  # episode_000162.parquet
    }
]


def fix_nan_in_arrays(dataset_path: str, episode_num: int):
    """Fix NaN values inside array/list columns in parquet files.
    
    Args:
        dataset_path: Path to the dataset directory
        episode_num: Episode number
    
    Returns:
        bool: True if successful, False otherwise
    """
    dataset_path = Path(dataset_path)
    
    # Look for episode parquet file in various directories
    episode_filename = f"episode_{episode_num:06d}.parquet"
    
    possible_dirs = [
        dataset_path / "motion_annotation_data" / "chunk-000",
        dataset_path / "subtask_annotation_data" / "chunk-000",
        dataset_path / "data" / "chunk-000",
        dataset_path / "state_action_data" / "chunk-000",
        dataset_path / "scene_annotation_data" / "chunk-000",
    ]
    
    parquet_file = None
    for check_dir in possible_dirs:
        potential_file = check_dir / episode_filename
        if potential_file.exists():
            parquet_file = potential_file
            break
    
    if parquet_file is None:
        print(f"❌ Episode file not found: {episode_filename}")
        return False

    print(f"\n📁 Processing: {parquet_file}")
    
    try:
        # Read the parquet file
        table = pq.read_table(parquet_file)
        df = table.to_pandas()
        
        print(f"   Total rows: {len(df)}")
        print(f"   Total columns: {len(df.columns)}")
        
        # Check for NaN values inside array columns
        has_nan = False
        nan_details = {}
        
        for col_name in df.columns:
            col_data = df[col_name]
            
            # Check if this is a column of lists/arrays
            if len(col_data) > 0 and isinstance(col_data.iloc[0], (list, np.ndarray)):
                # Count NaN values inside the arrays
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
                    nan_details[col_name] = {
                        'count': nan_count,
                        'rows': rows_with_nan
                    }
        
        if not has_nan:
            print("   ℹ️  No NaN values found inside arrays")
            return True
        
        # Found NaN values - show details
        print(f"   🔍 Found NaN values inside array columns!")
        for col_name, info in nan_details.items():
            print(f"\n   Column: {col_name}")
            print(f"      Total NaN elements: {info['count']}")
            print(f"      Rows affected: {len(info['rows'])}/{len(df)}")
            if len(info['rows']) <= 5:
                print(f"      Row indices: {info['rows']}")
            else:
                print(f"      Row indices: {info['rows'][:5]}... (showing first 5)")
        
        print("\n   ⚠️  About to replace all NaN values in arrays with 0")
        
        # Create backup
        backup_path = parquet_file.with_suffix('.parquet.backup')
        print(f"   💾 Creating backup: {backup_path.name}")
        import shutil
        shutil.copy2(parquet_file, backup_path)
        
        # Fix NaN values in array columns
        df_fixed = df.copy()
        for col_name in nan_details.keys():
            print(f"   🔧 Fixing column: {col_name}")
            df_fixed[col_name] = df_fixed[col_name].apply(
                lambda arr: np.nan_to_num(arr, nan=0.0).tolist() if arr is not None else arr
            )
        
        # Save the fixed dataframe
        df_fixed.to_parquet(parquet_file, index=False)
        print("   ✅ Fixed all NaN values in arrays")
        
        # Verify the fix
        table_verify = pq.read_table(parquet_file)
        df_verify = table_verify.to_pandas()
        
        # Re-check for NaN
        verify_nan = False
        for col_name in nan_details.keys():
            col_data = df_verify[col_name]
            for arr in col_data:
                if arr is not None and isinstance(arr, (list, np.ndarray)):
                    if np.isnan(np.array(arr)).any():
                        verify_nan = True
                        break
            if verify_nan:
                break
        
        if verify_nan:
            print("   ⚠️  Warning: Still have NaN values in arrays")
            return False
        
        print("   ✓ Verification passed - no NaN values in arrays")
        return True
        
    except Exception as e:
        print(f"   ❌ Error processing {parquet_file}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function to process all datasets."""
    print("=" * 80)
    print("Starting parquet array NaN fix process")
    print("=" * 80)
    
    success_count = 0
    total_count = len(datasets)
    
    for i, dataset in enumerate(datasets, 1):
        print(f"\n[{i}/{total_count}] Processing dataset:")
        print(f"    Path: {dataset['path']}")
        print(f"    Episode: {dataset['episode']} (episode_{dataset['episode']:06d}.parquet)")
        
        if fix_nan_in_arrays(dataset['path'], dataset['episode']):
            success_count += 1
    
    print("\n" + "=" * 80)
    print(f"Process completed: {success_count}/{total_count} datasets processed successfully")
    print("=" * 80)


if __name__ == "__main__":
    main()
