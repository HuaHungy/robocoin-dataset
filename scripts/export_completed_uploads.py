#!/usr/bin/env python3
"""
导出已完成上传的数据集名称

从数据库中导出所有 huggingface_upload_status 和 ms_upload_status 都为 COMPLETED 的
数据集 convert_path 名称（Path(convert_path).name），保存到项目根目录的 uploadComp.json 文件。

使用方法:
    python scripts/export_completed_uploads.py [--db /path/to/db] [--output /path/to/output.json]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "src"))

from robocoin_dataset.database.database import DatasetDatabase  # noqa: E402
from robocoin_dataset.database.models import DatasetDB, TaskStatus  # noqa: E402

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def export_completed_uploads(db_path: Path) -> list[str]:
    """
    从数据库导出所有已完成上传的数据集名称

    Args:
        db_path: 数据库文件路径

    Returns:
        convert_path 名称列表（Path(convert_path).name）
    """
    logger.info("开始查询已完成上传的数据集...")

    db = DatasetDatabase(db_path)
    dataset_names = []

    with db.with_session() as session:
        # 查询 huggingface_upload_status 和 ms_upload_status 都为 COMPLETED 的记录
        query = session.query(DatasetDB.convert_path).filter(
            DatasetDB.huggingface_upload_status == TaskStatus.COMPLETED,
            DatasetDB.ms_upload_status == TaskStatus.COMPLETED,
        )

        results = query.all()

        # 提取 convert_path 的名称
        for row in results:
            convert_path = row[0]
            if convert_path:
                dataset_name = Path(convert_path).name
                dataset_names.append(dataset_name)
            else:
                logger.warning("发现 convert_path 为空的记录，跳过")

        logger.info(f"找到 {len(dataset_names)} 个已完成上传的数据集")

    return dataset_names


def save_to_json(dataset_names: list[str], output_path: Path) -> None:
    """保存数据集名称列表到 JSON 文件"""
    logger.info(f"保存 {len(dataset_names)} 个数据集名称到 {output_path}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dataset_names, f, indent=2, ensure_ascii=False)

    logger.info(f"✅ 已保存: {output_path}")


def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(
        description="导出已完成上传的数据集名称",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db",
        type=str,
        default="/mnt/db/datasets_new.db",
        help="数据库文件路径 (默认: /mnt/db/dataset_new.db)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出 JSON 文件路径 (默认: 项目根目录/uploadComp.json)",
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
        output_path = project_root / "uploadComp.json"

    logger.info("=" * 60)
    logger.info("导出已完成上传的数据集名称")
    logger.info("=" * 60)
    logger.info(f"数据库路径: {db_path}")
    logger.info(f"输出路径: {output_path}")
    logger.info("")

    try:
        # 导出已完成上传的数据集名称
        dataset_names = export_completed_uploads(db_path)

        # 保存到 JSON 文件
        save_to_json(dataset_names, output_path)

        # 汇总报告
        logger.info("")
        logger.info("=" * 60)
        logger.info("汇总报告")
        logger.info("=" * 60)
        logger.info(f"已完成上传的数据集数量: {len(dataset_names)}")
        logger.info(f"输出文件: {output_path}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
