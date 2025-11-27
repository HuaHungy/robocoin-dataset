#!/usr/bin/env python3
"""Fix NaN values in parquet files at specific episode indices.

This script checks specific episode files for NaN values and replaces them with 0.
The 'index' refers to the episode number (e.g., index 55 means episode_000055.parquet).
"""

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

# Define the datasets and their problematic episode indices
# Note: index refers to the episode number, not row number within the parquet file
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


def fix_nan_in_parquet(dataset_path: str, episode_num: int):
    """Fix NaN values in a specific episode parquet file.
    
    Args:
        dataset_path: Path to the dataset directory
        episode_num: Episode number (e.g., 55 for episode_000055.parquet)
    
    Returns:
        bool: True if successful, False otherwise
    """
    dataset_path = Path(dataset_path)
    
    # Look for episode parquet file in various directories
    episode_filename = f"episode_{episode_num:06d}.parquet"
    
    # List of possible directories to check (in priority order)
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
        print("   Checked directories:")
        for check_dir in possible_dirs:
            print(f"      - {check_dir}")
        return False
    
    # Process the parquet file
    print(f"\n📁 Processing: {parquet_file}")
    
    try:
        # Try reading with pandas first
        try:
            df = pd.read_parquet(parquet_file)
        except Exception as pandas_error:
            print(f"   ⚠️  Pandas failed to read file: {pandas_error}")
            print("   🔧 Attempting repair with PyArrow...")
            
            # Try using PyArrow directly with error recovery
            try:
                # Read with PyArrow, which can sometimes handle corrupt files better
                table = pq.read_table(parquet_file)
                df = table.to_pandas()
                print("   ✓ Successfully read file with PyArrow")
            except Exception as arrow_error:
                print(f"   ❌ PyArrow also failed: {arrow_error}")
                print("   🔧 Attempting to read metadata and reconstruct...")
                
                # Try reading just the metadata
                try:
                    parquet_metadata = pq.read_metadata(parquet_file)
                    print(f"   File has {parquet_metadata.num_rows} rows and {parquet_metadata.num_columns} columns")
                    print("   ⚠️  File is severely corrupted - manual intervention required")
                    return False
                except Exception as meta_error:
                    print(f"   ❌ Cannot even read metadata: {meta_error}")
                    print("   ⚠️  File is completely corrupted - may need regeneration")
                    return False
        
        print(f"   Total rows: {len(df)}")
        print(f"   Total columns: {len(df.columns)}")
        
        # First, check if there are ANY NaN values in this file
        nan_count_total = df.isna().sum().sum()
        
        if nan_count_total == 0:
            print("   ℹ️  No NaN values found in this episode file - skipping")
            return True
        
        # Found NaN values - show details
        print(f"   🔍 Found {nan_count_total} NaN values in the file")
        
        # Get detailed information about NaN values
        nan_info = df.isna().sum()
        nan_cols = nan_info[nan_info > 0]
        
        print("   NaN distribution by column:")
        for col, count in nan_cols.items():
            print(f"      - {col}: {count} NaN values")
        
        # Show which rows have NaN values
        rows_with_nan = df[df.isna().any(axis=1)].index.tolist()
        if len(rows_with_nan) <= 10:
            print(f"   Rows with NaN: {rows_with_nan}")
        else:
            print(f"   Rows with NaN: {rows_with_nan[:10]}... (showing first 10 of {len(rows_with_nan)})")
        
        # Ask for confirmation before modifying
        print("\n   ⚠️  About to replace ALL NaN values with 0")
        
        # Replace all NaN with 0
        df_fixed = df.fillna(0)
        
        # Save the modified dataframe back to parquet
        df_fixed.to_parquet(parquet_file, index=False)
        print("   ✅ Fixed all NaN values in the file")
        
        # Verify the fix
        df_verify = pd.read_parquet(parquet_file)
        nan_count_after = df_verify.isna().sum().sum()
        if nan_count_after > 0:
            print(f"   ⚠️  Warning: Still have {nan_count_after} NaN values")
            return False
        else:
            print("   ✓ Verification passed - no NaN values remaining")
            return True
        
    except Exception as e:
        print(f"   ❌ Error processing {parquet_file}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function to process all datasets."""
    print("=" * 80)
    print("Starting parquet NaN fix process")
    print("=" * 80)
    
    success_count = 0
    total_count = len(datasets)
    
    for i, dataset in enumerate(datasets, 1):
        print(f"\n[{i}/{total_count}] Processing dataset:")
        print(f"    Path: {dataset['path']}")
        print(f"    Episode: {dataset['episode']} (episode_{dataset['episode']:06d}.parquet)")
        
        if fix_nan_in_parquet(dataset['path'], dataset['episode']):
            success_count += 1
    
    print("\n" + "=" * 80)
    print(f"Process completed: {success_count}/{total_count} datasets processed successfully")
    print("=" * 80)


if __name__ == "__main__":
    main()
