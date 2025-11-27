#!/usr/bin/env python3
"""Detailed null value inspection for parquet files."""

from pathlib import Path

import pyarrow.parquet as pq
import pyarrow as pa
import pandas as pd

# Files to check
files_to_check = [
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_put_the_pen_into_the_pen_holder/subtask_annotation_data/chunk-000/episode_000055.parquet",
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_take_out_a_pen_from_the_pen_holder/data/chunk-000/episode_000106.parquet",
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_pour_water/subtask_annotation_data/chunk-000/episode_000092.parquet",
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_place_the_test_tube/data/chunk-000/episode_000244.parquet",
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_five_in_one_board_storage/data/chunk-000/episode_000110.parquet",
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_cover_the_pot_a/subtask_annotation_data/chunk-000/episode_000217.parquet",
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_building_block_classification/data/chunk-000/episode_000162.parquet",
]


def deep_inspect_null(file_path: str):
    """Deep inspection of null values in parquet file."""
    print(f"\n{'='*80}")
    print(f"File: {Path(file_path).name}")
    print(f"Path: {file_path}")
    print('='*80)
    
    try:
        # Read with PyArrow
        table = pq.read_table(file_path)
        print(f"\n📊 Basic Info:")
        print(f"   Rows: {table.num_rows}")
        print(f"   Columns: {table.num_columns}")
        
        # Check each column
        print(f"\n🔍 Column Analysis:")
        for i, col_name in enumerate(table.column_names):
            col = table.column(col_name)
            print(f"\n   Column {i}: {col_name}")
            print(f"      Type: {col.type}")
            print(f"      Length: {len(col)}")
            print(f"      Null count (PyArrow): {col.null_count}")
            
            # Convert to pandas and check
            try:
                # For complex types, check if any chunks have nulls
                if pa.types.is_list(col.type) or pa.types.is_struct(col.type):
                    print(f"      Complex type detected")
                    # Check chunks
                    for chunk_idx, chunk in enumerate(col.chunks):
                        if chunk.null_count > 0:
                            print(f"         Chunk {chunk_idx} has {chunk.null_count} nulls")
                
                # Try to convert to pandas to check for NaN
                col_series = col.to_pandas()
                pandas_null_count = col_series.isna().sum()
                print(f"      Null count (pandas): {pandas_null_count}")
                
                # Show first few non-null values
                non_null = col_series[col_series.notna()]
                if len(non_null) > 0:
                    print(f"      First non-null value: {non_null.iloc[0]}")
                    if isinstance(non_null.iloc[0], list):
                        print(f"         (list with {len(non_null.iloc[0])} elements)")
                
                # Show null value positions if any
                null_positions = col_series[col_series.isna()].index.tolist()
                if null_positions:
                    if len(null_positions) <= 5:
                        print(f"      ⚠️ NULL at positions: {null_positions}")
                    else:
                        print(f"      ⚠️ NULL at positions: {null_positions[:5]}... (showing first 5 of {len(null_positions)})")
                        
            except Exception as e:
                print(f"      ⚠️ Error converting to pandas: {e}")
        
        # Overall summary
        df = table.to_pandas()
        total_nulls = df.isna().sum().sum()
        print(f"\n📈 Overall Summary:")
        print(f"   Total null values in entire file: {total_nulls}")
        
        if total_nulls > 0:
            print(f"\n   ⚠️⚠️⚠️ FILE HAS {total_nulls} NULL VALUES ⚠️⚠️⚠️")
            # Show rows with nulls
            rows_with_null = df[df.isna().any(axis=1)]
            print(f"   Number of rows with nulls: {len(rows_with_null)}")
            if len(rows_with_null) <= 3:
                print(f"\n   Rows with nulls:")
                print(rows_with_null)
        else:
            print(f"   ✅ No null values found")
            
    except Exception as e:
        print(f"\n❌ Error reading file: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main function."""
    print("="*80)
    print("DETAILED NULL VALUE INSPECTION")
    print("="*80)
    
    for file_path in files_to_check:
        deep_inspect_null(file_path)
    
    print("\n" + "="*80)
    print("INSPECTION COMPLETE")
    print("="*80)


if __name__ == "__main__":
    main()
