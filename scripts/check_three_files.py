#!/usr/bin/env python3
"""Check the three files in data directory."""

import numpy as np
import pyarrow.parquet as pq

files = [
    ('/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_put_the_pen_into_the_pen_holder/data/chunk-000/episode_000055.parquet', 55),
    ('/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_pour_water/data/chunk-000/episode_000092.parquet', 92),
    ('/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_cover_the_pot_a/data/chunk-000/episode_000217.parquet', 217),
]

for file_path, ep_num in files:
    print('\n' + '='*80)
    print(f'Episode {ep_num}: {file_path}')
    try:
        table = pq.read_table(file_path)
        df = table.to_pandas()
        print(f'Rows: {len(df)}, Columns: {len(df.columns)}')
        
        # Check for NaN in arrays
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
                    print(f'  ⚠️ {col}: {nan_count} NaN elements in {len(rows_with_nan)} rows')
                    print(f'     Affected rows: {rows_with_nan[:10]}...' if len(rows_with_nan) > 10 else f'     Affected rows: {rows_with_nan}')
                else:
                    print(f'  ✅ {col}: No NaN')
    except Exception as e:
        print(f'Error: {e}')
