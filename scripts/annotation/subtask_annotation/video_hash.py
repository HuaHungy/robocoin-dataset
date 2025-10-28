import argparse

from robocoin_dataset.annotation.subtask_annotion.video_hash import VideoHash

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_file_path", type=str, required=True)
    args = parser.parse_args()

    video_hasher = VideoHash(args.db_file_path)
    video_hasher.sync_video_hash_status()
    video_hasher.compute_video_hashes_one_dataset()

"""Usage:
python scripts/annotation/subtask_annotation/video_hash.py --db_file_path ./db/datasets_new.db
"""
