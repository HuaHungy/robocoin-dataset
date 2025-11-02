import argparse

from robocoin_dataset.data_merge.data_merger import DataMerger

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_file_path", type=str, required=True)
    args = parser.parse_args()

    data_merger = DataMerger(args.db_file_path)
    data_merger.merge_data_one_dataset()

"""Usage:
python scripts/data_merge/data_merge.py --db_file_path ./db/datasets_new.db
"""
