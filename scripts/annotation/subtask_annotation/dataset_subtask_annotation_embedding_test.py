import argparse

from robocoin_dataset.annotation.subtask_annotion.dataset_subtask_annotation_embedding import (
    DatasetSubtaskAnnotationEmbedding,
)
from robocoin_dataset.utils.logger import setup_logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_file_path", type=str, required=True)

    parser.add_argument("--log_dir", type=str, default="./logs")
    args = parser.parse_args()

    logger = setup_logger(name="dataset_subtask_annotation", log_dir=args.log_dir)
    dataset_subtask_annotator = DatasetSubtaskAnnotationEmbedding(args.db_file_path, logger=logger)
    dataset_subtask_annotator.embed_subtask_annotation()


"""Usage:
python scripts/annotation/subtask_annotation/dataset_subtask_annotation_embedding.py --db_file_path ./db/datasets_new.db --log_dir ./logs  
"""
