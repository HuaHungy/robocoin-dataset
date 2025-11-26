#!/usr/bin/env python3
"""Check all episode 55 files for NaN values."""

import numpy as np
import pyarrow.parquet as pq
from pathlib import Path

files = [
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_put_the_pen_into_the_pen_holder/data/chunk-000/episode_000055.parquet",
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_put_the_pen_into_the_pen_holder/state_action_data/chunk-000/episode_000055.parquet",
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_put_the_pen_into_the_pen_holder/scene_annotation_data/chunk-000/episode_000055.parquet",
    "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_put_the_pen_into_the_pen_holder/subtask_annotation_data/chunk-000/episode_000055.parquet",
]

for file_path in files:
    print(f"\n{'='*80}")
    print(f"File: {Path(file_path).parent.parent.name}/{Path(file_path).parent.name}/{Path(file_path).name}")
    print('='*80)
    
    try:
        table = pq.read_table(file_path)
        df = table.to_pandas()
        
        print(f"Rows: {len(df)}, Columns: {df.columns.tolist()}")
        
        # Check each column for NaN
        has_nan = False
        for col in df.columns:
            col_data = df[col]
            
            # Check if column contains arrays/lists
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
                    print(f"  ⚠️ {col}: {nan_count} NaN elements in {len(rows_with_nan)} rows")
                    if len(rows_with_nan) <= 5:
                        print(f"     Rows: {rows_with_nan}")
                    else:
                        print(f"     First 5 rows: {rows_with_nan[:5]}")
            else:
                # Regular column
                nan_count = col_data.isna().sum()
                if nan_count > 0:
                    has_nan = True
                    print(f"  ⚠️ {col}: {nan_count} NaN values")
        
        if not has_nan:
            print("  ✅ No NaN values")
            
    except Exception as e:
        print(f"  ❌ Error: {e}")
