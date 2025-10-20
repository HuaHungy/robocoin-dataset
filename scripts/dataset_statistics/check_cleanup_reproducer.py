#!/usr/bin/env python3
"""
Quick reproducer to instantiate a LeRobotFormatConverter and run convert(is_test=False)
to trigger dataset creation and cleanup logic. This script runs in a small temp folder.
"""
import logging
from pathlib import Path
import tempfile

from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverterFactory,
)

# Build a minimal fake converter config that matches expectations
converter_config = {
    "fps": 15,
    "features": {
        # minimal features: image feature required
    },
}

logger = logging.getLogger("test_cleanup")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logger.addHandler(handler)

# Use an existing converter module/class that expects minimal inputs.
# For safety we'll call create_converter but not actually perform heavy conversion.

def main():
    tmp_out = Path(tempfile.mkdtemp())
    # We need a valid converter module and class; use an existing h5 converter class
    module_path = "robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5"
    class_name = "LerobotFormatConverterHdf5"

    dataset_path = "."  # current repo root (exists)
    try:
        converter = LerobotFormatConverterFactory.create_converter(
            dataset_path=dataset_path,
            device_model="test",
            output_path=tmp_out,
            converter_config={"fps": 15, "features": {}},
            converter_module_path=module_path,
            converter_class_name=class_name,
            repo_id="test/repo",
            video_backend="pyav",
            image_writer_processes=1,
            image_writer_threads=1,
            logger=logger,
        )
        # call convert in test mode to avoid writing
        for _ in converter.convert(is_test=True):
            pass
    except Exception as e:
        logger.error(f"Reproducer error: {e}")

if __name__ == '__main__':
    main()
