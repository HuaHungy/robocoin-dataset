# Dataloader Scripts

Tools for testing and validating LeRobot dataset compatibility.

## 📁 Files

### `dataloader_test.py`
**Main CLI** - Test datasets with local/server/client modes
```bash
python scripts/dataloader/dataloader_test.py --local
```
👉 **See:** [DATALOADER_TEST_USAGE.md](./DATALOADER_TEST_USAGE.md) for complete guide

### `make_data_sym_links.py`
Creates LeRobot-style symlink structures for datasets

### `make_fake_data.py`
Generates fake datasets for testing

### `make_fake_db_item.py`
Creates fake database entries for testing

## 📚 Documentation

- **[DATALOADER_TEST_USAGE.md](./DATALOADER_TEST_USAGE.md)** - Complete usage guide with examples
- **[../DATALOADER_TEST_STATUS_FIX.md](../../DATALOADER_TEST_STATUS_FIX.md)** - Status checking fix details

## 🚀 Quick Start

```bash
# Test all datasets locally
python scripts/dataloader/dataloader_test.py --local --db your.db

# Distributed testing: Start server
python scripts/dataloader/dataloader_test.py --server --host 0.0.0.0

# Distributed testing: Start worker
python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100
```

## ⚠️ Requirements

Datasets must meet strict criteria:
- ✅ `data_merge_status = COMPLETED`
- ✅ `convert_status = COMPLETED`
- ✅ `convert_path` populated and exists
