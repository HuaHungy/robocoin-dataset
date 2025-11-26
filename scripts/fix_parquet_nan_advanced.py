#!/usr/bin/env python3
"""Advanced parquet repair script for corrupted files.

This script attempts to repair severely corrupted parquet files by:
1. Reading raw parquet data
2. Trying alternative parsers (fastparquet)
3. Using lower-level parquet API calls
"""

from pathlib import Path

import pyarrow.parquet as pq

# Files that need repair
corrupted_files = [
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_take_out_a_pen_from_the_pen_holder/data/chunk-000/episode_000106.parquet",
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_place_the_test_tube/data/chunk-000/episode_000244.parquet",
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_five_in_one_board_storage/data/chunk-000/episode_000110.parquet",
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_building_block_classification/data/chunk-000/episode_000162.parquet",
]


def try_repair_with_fastparquet(file_path: Path) -> bool:
    """Try to repair file using fastparquet library."""
    try:
        import fastparquet
        
        print(f"   🔧 Trying fastparquet...")
        pf = fastparquet.ParquetFile(str(file_path))
        df = pf.to_pandas()
        
        print(f"   ✓ Successfully read with fastparquet!")
        print(f"   Rows: {len(df)}, Columns: {len(df.columns)}")
        
        # Check for NaN
        nan_count = df.isna().sum().sum()
        if nan_count > 0:
            print(f"   🔍 Found {nan_count} NaN values")
            
            # Show NaN distribution
            nan_info = df.isna().sum()
            nan_cols = nan_info[nan_info > 0]
            print("   NaN distribution:")
            for col, count in nan_cols.items():
                print(f"      - {col}: {count} NaN values")
            
            # Replace NaN with 0
            df_fixed = df.fillna(0)
            
            # Save back
            backup_path = file_path.with_suffix('.parquet.backup')
            print(f"   💾 Creating backup: {backup_path.name}")
            import shutil
            shutil.copy2(file_path, backup_path)
            
            print(f"   💾 Saving repaired file...")
            df_fixed.to_parquet(file_path, index=False)
            
            print("   ✅ Successfully repaired and saved!")
            return True
        else:
            print("   ℹ️  No NaN values found")
            return True
            
    except ImportError:
        print("   ❌ fastparquet not installed")
        print("   Install with: pip install fastparquet")
        return False
    except Exception as e:
        print(f"   ❌ fastparquet failed: {e}")
        return False


def try_repair_with_pyarrow_lowlevel(file_path: Path) -> bool:
    """Try to read using low-level PyArrow API."""
    try:
        print(f"   🔧 Trying PyArrow low-level API...")
        
        # Open the file
        parquet_file = pq.ParquetFile(file_path)
        
        print(f"   Metadata: {parquet_file.metadata.num_rows} rows, {parquet_file.metadata.num_columns} columns")
        print(f"   Schema: {parquet_file.schema_arrow}")
        
        # Try reading row group by row group
        print(f"   Number of row groups: {parquet_file.num_row_groups}")
        
        tables = []
        for i in range(parquet_file.num_row_groups):
            try:
                print(f"   Reading row group {i}...")
                table = parquet_file.read_row_group(i)
                tables.append(table)
                print(f"      ✓ Row group {i}: {len(table)} rows")
            except Exception as e:
                print(f"      ❌ Row group {i} failed: {e}")
                
        if not tables:
            print("   ❌ Could not read any row groups")
            return False
        
        # Combine tables
        import pyarrow as pa
        combined_table = pa.concat_tables(tables)
        df = combined_table.to_pandas()
        
        print(f"   ✓ Successfully combined {len(tables)} row groups")
        print(f"   Total rows: {len(df)}")
        
        # Check for NaN
        nan_count = df.isna().sum().sum()
        if nan_count > 0:
            print(f"   🔍 Found {nan_count} NaN values")
            df_fixed = df.fillna(0)
            
            # Save
            backup_path = file_path.with_suffix('.parquet.backup')
            print(f"   💾 Creating backup: {backup_path.name}")
            import shutil
            shutil.copy2(file_path, backup_path)
            
            df_fixed.to_parquet(file_path, index=False)
            print("   ✅ Successfully repaired!")
            return True
        else:
            print("   ℹ️  No NaN values found")
            return True
            
    except Exception as e:
        print(f"   ❌ PyArrow low-level API failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main repair function."""
    print("=" * 80)
    print("Advanced Parquet Repair Tool")
    print("=" * 80)
    
    for i, file_path_str in enumerate(corrupted_files, 1):
        file_path = Path(file_path_str)
        print(f"\n[{i}/{len(corrupted_files)}] Processing:")
        print(f"    {file_path}")
        
        if not file_path.exists():
            print("    ❌ File not found!")
            continue
        
        # Try fastparquet first
        if try_repair_with_fastparquet(file_path):
            continue
        
        # Try PyArrow low-level API
        if try_repair_with_pyarrow_lowlevel(file_path):
            continue
        
        print("    ⚠️  All repair attempts failed")
    
    print("\n" + "=" * 80)
    print("Repair process completed")
    print("=" * 80)


if __name__ == "__main__":
    main()
