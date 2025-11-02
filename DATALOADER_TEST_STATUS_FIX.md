# Dataloader Test Status Checking Fix

**Date:** 2025-11-02
**Issue:** Server mode couldn't find tasks that local mode could process

## 🐛 Root Cause

The local mode and server mode had **inconsistent** dataset discovery logic:

- **Local mode** (`dataloader_test.py`):
  - Only checked: `convert_path != NULL`
  - ❌ Missing status checks

- **Server mode** (`dataloader.py`):
  - Only checked: `convert_status == COMPLETED`
  - ❌ Missing `data_merge_status` check

This caused:
1. Local mode to process datasets that weren't ready
2. Server mode to miss `data_merge_status` requirement

## ✅ Solution

**Enforced STRICT requirements in BOTH modes:**

### Required Conditions (All Must Be True)
1. ✅ `data_merge_status == TaskStatus.COMPLETED`
2. ✅ `convert_status == TaskStatus.COMPLETED`
3. ✅ `convert_path != NULL` (and path exists)

## 📝 Changes Made

### 1. Fixed Server Mode (`src/robocoin_dataset/dataloader/dataloader.py`)

**Function:** `_sync_dataloader_detection_tasks()`

```python
# Added BOTH required status checks
query = session.query(DatasetDB).filter(
    and_(
        DatasetDB.data_merge_status == TaskStatus.COMPLETED,  # ✅ Added
        DatasetDB.convert_status == TaskStatus.COMPLETED,     # ✅ Kept
        or_(
            DatasetDB.data_loader_detection_status == TaskStatus.PENDING,
            and_(
                DatasetDB.data_loader_detection_status == TaskStatus.COMPLETED,
                DatasetDB.data_loader_detection_version_ps < DatasetDB.convert_version,
            ),
        ),
    )
)
```

### 2. Fixed Local Mode (`scripts/dataloader/dataloader_test.py`)

**Functions:**
- `_find_first_dataset_with_convert_path()`
- `_find_all_datasets_with_convert_path()`

```python
# Added BOTH required status checks
rows = (
    session.query(DatasetDB.dataset_uuid, DatasetDB.convert_path)
    .filter(DatasetDB.data_merge_status == TaskStatus.COMPLETED)  # ✅ Added
    .filter(DatasetDB.convert_status == TaskStatus.COMPLETED)      # ✅ Added
    .filter(DatasetDB.convert_path != None)
    .all()
)
```

## 🎯 Expected Behavior After Fix

### Before Fix:
- ❌ Local mode: Found datasets with `convert_path` but wrong statuses
- ❌ Server mode: Only checked `convert_status`, ignored `data_merge_status`
- ❌ Inconsistent: Different results between local and server modes

### After Fix:
- ✅ Local mode: Only finds fully COMPLETED datasets
- ✅ Server mode: Checks BOTH merge and convert statuses
- ✅ Consistent: Both modes use identical criteria

## 🧪 How to Verify

### 1. Check Database Status

```sql
-- See which datasets meet criteria
SELECT
    dataset_uuid,
    data_merge_status,
    convert_status,
    convert_path,
    data_loader_detection_status
FROM DatasetDB
WHERE data_merge_status = 'COMPLETED'
  AND convert_status = 'COMPLETED'
  AND convert_path IS NOT NULL;
```

### 2. Test Local Mode

```bash
python scripts/dataloader/dataloader_test.py --local --db your.db
```

**Expected:** Only processes datasets with BOTH statuses COMPLETED

### 3. Test Server Mode

```bash
# Terminal 1: Start server
python scripts/dataloader/dataloader_test.py --server --db your.db

# Terminal 2: Start client
python scripts/dataloader/dataloader_test.py --client
```

**Expected:** Server finds same datasets as local mode

## 📊 Diagnostic Messages

### If "No task available" appears:
Check your database to ensure records have:
- ✅ `data_merge_status = 'COMPLETED'`
- ✅ `convert_status = 'COMPLETED'`
- ✅ `convert_path` populated and valid

### Update Status Example:

```sql
-- If you need to mark records as COMPLETED for testing
UPDATE DatasetDB
SET
    data_merge_status = 'COMPLETED',
    convert_status = 'COMPLETED'
WHERE dataset_uuid = 'your-uuid-here'
  AND convert_path IS NOT NULL;
```

## 🔒 Design Principle

**Dataloader testing should ONLY run on fully processed datasets:**

1. Data must be merged → `data_merge_status = COMPLETED`
2. Data must be converted → `convert_status = COMPLETED`
3. Converted path must exist → `convert_path != NULL`

This ensures dataloader validation happens at the correct pipeline stage.

## ✨ Summary

**Status checks are now STRICT and CONSISTENT across all modes:**
- ✅ Both `data_merge_status` and `convert_status` must be `COMPLETED`
- ✅ Local and server modes use identical filtering logic
- ✅ No more "ghost tasks" that appear in one mode but not the other
