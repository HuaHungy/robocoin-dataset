'''
Make a fake dataset record for dataloader detection testing

USAGE:
python scripts/dataloader/make_fake_db_item.py \
    --db examples/dataloader_test/datasets_new.db \
    --dataset-root examples/dataloader_test/fake_ori_data_001_symlink \
    --name fake_ori_data_001 \
    --eef dual_arm
'''

import argparse
import json
import sys
import uuid
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, TaskStatus


def read_meta_info(dataset_root: Path) -> dict:
    meta_file = dataset_root / "meta" / "info.json"
    if not meta_file.exists():
        return {}
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def count_total_episodes(dataset_root: Path, meta: dict) -> int:
    """Best-effort count of episodes for a LeRobot-style dataset root.

    Priority:
    1) meta/info.json -> key "total_episodes"
    2) Count parquet files: data/chunk-*/episode_*.parquet
       or fallback to data/episode_*.parquet
    3) meta/episodes.jsonl line count (if present)
    """
    try:
        total = meta.get("total_episodes")
        if isinstance(total, int) and total >= 0:
            return total
    except Exception:
        pass

    data_dir = dataset_root / "data"
    if data_dir.exists():
        try:
            # Prefer chunked layout
            chunk_dirs = [d for d in data_dir.iterdir() if d.is_dir() and d.name.startswith("chunk-")]
            if chunk_dirs:
                count = 0
                for chunk_dir in chunk_dirs:
                    count += len(list(chunk_dir.glob("episode_*.parquet")))
                if count > 0:
                    return count
            # Fallback: flat layout
            flat = len(list(data_dir.glob("episode_*.parquet")))
            if flat > 0:
                return flat
        except Exception:
            pass

    # Fallback: meta/episodes.jsonl line count
    episodes_jsonl = dataset_root / "meta" / "episodes.jsonl"
    if episodes_jsonl.exists():
        try:
            with open(episodes_jsonl, encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            pass

    return 0


def upsert_fake_dataset(
    db_path: Path,
    dataset_root: Path,
    dataset_name: str | None,
    dataset_uuid_str: str | None,
    end_effector_type: str,
) -> str:
    db = DatasetDatabase(db_path)
    meta = read_meta_info(dataset_root)

    ds_name = dataset_name or dataset_root.name
    ds_uuid = dataset_uuid_str or str(uuid.uuid4())

    with db.with_session() as session:
        # 1) delete any existing rows with dataset_name like 'fake_ori_data_%'
        session.query(DatasetDB).filter(
            DatasetDB.dataset_name.like("fake_ori_data_%")
        ).delete(synchronize_session=False)
        session.commit()

        # 2) insert a new item with required fields
        item = DatasetDB(
            dataset_name=ds_name,
            dataset_uuid=ds_uuid,
            end_effector_type=end_effector_type,
        )
        session.add(item)

        # Core paths (keep for downstream usage)
        item.data_path = str(dataset_root)
        item.convert_path = str(dataset_root)

        # Minimal base metadata
        item.device_model = "robot"
        item.device_model_version = "default_version"
        item.operation_platform_height = 77.2
        item.yaml_file_path = str(dataset_root)

        # Pipeline fields for successful baseline
        item.convert_test_status = TaskStatus.COMPLETED
        item.convert_test_version = 1
        item.convert_status = TaskStatus.COMPLETED
        item.convert_version_ps = 1
        item.convert_version = 1

        episodes_count = count_total_episodes(dataset_root, meta)
        item.total_episodes = episodes_count
        item.converted_episodes = episodes_count
        item.skipped_episodes = 0
        item.convert_err_msg = None

        item.sa_dpp_status = TaskStatus.COMPLETED
        item.sa_dpp_version_ps = 1
        item.sa_dpp_version = 1
        item.sa_dpp_err_msg = None

        item.sim_replay_status = TaskStatus.COMPLETED
        item.sim_replay_version_ps = 1
        item.sim_replay_version = 1
        item.sim_replay_error_msg = None

        item.motion_annotation_status = TaskStatus.COMPLETED
        item.motion_annotation_version_ps = 1
        item.motion_annotation_version = 1
        item.motion_annotation_err_msg = None

        item.video_hash_status = None  # not requested to COMPLETE
        item.video_hash_version_ps = 1
        item.video_hash_version = 1
        item.video_hash_err_msg = None

        item.video_match_status = TaskStatus.COMPLETED
        item.video_match_version_ps = 1
        item.video_match_version = 1
        item.video_match_err_msg = None

        # MUST SET: completed annotation subtasks and data merge
        item.video_ori_subtask_annotation_status = TaskStatus.COMPLETED
        item.video_ori_subtask_annotation_version_ps = 1
        item.video_ori_subtask_annotation_version = 1
        item.video_ori_subtask_annotation_err_msg = None

        item.video_opt_subtask_annotation_status = TaskStatus.COMPLETED
        item.video_opt_subtask_annotation_version_ps = 1
        item.video_opt_subtask_annotation_version = 1
        item.video_opt_subtask_annotation_err_msg = None

        item.video_embed_subtask_annotation_status = TaskStatus.COMPLETED
        item.video_embed_subtask_annotation_version_ps = 1
        item.video_embed_subtask_annotation_version = 1
        item.video_embed_subtask_annotation_err_msg = None

        item.scene_annotation_status = TaskStatus.COMPLETED
        item.scene_annotation_version_ps = 1
        item.scene_annotation_version = 1
        item.scene_annotation_err_msg = None

        item.data_merge_status = TaskStatus.COMPLETED
        item.data_merge_version_ps_sta = 1
        item.data_merge_version_ps_sa = 1
        item.data_merge_version_ps_dpp = 1
        item.data_merge_version = 1
        item.data_merge_err_msg = None

        item.data_loader_detection_status = None
        item.data_loader_detection_version_ps = None
        item.data_loader_detection_version = None
        item.data_loader_detection_err_msg = None

        item.ms_upload_status = None
        item.ms_upload_version_ps = None
        item.ms_upload_version = None
        item.ms_upload_err_msg = None

        item.huggingface_upload_status = None
        item.huggingface_upload_version_ps = None
        item.huggingface_upload_version = None
        item.huggingface_upload_err_msg = None

        item.dataset_info_sync_status = None
        item.dataset_info_sync_version_ps = None
        item.dataset_info_sync_version = None
        item.dataset_info_sync_err_msg = None

        session.commit()

    return ds_uuid


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Insert or update a fake dataset record for dataloader detection testing",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("examples/dataloader_test/datasets_new.db").absolute(),
        help="Path to SQLite database file",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("examples/dataloader_test/fake_ori_data_001_symlink").absolute(),
        help="Path to lerobot-style dataset root (with meta/, videos/, data/)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Dataset name to store (defaults to dataset root directory name)",
    )
    parser.add_argument(
        "--uuid",
        type=str,
        default=None,
        help="Dataset UUID to store (defaults to a newly generated UUID4)",
    )
    parser.add_argument(
        "--eef",
        type=str,
        default="unknown",
        help="End effector type (required by schema, default: unknown)",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    db_path: Path = args.db.expanduser().absolute()
    dataset_root: Path = args.dataset_root.expanduser().absolute()

    if not dataset_root.exists():
        print(f"Dataset root not found: {dataset_root}", file=sys.stderr)
        return 2

    ds_uuid = upsert_fake_dataset(
        db_path=db_path,
        dataset_root=dataset_root,
        dataset_name=args.name,
        dataset_uuid_str=args.uuid,
        end_effector_type=args.eef,
    )

    print("OK")
    print(f"db: {db_path}")
    print(f"dataset_root: {dataset_root}")
    print(f"dataset_uuid: {ds_uuid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
