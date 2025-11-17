#!/usr/bin/env python3
# 检查Hub上已上传数据集的visualize_check_status状态
# python scripts/hub_upload/check_visualize_status.py --db-path /mnt/db/datasets_new.db

import argparse
import sys
import warnings
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "src"))

import requests  # noqa: E402
from huggingface_hub import HfApi  # noqa: E402

from robocoin_dataset.database.database import DatasetDatabase  # noqa: E402
from robocoin_dataset.database.models import DatasetDB, TaskStatus  # noqa: E402

warnings.filterwarnings("ignore", message="pkg_resources is deprecated as an API")


def _return_hub_existing_name_list(namespace: str = "RoboCOIN") -> tuple[list[str], list[str]]:
    """返回HF和MS上所有的数据集名称列表"""
    # 获取HuggingFace repos
    api = HfApi()
    repos = api.list_datasets(author=namespace)
    hf_names = [repo.id.split("/", 1)[1] if "/" in repo.id else repo.id for repo in repos]

    # 获取ModelScope repos
    ms_names = []
    page = 1
    while True:
        resp = requests.get(
            "https://www.modelscope.cn/api/v1/datasets",
            params={"owner": namespace, "PageNumber": page, "PageSize": 50},
            timeout=10
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        datasets = data.get("Data", [])
        ms_names.extend([d.get("Name", "") for d in datasets if d.get("Name")])
        if len(ms_names) >= data.get("TotalCount", 0):
            break
        page += 1

    return hf_names, ms_names


def _check_name_list_consistency(hf_names: list[str], ms_names: list[str], db_path: str) -> None:
    """检查数据库中对应数据集的visualize_check_status，输出不是COMPLETED的UUID"""
    db = DatasetDatabase(Path(db_path))

    print("\n=== HuggingFace 平台 visualize_check_status 未完成的数据集 ===")
    with db.with_session() as session:
        for name in hf_names:
            datasets = session.query(DatasetDB).filter(DatasetDB.convert_path.like(f"%/{name}")).all()
            for ds in datasets:
                if ds.visualize_check_status != TaskStatus.COMPLETED:
                    print(f"{ds.dataset_uuid}")

    print("\n=== ModelScope 平台 visualize_check_status 未完成的数据集 ===")
    with db.with_session() as session:
        for name in ms_names:
            datasets = session.query(DatasetDB).filter(DatasetDB.convert_path.like(f"%/{name}")).all()
            for ds in datasets:
                if ds.visualize_check_status != TaskStatus.COMPLETED:
                    print(f"{ds.dataset_uuid}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default="RoboCOIN")
    parser.add_argument("--db-path", default="/mnt/db/datasets_new.db")
    args = parser.parse_args()

    hf_names, ms_names = _return_hub_existing_name_list(args.namespace)
    _check_name_list_consistency(hf_names, ms_names, args.db_path)


if __name__ == "__main__":
    main()
