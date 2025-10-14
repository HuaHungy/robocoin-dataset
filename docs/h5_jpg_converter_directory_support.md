# H5+JPG Converter - Directory Structure Support

## Quick Reference

The H5+JPG converter now supports **flexible directory structures** up to 5 levels deep.

## Supported Structures

### ✅ All these structures work:

1. **Flat** (1 level)
   ```
   task_path/
     ├── episode_001/aligned_joints.h5
     └── episode_002/aligned_joints.h5
   ```

2. **Nested** (2 levels) - Common
   ```
   task_path/
     └── batch_A/
         ├── episode_001/aligned_joints.h5
         └── episode_002/aligned_joints.h5
   ```

3. **Deep Nested** (3 levels) - Ruantong A2D
   ```
   task_path/
     └── device_ID/
         └── batch_001/
             └── episode_001/aligned_joints.h5
   ```

4. **Very Deep** (up to 5 levels)
   ```
   task_path/
     └── level1/
         └── level2/
             └── level3/
                 └── episode/aligned_joints.h5
   ```

## What Gets Skipped

- Directories starting with `.` (hidden)
- Directories starting with `@` (system, like `@eaDir`)
- Files (only directories are searched)

## Testing Your Dataset

Use the test tool before conversion:

```bash
# Test a specific task path
python tools/test_ruantong_structure.py <task_path>

# Example
python tools/test_ruantong_structure.py "/path/to/dataset/task_001"
```

**Expected output:**
```
📂 Directory structure (first 3 levels):
└── task_001/
    └── batch_A/
        ├── episode_001/ ✅ [Episode]
        └── episode_002/ ✅ [Episode]

🔍 Searching for episode directories (up to 5 levels deep)...
✅ Found 2 episode(s)
```

## Troubleshooting

### ❌ "No episode directories found"

**Check these:**

1. **File exists?** Each episode must have `aligned_joints.h5`
   ```bash
   find <task_path> -name "aligned_joints.h5"
   ```

2. **Too deep?** Maximum 5 levels from task_path
   ```bash
   # This won't work (6 levels)
   task/a/b/c/d/e/episode/aligned_joints.h5
   ```

3. **Special names?** Directories starting with `.` or `@` are skipped
   ```bash
   # These are skipped
   task/@eaDir/episode/
   task/.hidden/episode/
   ```

4. **Permissions?** Check read access
   ```bash
   ls -la <task_path>
   ```

### ❌ "Episode index out of range"

The converter found episodes, but fewer than expected.

**Debug:**
```bash
# See what was found
python tools/test_ruantong_structure.py <task_path>
```

## Error Messages

The converter now shows **detailed directory structure** in errors:

```
❌ No episode directories found.
   📁 Task path: /path/to/task
   🔍 Searched up to 5 levels deep
   📂 Directory structure (first 3 levels):
   task/
     @eaDir/ [Skipped]
     batch_A/
       episode_001/
       episode_002/
   🗂️  Expected: Directories containing 'aligned_joints.h5' file
   💡 Check if:
      1. Episode directories exist under task path
      2. Each episode directory contains 'aligned_joints.h5' file
      3. File permissions are correct
      4. Directory names don't start with '.' or '@' (these are skipped)
```

## Dataset-Specific Notes

### Ruantong A2D (软通天擎)

**Structure:** 3 levels
```
task_path/503/
  └── A2D0015AC00557/        ← Device ID
      ├── 182088/            ← Episode
      │   ├── aligned_joints.h5
      │   ├── camera/
      │   └── meta_info.json
      └── 182090/
```

**Notes:**
- Device ID directory contains all episodes
- `@eaDir` is automatically skipped
- ~194 episodes per task typical

## See Also

- **Full Fix Documentation**: `docs/fixes/ruantong_directory_structure_fix.md`
- **Test Tool**: `tools/test_ruantong_structure.py`
- **Converter Code**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_jpg.py`
