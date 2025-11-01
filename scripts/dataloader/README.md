# DataLoader Scripts - FAKE Test Data Generator & Symlink Creator

This directory contains scripts to generate **FAKE test data** and create symbolic links for LeRobot-compatible dataset structure.

## 📋 Contents

1. **`make_fake_data.py`** - Generates FAKE test data in pipeline-produced format
2. **`make_data_sym_links.py`** *(in `src/robocoin_dataset/dataloader/`)* - Creates symlinks for LeRobot compatibility

---

## 🔧 Script 1: `make_fake_data.py`

### Purpose
Generates **FAKE test data** for testing the symlink creation and dataloader functionality. The data mimics the structure of your real pipeline output but contains synthetic/placeholder content.

### Quick Start

```bash
# Generate FAKE test data with default settings
python scripts/dataloader/make_fake_data.py

# This creates: examples/dataloader_test/fake_ori_data_001/
```

### Auto-Increment Feature

**The script automatically increments version numbers to prevent overwrites:**

```bash
# First run → creates fake_ori_data_001
python scripts/dataloader/make_fake_data.py

# Second run → detects fake_ori_data_001 exists → creates fake_ori_data_002
python scripts/dataloader/make_fake_data.py

# Third run → creates fake_ori_data_003
python scripts/dataloader/make_fake_data.py
```

**Works with any naming pattern:**
- `fake_ori_data_001` → `fake_ori_data_002` → `fake_ori_data_003` → ...
- `fake_test_001` → `fake_test_002` → ...
- `my_fake_dataset_001` → `my_fake_dataset_002` → ...

The prefix "fake_" is in the default name to **explicitly identify test data**.

### Command Options

```bash
# Default: 2500 episodes in 3 chunks
python scripts/dataloader/make_fake_data.py

# Custom dataset name (still FAKE data)
python scripts/dataloader/make_fake_data.py --dataset-name fake_test_001

# Smaller dataset for quick testing
python scripts/dataloader/make_fake_data.py --episodes 100 --chunks 1

# Larger dataset
python scripts/dataloader/make_fake_data.py --episodes 10000 --chunks 10

# Custom output location
python scripts/dataloader/make_fake_data.py --output /path/to/custom/location

# Customize number of videos per episode
python scripts/dataloader/make_fake_data.py --videos-per-episode 3
```

### Generated Structure

The script generates FAKE data in this pipeline-produced format:

```
fake_ori_data_001/
├── annotations/              # FAKE annotation data
│   └── subtasks.jsonl
├── merged_data/              # FAKE episode data in chunks
│   ├── chunk-000/
│   │   ├── episode_000000.parquet  # FAKE parquet files
│   │   ├── episode_000001.parquet
│   │   └── ...
│   ├── chunk-001/
│   └── ...
├── videos/                   # FAKE video files (empty placeholders)
│   ├── episode_000000_camera_front.mp4
│   ├── episode_000000_camera_wrist.mp4
│   └── ...
├── episodes.jsonl            # FAKE episode metadata
├── merged_episodes_stats.jsonl  # FAKE statistics
├── merged_info.json          # FAKE dataset info
└── tasks.jsonl               # FAKE task definitions
```

### What's Generated

| Component | Content |
|-----------|---------|
| **Parquet files** | Small placeholder DataFrames (5 rows each) with fake robot data |
| **Video files** | Empty placeholder files (`.mp4` extension, no actual video) |
| **JSONL files** | Synthetic metadata matching the pipeline format |
| **JSON files** | Synthetic configuration and info data |

### Help

```bash
python scripts/dataloader/make_fake_data.py --help
```

---

## 🔗 Script 2: `make_data_sym_links.py`

### Purpose
Creates a LeRobot-compatible directory structure using **symbolic links** that point to your actual pipeline data. This avoids duplicating large datasets.

### Location
`src/robocoin_dataset/dataloader/make_data_sym_links.py`

### Quick Start

```bash
# After generating fake test data, create symlinks:
python src/robocoin_dataset/dataloader/make_data_sym_links.py \
    --source examples/dataloader_test/fake_ori_data_001

# This creates: examples/dataloader_test/symlinked_fake_ori_data_001/
```

### Command Options

```bash
# Auto-generates target directory name
python src/robocoin_dataset/dataloader/make_data_sym_links.py \
    --source examples/dataloader_test/fake_ori_data_001

# Specify custom target directory
python src/robocoin_dataset/dataloader/make_data_sym_links.py \
    --source examples/dataloader_test/fake_ori_data_001 \
    --target /path/to/custom/lerobot_dataset

# Use absolute paths instead of relative
python src/robocoin_dataset/dataloader/make_data_sym_links.py \
    --source examples/dataloader_test/fake_ori_data_001 \
    --absolute

# Skip missing files instead of raising errors
python src/robocoin_dataset/dataloader/make_data_sym_links.py \
    --source examples/dataloader_test/fake_ori_data_001 \
    --skip-missing
```

### Created Symlink Structure

The script creates this LeRobot-compatible structure:

```
symlinked_fake_ori_data_001/
├── annotations/           → ../fake_ori_data_001/annotations
├── data/                  → ../fake_ori_data_001/merged_data
├── videos/                → ../fake_ori_data_001/videos
└── meta/                  (real directory, not symlinked)
    ├── episodes.jsonl     → ../../fake_ori_data_001/episodes.jsonl
    ├── episodes_stats.jsonl → ../../fake_ori_data_001/merged_episodes_stats.jsonl
    ├── info.json          → ../../fake_ori_data_001/merged_info.json
    └── tasks.jsonl        → ../../fake_ori_data_001/tasks.jsonl
```

