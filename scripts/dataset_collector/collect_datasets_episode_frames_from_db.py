#!/usr/bin/env python3
#  collect_episode_frames_from_db.py
import sys
import logging
from datetime import datetime
from pathlib import Path
from multiprocessing import cpu_count
import yaml
from tqdm.contrib.concurrent import thread_map

from robocoin_dataset.statistic.episode_frames_collector_factory import EpisodeFramesCollectorFactory

import logging, sys
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s | %(levelname)s | %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])

# ----------- 数据库 -----------
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB as Dataset, EpisodeFrameDB as EpisodeFrame

# ----------- 日志 -----------
logger = logging.getLogger("COLLECT_EPISODE_FRAMES_DB")
logger.handlers.clear()
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
log_dir = Path("./outputs/logs")
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"collect_frames_{datetime.now():%Y%m%d_%H%M%S}.log"
handler = logging.FileHandler(log_file, encoding="utf-8")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def collect_episode_frames_from_db(
    db_path: Path,
    device_model: str = None,
    concurrent_workers: int = None,
):
    if concurrent_workers is None:
        concurrent_workers = min(8, cpu_count() * 2)

    db_instance = DatasetDatabase(db_path)

    # 1. 主线程一次性捞完数据集
    with db_instance.with_session() as session:
        q = session.query(Dataset)
        if device_model:
            q = q.filter(Dataset.device_model == device_model)
        datasets = q.all()

    if not datasets:
        logger.warning("No datasets found (filter: device_model=%s)", device_model)
        return
    logger.info("Ready to process %s datasets", len(datasets))

    # 2. 路径预检：放主线程，避免 1000 个线程同时打日志
    valid_datasets = []
    for ds in datasets:
        if not Path(ds.yaml_file_path).exists():
            logger.error("[%s] YAML not found: %s", ds.dataset_uuid, ds.yaml_file_path)
            continue
        if not Path(ds.yaml_file_path).exists():
            logger.error("[%s] Dir not found: %s", ds.dataset_uuid, ds.yaml_file_path)
            continue
        valid_datasets.append(ds)
    logger.info("After path filter: %s datasets", len(valid_datasets))

    # 3. 处理单条数据集
    def process_dataset(ds: Dataset) -> str:
        uuid = ds.dataset_uuid
        yaml_path = Path(ds.yaml_file_path)
        ds_dir   = Path(ds.yaml_file_path).parent

        # 采集帧数
        try:
            collector = EpisodeFramesCollectorFactory().create_collector(yaml_path, ds_dir)
            frames = collector.collect()
        except Exception as e:
            logger.exception("[%s] Collection error: %s", uuid, e)
            return uuid

        if not frames:
            logger.warning("[%s] No frames collected", uuid)
            return uuid

        # 4. 写库：删旧 → 批量插新 → commit
        with db_instance.with_session() as sess:
            try:
                sess.query(EpisodeFrame).filter_by(dataset_uuid=uuid).delete()
                sess.bulk_save_objects(
                    [EpisodeFrame(dataset_uuid=uuid, episode_index=i, frames_num=n)
                     for i, n in enumerate(frames)]
                )
                sess.commit()
                logger.info("[%s] ✅ Saved %s episodes", uuid, len(frames))
            except Exception as e:
                sess.rollback()
                logger.exception("[%s] ❌ DB save failed: %s", uuid, e)
        return uuid

    # 5. 进度条
    thread_map(
        process_dataset,
        valid_datasets,
        max_workers=concurrent_workers,
        desc="Processing",
        unit="ds",
    )


# ----------- CLI -----------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Collect episode frames from database.")
    parser.add_argument("--db_path", type=Path, required=True, help="SQLite db file")
    parser.add_argument("--device_model", type=str, help="Filter by device_model")
    parser.add_argument("--concurrent_workers", type=int, help="Defaults to min(8, 2*CPU)")
    args = parser.parse_args()

    collect_episode_frames_from_db(
        db_path=args.db_path,
        device_model=args.device_model,
        concurrent_workers=args.concurrent_workers,
    )


if __name__ == "__main__":
    main()
    
    
"""
python ~/robocoin-dataset/scripts/dataset_collector/collect_datasets_episode_frames_from_db.py \
       --db_path /home/adminpc1/robocoin-dataset/db/datasets.db\
       --device_model unitree_g1\
       --concurrent_workers 4
"""