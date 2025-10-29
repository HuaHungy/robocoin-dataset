import argparse

from robocoin_dataset.annotation.subtask_annotion.dataset_subtask_annotation_optimization import (
    DatasetSubtaskAnnotationOptimization,
)
from robocoin_dataset.utils.logger import setup_logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_file_path", type=str, required=True)

    parser.add_argument("--log_dir", type=str, default="./logs")
    parser.add_argument("--ds_api_key", type=str, default="sk-a3c8736391cf43809957329f28cac287")
    args = parser.parse_args()

    logger = setup_logger(name="dataset_subtask_annotation", log_dir=args.log_dir)
    dataset_subtask_annotator = DatasetSubtaskAnnotationOptimization(
        args.db_file_path, logger=logger, ds_api_key=args.ds_api_key
    )
    dataset_subtask_annotator.optimize_subtask_annotation()


"""Usage:
python scripts/annotation/subtask_annotation/dataset_subtask_annotation_optimization.py --db_file_path ./db/datasets_new.db --log_dir ./logs  
"""
