import argparse
import json
from pathlib import Path

import tqdm

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="compute episode num")
    parser.add_argument("--db_file_path", type=str, default="")
    args = parser.parse_args()
    db = DatasetDatabase(Path(args.db_file_path))
    total_episode_num = 0
    repo_paths = {}

    with db.with_session() as session:
        session.query(DatasetDB.convert_path)
        items = session.query(DatasetDB).all()
        repo_paths = {item.dataset_uuid: item.convert_path for item in items}
        repo_path_unique = set(repo_paths.values())

    repo_episodes_num_uuid = {}
    repo_episodes_num_path = {}
    for uuid, path in tqdm.tqdm(
        repo_paths.items(), desc="compute episode num", total=len(items), unit="dataset"
    ):
        if not path:
            continue
        info_file_path = Path(path) / "meta/info.json"
        if not info_file_path.exists():
            continue
        with info_file_path.open("r") as f:
            info = json.load(f)
            total_episodes = info["total_episodes"]
            repo_episodes_num_path[path] = total_episodes
            repo_episodes_num_uuid[uuid] = total_episodes

    with db.with_session() as session:
        for uuid, num in repo_episodes_num_uuid.items():
            session.query(DatasetDB).filter(DatasetDB.dataset_uuid == uuid).update(
                {"total_episodes": num}
            )
        session.commit()

    total_episode_num = sum(repo_episodes_num_path.values())

    print(f"total_episode_num: {total_episode_num}")
else:
    pass