### File Mapping: Pipeline → LeRobot

| LeRobot Standard (Target) | Pipeline Output (Source) |
|---------------------------|--------------------------|
| `data/` | `merged_data/` |
| `meta/info.json` | `merged_info.json` |
| `meta/episodes_stats.jsonl` | `merged_episodes_stats.jsonl` |
| `meta/episodes.jsonl` | `episodes.jsonl` |
| `meta/tasks.jsonl` | `tasks.jsonl` |
| `annotations/` | `annotations/` |
| `videos/` | `videos/` |

### Symlink Features

- **Relative paths by default** - Portable across different mount points
- **Folder-level symlinks** - For `annotations/`, `data/`, `videos/`
- **File-level symlinks** - For metadata in `meta/`
- **No data duplication** - All data stays in original location

### Help

```bash
python src/robocoin_dataset/dataloader/make_data_sym_links.py --help
```

---

## 📂 Test Data Location

All FAKE test data is generated in:
```
examples/dataloader_test/
├── fake_ori_data_001/          # FAKE pipeline data
├── fake_ori_data_002/          # FAKE pipeline data
├── symlinked_fake_ori_data_001/  # LeRobot symlinked structure
└── .gitignore                  # Excludes FAKE data from git
```

### Git Ignore

The `.gitignore` in `examples/dataloader_test/` excludes all FAKE test data:

```gitignore
fake_ori_data_*/     # All fake_ori_data_* directories (FAKE data)
symlinked_*/         # All symlinked directories
```

**Why gitignore?**
1. ✅ FAKE test data can be LARGE (thousands of files)
2. ✅ FAKE test data is REGENERATABLE (no need to version control)
3. ✅ Keeps repository clean and fast
4. ✅ Prevents accidental commits of test data

---

## 🎯 Complete Workflow Example

### Step 1: Generate FAKE Test Data

```bash
# Generate FAKE test data (2500 episodes, 3 chunks)
python scripts/dataloader/make_fake_data.py

# Output: examples/dataloader_test/fake_ori_data_001/
```

### Step 2: Create Symlinks

```bash
# Create LeRobot-compatible symlink structure
python src/robocoin_dataset/dataloader/make_data_sym_links.py \
    --source examples/dataloader_test/fake_ori_data_001

# Output: examples/dataloader_test/symlinked_fake_ori_data_001/
```

### Step 3: Verify Structure

```bash
# Check symlinks
ls -la examples/dataloader_test/symlinked_fake_ori_data_001/
ls -la examples/dataloader_test/symlinked_fake_ori_data_001/meta/

# Access data through symlinks
ls examples/dataloader_test/symlinked_fake_ori_data_001/data/chunk-000/ | head -5
cat examples/dataloader_test/symlinked_fake_ori_data_001/meta/info.json
```

### Step 4: Test Your Dataloader

```bash
# Now use the symlinked structure with your dataloader
# The LeRobot dataloader will see the standard structure
# But read from your actual pipeline data through symlinks
```

---

## 🧹 Cleanup

```bash
# Remove specific FAKE dataset
rm -rf examples/dataloader_test/fake_ori_data_001
rm -rf examples/dataloader_test/symlinked_fake_ori_data_001

# Remove ALL FAKE test data
rm -rf examples/dataloader_test/fake_ori_data_*
rm -rf examples/dataloader_test/symlinked_*
```

---

## 🔍 Troubleshooting

### Issue: "Dataset already exists"
**Solution**: The script auto-increments version numbers. You'll see a message like:
```
📝 Dataset 'fake_ori_data_001' already exists. Looking for next available version...
   ✅ Auto-incremented to: fake_ori_data_002
```

### Issue: Broken symlinks
**Solution**:
1. Ensure source directory exists
2. Use absolute paths: `--absolute` flag
3. Check file permissions

### Issue: Out of disk space
**Solution**:
1. Reduce episodes: `--episodes 100`
2. Reduce chunks: `--chunks 1`
3. Clean up old FAKE datasets: `rm -rf examples/dataloader_test/fake_ori_data_*`

### Issue: Symlinks not working on Windows
**Solution**:
1. Use absolute paths: `--absolute`
2. Or run with administrator privileges
3. Or use WSL (Windows Subsystem for Linux)

---

## 📊 Dataset Sizes

| Episodes | Chunks | Approx Size | Use Case |
|----------|--------|-------------|----------|
| 50 | 1 | ~1 MB | Quick test |
| 100 | 1 | ~2 MB | Small test |
| 500 | 1 | ~10 MB | Medium test |
| 2500 | 3 | ~50 MB | Default test |
| 10000 | 10 | ~200 MB | Large test |

*Note: Actual sizes depend on video files. Current implementation creates empty placeholder videos.*

---

## 🚨 Important Notes

1. **ALL data generated by `make_fake_data.py` is FAKE/synthetic test data**
2. **Never use FAKE data for training or production**
3. **FAKE data is for testing pipeline and dataloader functionality only**
4. **Real production data should follow the same structure but with actual content**
5. **The naming convention `fake_*` explicitly identifies test data**

---

## 📚 Additional Resources

- See inline help: `python scripts/dataloader/make_fake_data.py --help`
- See inline help: `python src/robocoin_dataset/dataloader/make_data_sym_links.py --help`
- Check `.gitignore` in `examples/dataloader_test/` for exclusion patterns

---

## 🤝 Development Notes

When creating test scenarios:
1. Always use the `fake_` prefix for test dataset names
2. Use auto-increment to avoid overwriting existing tests
3. Clean up FAKE test data when done
4. Don't commit FAKE test data to git (it's ignored)
5. Document any changes to data structure in this README
