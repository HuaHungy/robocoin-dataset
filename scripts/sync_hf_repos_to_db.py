#!/usr/bin/env python3
"""
同步 HuggingFace 仓库到数据库状态

从 HuggingFace namespace=RoboCOIN/ 下获取所有 repo name，与数据库中的 convert_path 进行匹配，
更新匹配记录的 huggingface_upload_status 和 ms_upload_status 为 COMPLETED，
其他记录设置为 PENDING，并生成 path.json 文件。

使用方法:
    python scripts/sync_hf_repos_to_db.py [--db /path/to/db]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "src"))

from huggingface_hub import HfApi  # noqa: E402

from robocoin_dataset.database.database import DatasetDatabase  # noqa: E402
from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB, TaskStatus  # noqa: E402

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# HuggingFace 命名空间
HF_NAMESPACE = "RoboCOIN"


def get_hf_repo_names(namespace: str, token: str = None) -> list[str]:
    """从 HuggingFace 获取指定命名空间下的所有仓库名称"""
    logger.info(f"正在从 HuggingFace 获取 {namespace} 命名空间下的仓库...")

    try:
        api = HfApi(token=token)
        repos = api.list_datasets(author=namespace)

        repo_names = []
        for repo in repos:
            repo_id = repo.id
            if "/" in repo_id:
                repo_name = repo_id.split("/", 1)[1]
                repo_names.append(repo_name)
            else:
                repo_names.append(repo_id)

        logger.info(f"从 HuggingFace 获取到 {len(repo_names)} 个仓库")
        return repo_names

    except Exception as e:
        logger.error(f"获取 HuggingFace 仓库失败: {e}")
        raise


def match_and_update_db(
    db_path: Path, hf_repo_names: list[str]
) -> tuple[list[str], list[str], set[str]]:
    """
    匹配数据库中的 convert_path 与 HuggingFace 仓库名称，并更新状态

    Args:
        db_path: 数据库文件路径
        hf_repo_names: HuggingFace 仓库名称列表

    Returns:
        tuple: (matched_uuids, hard_link_paths, matched_repo_names)
            - matched_uuids: 匹配记录的 UUID 列表
            - hard_link_paths: 对应的 hard_link_path 列表
            - matched_repo_names: 匹配上的仓库名称集合
    """
    logger.info("开始匹配和更新数据库...")

    db = DatasetDatabase(db_path)
    hf_repo_set = set(hf_repo_names)

    matched_uuids = []
    matched_records = []
    matched_repo_names = set()

    with db.with_session() as session:
        # 查询所有数据集记录
        all_datasets = session.query(DatasetDB).all()
        logger.info(f"数据库中共有 {len(all_datasets)} 条数据集记录")

        # 匹配 convert_path 的末尾字符串
        for dataset in all_datasets:
            if not dataset.convert_path:
                continue

            # 获取 convert_path 的末尾字符串（最后一部分路径）
            convert_path_end = Path(dataset.convert_path).name

            # 完全匹配检查
            if convert_path_end in hf_repo_set:
                matched_uuids.append(dataset.dataset_uuid)
                matched_records.append(dataset)
                matched_repo_names.add(convert_path_end)
                logger.debug(
                    f"匹配: convert_path={dataset.convert_path}, "
                    f"end={convert_path_end}, uuid={dataset.dataset_uuid}"
                )

        logger.info(f"找到 {len(matched_records)} 条匹配记录")

        # 更新匹配记录的状态为 COMPLETED
        for dataset in matched_records:
            dataset.huggingface_upload_status = TaskStatus.COMPLETED
            dataset.ms_upload_status = TaskStatus.COMPLETED

        # 更新其他所有记录的状态为 PENDING
        matched_uuids_set = set(matched_uuids)
        for dataset in all_datasets:
            if dataset.dataset_uuid not in matched_uuids_set:
                dataset.huggingface_upload_status = TaskStatus.PENDING
                dataset.ms_upload_status = TaskStatus.PENDING

        # 提交更改
        session.commit()
        logger.info(
            f"已更新 {len(matched_records)} 条记录为 COMPLETED，"
            f"其余 {len(all_datasets) - len(matched_records)} 条记录为 PENDING"
        )

        # 查询 dataset_hard_link 表获取 hard_link_path
        hard_link_paths = []
        if matched_uuids:
            hard_link_records = (
                session.query(DatasetHardLinkDB)
                .filter(DatasetHardLinkDB.dataset_uuid.in_(matched_uuids))
                .all()
            )

            hard_link_paths.extend(
                record.hard_link_path
                for record in hard_link_records
                if record.hard_link_path
            )

            logger.info(f"从 dataset_hard_link 表获取到 {len(hard_link_paths)} 条 hard_link_path")

    return matched_uuids, hard_link_paths, matched_repo_names


def save_path_json(hard_link_paths: list[str], output_path: Path) -> None:
    """保存 hard_link_path 列表到 JSON 文件"""
    logger.info(f"保存 {len(hard_link_paths)} 条路径到 {output_path}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(hard_link_paths, f, indent=2, ensure_ascii=False)

    logger.info(f"✅ 已保存: {output_path}")


def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(
        description="同步 HuggingFace 仓库到数据库状态",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db",
        type=str,
        default="/mnt/db/datasets_new.db",
        help="数据库文件路径 (默认: /mnt/db/datasets_new.db)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="HuggingFace token (可选，用于访问私有仓库)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出 JSON 文件路径 (默认: 项目根目录/path.json)",
    )

    args = parser.parse_args()

    db_path = Path(args.db).expanduser().absolute()
    if not db_path.exists():
        logger.error(f"数据库文件不存在: {db_path}")
        sys.exit(1)

    # 确定输出路径
    if args.output:
        output_path = Path(args.output).expanduser().absolute()
    else:
        output_path = project_root / "path.json"

    logger.info("=" * 60)
    logger.info("同步 HuggingFace 仓库到数据库状态")
    logger.info("=" * 60)
    logger.info(f"数据库路径: {db_path}")
    logger.info(f"输出路径: {output_path}")
    logger.info(f"HuggingFace 命名空间: {HF_NAMESPACE}")
    logger.info("")

    try:
        # 步骤 1: 获取 HuggingFace 仓库名称
        logger.info("步骤 1: 获取 HuggingFace 仓库名称")
        logger.info("-" * 60)
        hf_repo_names = get_hf_repo_names(HF_NAMESPACE, token=args.token)
        logger.info("")

        # 步骤 2: 匹配和更新数据库
        logger.info("步骤 2: 匹配和更新数据库")
        logger.info("-" * 60)
        matched_uuids, hard_link_paths, matched_repo_names = match_and_update_db(
            db_path, hf_repo_names
        )
        logger.info("")

        # 步骤 3: 计算并打印缺失记录
        logger.info("步骤 3: 分析缺失记录")
        logger.info("-" * 60)
        hf_repo_set = set(hf_repo_names)
        missing_repos = sorted(hf_repo_set - matched_repo_names)

        if missing_repos:
            logger.warning(f"⚠️  发现 {len(missing_repos)} 个 HuggingFace 仓库在数据库中没有匹配记录:")
            for repo_name in missing_repos:
                logger.warning(f"  - {repo_name}")
        else:
            logger.info("✅ 所有 HuggingFace 仓库都在数据库中有匹配记录")
        logger.info("")

        # 步骤 4: 保存路径到 JSON 文件
        logger.info("步骤 4: 保存路径到 JSON 文件")
        logger.info("-" * 60)
        save_path_json(hard_link_paths, output_path)
        logger.info("")

        # 汇总报告
        logger.info("=" * 60)
        logger.info("汇总报告")
        logger.info("=" * 60)
        logger.info(f"HuggingFace 仓库数量: {len(hf_repo_names)}")
        logger.info(f"匹配的记录数: {len(matched_uuids)}")
        logger.info(f"缺失的记录数: {len(missing_repos)}")
        logger.info(f"hard_link_path 数量: {len(hard_link_paths)}")
        logger.info(f"输出文件: {output_path}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
