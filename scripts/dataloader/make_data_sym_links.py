#!/usr/bin/env python3
"""
Simple wrapper script to call the make_data_sym_links module from src/robocoin_dataset/dataloader.

This script provides an easy-to-run entry point in the scripts/dataloader directory
that calls the actual implementation in src/robocoin_dataset/dataloader/make_data_sym_links.py

USAGE:
  # Use default target (creates '<source_name>_symlink' next to source):
  python scripts/dataloader/make_data_sym_links.py --source examples/dataloader_test/fake_ori_data_001
  python scripts/dataloader/make_data_sym_links.py -s examples/dataloader_test/fake_ori_data_001

  # Specify custom target directory:
  python scripts/dataloader/make_data_sym_links.py --source /examples/dataloader_test/fake_ori_data_001 --target examples/dataloader_test/fake_ori_data_001_symlink
  python scripts/dataloader/make_data_sym_links.py -s /examples/dataloader_test/fake_ori_data_001 -t examples/dataloader_test/fake_ori_data_001_symlink

  # Create symlinks with absolute paths instead of relative:
  python scripts/dataloader/make_data_sym_links.py -s /path/to/source/data --absolute

  # Skip missing source files instead of raising errors:
  python scripts/dataloader/make_data_sym_links.py -s /path/to/source/data --skip-missing

EXAMPLE WORKFLOW:
  # Step 1: Generate fake test data
  python scripts/dataloader/make_fake_data.py

  # Step 2: Create LeRobot-compatible symlink structure
  python scripts/dataloader/make_data_sym_links.py --source examples/dataloader_test/fake_ori_data_001
"""

import sys
from pathlib import Path

# Add src directory to Python path to import the module
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
src_dir = project_root / "src"

if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# Import and run the main function from the actual implementation
if __name__ == "__main__":
    from robocoin_dataset.dataloader.make_data_sym_links import main
    sys.exit(main())
