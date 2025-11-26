import argparse

from robocoin_dataset.data_merge.data_merger import merge_dataset_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_path", type=str)

    args = parser.parse_args()

    patch_features = ["subtask_annotation", "scene_annotation", "motion_annotation", "state_action"]

    merge_feature = "merged"

    merge_dataset_data(args.repo_path, patch_features, merge_feature)

"""Usage:
python scripts/data_merge/data_merge_test.py
"""
