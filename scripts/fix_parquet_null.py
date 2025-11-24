#!/usr/bin/env python3
"""Fix null values in parquet files at specific episode indices.

This script checks specific episode files for null values and replaces them with 0.
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


def fix_null_in_parquet(dataset_path: str, episode_num: int):
    """Fix null values in a specific episode parquet file.
    
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
        # Read the parquet file using PyArrow to detect nulls properly
        print("   Reading with PyArrow...")
        table = pq.read_table(parquet_file)
        
        print(f"   Total rows: {table.num_rows}")
        print(f"   Total columns: {table.num_columns}")
        
        # Check for null values in the table
        null_count_total = 0
        null_info = {}
        
        for col_name in table.column_names:
            col = table.column(col_name)
            null_count = col.null_count
            if null_count > 0:
                null_count_total += null_count
                null_info[col_name] = null_count
        
        if null_count_total == 0:
            print("   ℹ️  No null values found in this episode file - skipping")
            return True
        
        # Found null values - show details
        print(f"   🔍 Found {null_count_total} null values in the file")
        
        print("   Null distribution by column:")
        for col, count in null_info.items():
            print(f"      - {col}: {count} null values")
        
        # Convert to pandas for easier manipulation
        df = table.to_pandas()
        
        # Show which rows have null values
        rows_with_null = df[df.isna().any(axis=1)].index.tolist()
        if len(rows_with_null) <= 10:
            print(f"   Rows with null: {rows_with_null}")
        else:
            print(f"   Rows with null: {rows_with_null[:10]}... (showing first 10 of {len(rows_with_null)})")
        
        print("\n   ⚠️  About to replace ALL null values with 0")
        
        # Create backup
        backup_path = parquet_file.with_suffix('.parquet.backup')
        print(f"   💾 Creating backup: {backup_path.name}")
        import shutil
        shutil.copy2(parquet_file, backup_path)
        
        # Replace all null/NaN with 0
        df_fixed = df.fillna(0)
        
        # Save the modified dataframe back to parquet
        df_fixed.to_parquet(parquet_file, index=False)
        print("   ✅ Fixed all null values in the file")
        
        # Verify the fix
        table_verify = pq.read_table(parquet_file)
        null_count_after = sum(table_verify.column(col).null_count for col in table_verify.column_names)
        
        if null_count_after > 0:
            print(f"   ⚠️  Warning: Still have {null_count_after} null values")
            return False
        
        print("   ✓ Verification passed - no null values remaining")
        return True
        
    except Exception as e:
        print(f"   ❌ Error processing {parquet_file}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function to process all datasets."""
    print("=" * 80)
    print("Starting parquet null value fix process")
    print("=" * 80)
    
    success_count = 0
    total_count = len(datasets)
    
    for i, dataset in enumerate(datasets, 1):
        print(f"\n[{i}/{total_count}] Processing dataset:")
        print(f"    Path: {dataset['path']}")
        print(f"    Episode: {dataset['episode']} (episode_{dataset['episode']:06d}.parquet)")
        
        if fix_null_in_parquet(dataset['path'], dataset['episode']):
            success_count += 1
    
    print("\n" + "=" * 80)
    print(f"Process completed: {success_count}/{total_count} datasets processed successfully")
    print("=" * 80)


if __name__ == "__main__":
    main()
