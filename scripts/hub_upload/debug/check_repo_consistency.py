#!/usr/bin/env python3
"""
Hub Repo Consistency Checker - Hub平台仓库一致性检查

功能：
  比较 Hub 平台（Hugging Face/ModelScope）上的 RoboCOIN repos 与数据库中标记为 COMPLETED 的数据集
  1. 读取指定平台命名空间下的所有 repo 名字
  2. 读取数据库中对应平台 upload_status=COMPLETED 的 convert_path 文件夹名
  3. 比较差异，检测不一致情况

使用：
  # 检查 Hugging Face（默认）
  python scripts/hub_upload/check_repo_consistency.py

  # 检查 ModelScope
  python scripts/hub_upload/check_repo_consistency.py --platform modelscope

  # 同时检查两个平台
  python scripts/hub_upload/check_repo_consistency.py --platform all --verbose

  # 带 token
  python scripts/hub_upload/check_repo_consistency.py --platform huggingface --token YOUR_TOKEN

参数：
  --platform {huggingface,modelscope,all}  要检查的平台 (默认: huggingface)
  --namespace NAMESPACE                     命名空间 (默认: RoboCOIN)
  --token TOKEN                             认证token（访问私有repos）
  --db-path DB_PATH                         数据库路径 (默认: /mnt/db/datasets_new.db)
  --verbose, -v                             显示详细信息

退出码：
  0 - 完全一致  1 - 发现不一致  2 - 执行失败

注意：
  - HuggingFace查询 huggingface_upload_status 字段
  - ModelScope查询 ms_upload_status 字段
  - 使用 --platform all 时两个平台共用token，如需不同token请分开运行
  - ModelScope使用web API通过owner参数筛选（速度快）
  - 如ModelScope API失败会返回空列表并继续运行
"""

import argparse
import logging
import sys
import warnings
from enum import Enum
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "src"))

from huggingface_hub import HfApi  # noqa: E402

from robocoin_dataset.database.database import DatasetDatabase  # noqa: E402
from robocoin_dataset.database.models import DatasetDB, TaskStatus  # noqa: E402

# 忽略 modelscope 的 pkg_resources 废弃警告
warnings.filterwarnings("ignore", message="pkg_resources is deprecated as an API")


class HubPlatform(str, Enum):
    """Hub 平台枚举"""
    HUGGINGFACE = "huggingface"
    MODELSCOPE = "modelscope"
    ALL = "all"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_hf_repos(namespace: str, token: str = None) -> list[str]:
    """
    从 Hugging Face 获取指定命名空间下的所有数据集 repo 名字

    Args:
        namespace: Hugging Face 命名空间/用户名
        token: Hugging Face token（可选）

    Returns:
        repo 名字列表（不包含命名空间前缀）
    """
    logger.info(f"正在从 Hugging Face 获取 {namespace} 命名空间下的所有 repos...")

    try:
        api = HfApi(token=token)

        # 获取指定用户/组织的所有数据集
        repos = api.list_datasets(author=namespace)

        # 提取 repo 名称（去掉命名空间前缀）
        repo_names = []
        for repo in repos:
            repo_id = repo.id  # 格式: "namespace/repo_name"
            if "/" in repo_id:
                repo_name = repo_id.split("/", 1)[1]
                repo_names.append(repo_name)
            else:
                repo_names.append(repo_id)

        logger.info(f"从 Hugging Face 获取到 {len(repo_names)} 个 repos")
        return repo_names

    except Exception as e:
        logger.error(f"获取 Hugging Face repos 失败: {e}")
        raise


def get_ms_repos(namespace: str, token: str = None) -> list[str]:
    """
    从 ModelScope 获取指定命名空间下的所有数据集 repo 名字

    使用 ModelScope web API 直接查询指定 owner 的数据集，支持分页

    Args:
        namespace: ModelScope 命名空间/用户名
        token: ModelScope token（可选，当前未使用）

    Returns:
        repo 名字列表（不包含命名空间前缀）
    """
    import requests

    logger.info(f"正在从 ModelScope 获取 {namespace} 命名空间下的所有 repos...")

    try:
        # 使用 ModelScope web API 查询特定 owner 的数据集
        url = "https://www.modelscope.cn/api/v1/datasets"

        all_repo_names = []
        page_number = 1
        page_size = 50  # 每页获取50个（最大值）

        while True:
            params = {
                "owner": namespace,
                "PageNumber": page_number,
                "PageSize": page_size,
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code != 200:
                logger.error(f"ModelScope API 返回错误状态码: {response.status_code}")
                if page_number == 1:
                    logger.warning(f"ModelScope 查询失败，返回空列表。建议手动验证 {namespace} 下的数据集。")
                    return []
                # 如果不是第一页失败，返回已获取的数据
                logger.warning(f"第 {page_number} 页查询失败，返回已获取的 {len(all_repo_names)} 个数据集")
                break

            data = response.json()

            # 提取数据集列表
            datasets = data.get("Data", [])

            for dataset in datasets:
                # 获取数据集名称
                repo_name = dataset.get("Name", "")
                if repo_name:
                    all_repo_names.append(repo_name)

            # 检查是否还有更多数据
            total_count = data.get("TotalCount", 0)
            current_count = len(all_repo_names)

            logger.debug(f"已获取 {current_count}/{total_count} 个数据集")

            if current_count >= total_count:
                break

            page_number += 1

        logger.info(f"从 ModelScope 获取到 {len(all_repo_names)} 个 {namespace} 的 repos")
        return all_repo_names

    except requests.exceptions.RequestException as e:
        logger.error(f"ModelScope API 请求失败: {e}")
        logger.warning(f"ModelScope 查询失败，返回空列表。建议手动验证 {namespace} 下的数据集。")
        return []
    except Exception as e:
        logger.error(f"获取 ModelScope repos 失败: {e}")
        logger.warning(f"ModelScope 查询失败，返回空列表。建议手动验证 {namespace} 下的数据集。")
        return []


def get_hub_repos(
    platform: HubPlatform, namespace: str, token: str = None
) -> list[str]:
    """
    从指定 Hub 平台获取 repos

    Args:
        platform: Hub 平台（huggingface 或 modelscope）
        namespace: 命名空间/用户名
        token: 认证 token（可选）

    Returns:
        repo 名字列表
    """
    if platform == HubPlatform.HUGGINGFACE:
        return get_hf_repos(namespace, token)
    if platform == HubPlatform.MODELSCOPE:
        return get_ms_repos(namespace, token)
    raise ValueError(f"不支持的平台: {platform}")


def get_db_completed_datasets(db_path: str, platform: HubPlatform) -> list[str]:
    """
    从数据库获取指定平台 upload_status 为 COMPLETED 的数据集的 convert_path 结尾文件夹名称

    Args:
        db_path: 数据库文件路径
        platform: Hub 平台（huggingface 或 modelscope）

    Returns:
        convert_path 结尾文件夹名称列表
    """
    # 根据平台选择对应的状态字段
    if platform == HubPlatform.HUGGINGFACE:
        status_attr = DatasetDB.huggingface_upload_status
    elif platform == HubPlatform.MODELSCOPE:
        status_attr = DatasetDB.ms_upload_status
    else:
        raise ValueError(f"不支持的平台: {platform}")

    logger.info(f"正在从数据库 {db_path} 读取 {platform.value} 平台 COMPLETED 状态的数据集...")

    try:
        db = DatasetDatabase(Path(db_path))

        with db.with_session() as session:
            # 查询对应平台的 upload_status 为 COMPLETED 的条目
            completed_datasets = (
                session.query(DatasetDB)
                .filter(status_attr == TaskStatus.COMPLETED)
                .all()
            )

            # 提取 convert_path 的结尾文件夹名称
            dataset_names = []
            for dataset in completed_datasets:
                if dataset.convert_path:
                    # 获取路径的最后一个部分（文件夹名称）
                    folder_name = Path(dataset.convert_path).name
                    dataset_names.append(folder_name)
                else:
                    logger.warning(
                        f"数据集 {dataset.dataset_uuid} 的 convert_path 为空，跳过"
                    )

            logger.info(f"从数据库获取到 {len(dataset_names)} 个 {platform.value} COMPLETED 状态的数据集")
            return dataset_names

    except Exception as e:
        logger.error(f"读取数据库失败: {e}")
        raise


def compare_lists(
    hub_repos: list[str], db_datasets: list[str]
) -> tuple[set[str], set[str], set[str]]:
    """
    比较两个列表的差异

    Args:
        hub_repos: Hub 平台上的 repo 列表
        db_datasets: 数据库中的数据集列表

    Returns:
        (在数据库但不在Hub, 在Hub但不在数据库, 两者都有)
    """
    hub_set = set(hub_repos)
    db_set = set(db_datasets)

    # 在数据库中标记为 COMPLETED，但在 Hub 上不存在
    in_db_not_in_hub = db_set - hub_set

    # 在 Hub 上存在，但在数据库中没有标记为 COMPLETED
    in_hub_not_in_db = hub_set - db_set

    # 两者都有
    in_both = db_set & hub_set

    return in_db_not_in_hub, in_hub_not_in_db, in_both


def print_results(
    in_db_not_in_hub: set[str],
    in_hub_not_in_db: set[str],
    in_both: set[str],
    platform: HubPlatform,
    verbose: bool = False,
) -> None:
    """
    打印比较结果

    Args:
        in_db_not_in_hub: 在数据库但不在 Hub 的数据集
        in_hub_not_in_db: 在 Hub 但不在数据库的数据集
        in_both: 两者都有的数据集
        platform: Hub 平台
        verbose: 是否显示详细信息
    """
    platform_name = platform.value.upper()

    print("\n" + "=" * 80)
    print(f"检测结果汇总 - {platform_name}")
    print("=" * 80)

    print("\n📊 统计信息:")
    print(f"  - {platform_name} 上的 repos 总数: {len(in_hub_not_in_db) + len(in_both)}")
    print(f"  - 数据库中 COMPLETED 状态的数据集总数: {len(in_db_not_in_hub) + len(in_both)}")
    print(f"  - 两者都有的数据集数量: {len(in_both)}")

    print("\n⚠️  差异数据集:")
    print(f"  - 在数据库中标记为 COMPLETED 但在 {platform_name} 上不存在: {len(in_db_not_in_hub)}")
    print(f"  - 在 {platform_name} 上存在但在数据库中未标记为 COMPLETED: {len(in_hub_not_in_db)}")

    if in_db_not_in_hub:
        print(f"\n❌ 在数据库中标记为 COMPLETED 但在 {platform_name} 上不存在的数据集 ({len(in_db_not_in_hub)}):")
        for dataset in sorted(in_db_not_in_hub):
            print(f"  - {dataset}")

    if in_hub_not_in_db:
        print(f"\n⚠️  在 {platform_name} 上存在但在数据库中未标记为 COMPLETED 的数据集 ({len(in_hub_not_in_db)}):")
        for dataset in sorted(in_hub_not_in_db):
            print(f"  - {dataset}")

    if verbose and in_both:
        print(f"\n✅ 两者都有的数据集 ({len(in_both)}):")
        for dataset in sorted(in_both):
            print(f"  - {dataset}")

    print("\n" + "=" * 80)

    # 总结
    if not in_db_not_in_hub and not in_hub_not_in_db:
        print(f"✅ 完美一致！数据库和 {platform_name} 完全同步。")
    else:
        print("⚠️  发现不一致！请检查上述差异数据集。")
    print("=" * 80 + "\n")


def check_platform_consistency(
    platform: HubPlatform,
    namespace: str,
    token: str,
    db_path: str,
    verbose: bool,
) -> bool:
    """
    检查单个平台的一致性

    Args:
        platform: Hub 平台
        namespace: 命名空间
        token: 认证 token
        db_path: 数据库路径
        verbose: 是否显示详细信息

    Returns:
        True 如果一致，False 如果有差异
    """
    # 1. 获取 Hub 平台上的 repos
    hub_repos = get_hub_repos(platform, namespace, token)

    # 2. 获取数据库中 COMPLETED 状态的数据集
    db_datasets = get_db_completed_datasets(db_path, platform)

    # 3. 比较差异
    in_db_not_in_hub, in_hub_not_in_db, in_both = compare_lists(
        hub_repos, db_datasets
    )

    # 4. 打印结果
    print_results(in_db_not_in_hub, in_hub_not_in_db, in_both, platform, verbose)

    # 5. 返回是否一致
    return not (in_db_not_in_hub or in_hub_not_in_db)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="检测 Hub 平台（Hugging Face / ModelScope）上的 RoboCOIN repos 和数据库中标记为 COMPLETED 的数据集的一致性"
    )
    parser.add_argument(
        "--platform",
        type=str,
        choices=["huggingface", "modelscope", "all"],
        default="huggingface",
        help="要检查的 Hub 平台 (默认: huggingface)",
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default="RoboCOIN",
        help="Hub 命名空间/用户名 (默认: RoboCOIN)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Hub token (可选，用于访问私有 repos)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="/mnt/db/datasets_new.db",
        help="数据库文件路径 (默认: /mnt/db/datasets_new.db)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="显示详细信息，包括两者都有的数据集列表",
    )

    args = parser.parse_args()

    try:
        all_consistent = True

        # 根据指定的平台进行检查
        if args.platform == "all":
            # 检查所有平台
            platforms_to_check = [HubPlatform.HUGGINGFACE, HubPlatform.MODELSCOPE]
        else:
            # 检查单个平台
            platforms_to_check = [HubPlatform(args.platform)]

        for platform in platforms_to_check:
            consistent = check_platform_consistency(
                platform=platform,
                namespace=args.namespace,
                token=args.token,
                db_path=args.db_path,
                verbose=args.verbose,
            )
            if not consistent:
                all_consistent = False

        # 返回适当的退出码
        if all_consistent:
            sys.exit(0)  # 完全一致
        else:
            sys.exit(1)  # 存在不一致

    except Exception as e:
        logger.error(f"脚本执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
