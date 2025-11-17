#!/usr/bin/env python3
"""
Visual Completed Status Tracker - 可视化检查状态追踪器

功能：
  追踪和检测 visualize_check_status 字段的状态变化

  1. 记录模式（默认）：
     - 读取所有 visualize_check_status=COMPLETED 的 UUID
     - 保存到时间戳文件：YYYYMMDD_HHMMSS_visual_completed_count.json

  2. 比较模式（指定 --file）：
     - 读取历史文件中的UUID列表
     - 查询这些UUID的当前状态
     - 检测从COMPLETED变为其他状态的条目
     - 生成回退报告

使用：
  # 记录模式：保存当前COMPLETED状态
  python scripts/hub_upload/track_visual_completed.py
  python scripts/hub_upload/track_visual_completed.py --db-path /mnt/db/datasets_new.db

  # 比较模式：检测状态回退
  python scripts/hub_upload/track_visual_completed.py  --file 20241117_120000_visual_completed_count.json
  python scripts/hub_upload/track_visual_completed.py  --db-path /path/to/db --file history.json

参数：
  --db-path DB_PATH       数据库路径 (默认: /mnt/db/datasets_new.db)
  --file FILE             历史记录文件，指定后进入比较模式
  --output-dir DIR        输出目录 (默认: 脚本所在目录)

退出码：
  0 - 成功（记录）或无回退（比较）
  1 - 检测到状态回退
  2 - 执行失败

工作流示例：
  # 1. 建立基线
  python track_visual_completed.py
  # 输出: 20241117_100000_visual_completed_count.json

  # 2. 定期检查（每天/每周）
  python track_visual_completed.py --file 20241117_100000_visual_completed_count.json

  # 3. 如果无回退，更新基线
  if [ $? -eq 0 ]; then
      python track_visual_completed.py  # 生成新基线
  fi

集成到CI/CD：
  - 每天自动运行检查
  - 退出码1时发送告警
  - 定期更新基线文件

注意：
  - 文件生成在脚本同级目录
  - JSON格式包含timestamp、count、uuids列表
  - 不建议手动编辑历史文件
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "src"))

from robocoin_dataset.database.database import DatasetDatabase  # noqa: E402
from robocoin_dataset.database.models import DatasetDB, TaskStatus  # noqa: E402

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_completed_uuids(db_path: str) -> list[str]:
    """
    从数据库获取所有 visualize_check_status 为 COMPLETED 的 UUID

    Args:
        db_path: 数据库文件路径

    Returns:
        UUID 列表
    """
    logger.info(f"正在从数据库 {db_path} 读取 visualize_check_status=COMPLETED 的条目...")

    try:
        db = DatasetDatabase(Path(db_path))

        with db.with_session() as session:
            # 查询 visualize_check_status 为 COMPLETED 的条目
            completed_datasets = (
                session.query(DatasetDB.dataset_uuid)
                .filter(DatasetDB.visualize_check_status == TaskStatus.COMPLETED)
                .all()
            )

            # 提取 UUID
            uuids = [dataset.dataset_uuid for dataset in completed_datasets]

            logger.info(f"找到 {len(uuids)} 个 visualize_check_status=COMPLETED 的数据集")
            return uuids

    except Exception as e:
        logger.error(f"读取数据库失败: {e}")
        raise


def save_uuids_to_file(uuids: list[str], output_dir: str = ".") -> Path:
    """
    保存 UUID 列表到时间戳文件

    Args:
        uuids: UUID 列表
        output_dir: 输出目录

    Returns:
        生成的文件路径
    """
    # 生成时间戳文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_visual_completed_count.json"

    output_path = Path(output_dir) / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 保存数据
    data = {
        "timestamp": timestamp,
        "datetime": datetime.now().isoformat(),
        "count": len(uuids),
        "uuids": sorted(uuids),  # 排序以便比较
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"已保存 {len(uuids)} 个 UUID 到文件: {output_path}")
    return output_path


def load_uuids_from_file(file_path: str) -> tuple[list[str], str]:
    """
    从文件加载 UUID 列表

    Args:
        file_path: 文件路径

    Returns:
        (UUID 列表, 时间戳)
    """
    logger.info(f"正在从文件加载历史数据: {file_path}")

    try:
        with open(file_path, encoding='utf-8') as f:
            data = json.load(f)

        uuids = data.get("uuids", [])
        timestamp = data.get("datetime", data.get("timestamp", "unknown"))

        logger.info(f"加载了 {len(uuids)} 个历史 UUID (时间: {timestamp})")
        return uuids, timestamp

    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        raise


def get_current_status_for_uuids(db_path: str, uuids: list[str]) -> dict[str, str]:
    """
    获取指定 UUID 列表的当前 visualize_check_status

    Args:
        db_path: 数据库文件路径
        uuids: UUID 列表

    Returns:
        UUID -> 状态的映射字典
    """
    logger.info(f"正在查询 {len(uuids)} 个 UUID 的当前状态...")

    try:
        db = DatasetDatabase(Path(db_path))
        status_map = {}

        with db.with_session() as session:
            for uuid in uuids:
                dataset = (
                    session.query(DatasetDB)
                    .filter(DatasetDB.dataset_uuid == uuid)
                    .first()
                )

                if dataset:
                    status = dataset.visualize_check_status
                    status_map[uuid] = status.value if status else "NULL"
                else:
                    status_map[uuid] = "NOT_FOUND"

        logger.info(f"成功查询 {len(status_map)} 个 UUID 的状态")
        return status_map

    except Exception as e:
        logger.error(f"查询状态失败: {e}")
        raise


def compare_and_detect_regression(
    historical_uuids: list[str],
    db_path: str,
    historical_timestamp: str,
) -> list[dict]:
    """
    比较历史记录和当前状态，检测状态回退

    Args:
        historical_uuids: 历史上为 COMPLETED 的 UUID 列表
        db_path: 数据库文件路径
        historical_timestamp: 历史记录的时间戳

    Returns:
        状态回退的条目列表
    """
    logger.info("开始比较历史状态和当前状态...")

    # 获取当前状态
    current_status_map = get_current_status_for_uuids(db_path, historical_uuids)

    # 检测回退
    regressed = []
    for uuid in historical_uuids:
        current_status = current_status_map.get(uuid, "UNKNOWN")

        # 如果当前状态不是 COMPLETED，说明发生了回退
        if current_status != TaskStatus.COMPLETED.value:
            regressed.append({
                "uuid": uuid,
                "historical_status": "COMPLETED",
                "current_status": current_status,
            })

    logger.info(f"检测到 {len(regressed)} 个状态回退的条目")
    return regressed


def print_regression_report(
    regressed: list[dict],
    historical_timestamp: str,
    historical_count: int,
    current_completed_count: int,
) -> None:
    """
    打印状态回退报告

    Args:
        regressed: 状态回退的条目列表
        historical_timestamp: 历史记录时间戳
        historical_count: 历史 COMPLETED 数量
        current_completed_count: 当前 COMPLETED 数量
    """
    print("\n" + "=" * 80)
    print("Visual Check Status 回退检测报告")
    print("=" * 80)

    print(f"\n📅 历史记录时间: {historical_timestamp}")
    print("📊 统计信息:")
    print(f"  - 历史 COMPLETED 数量: {historical_count}")
    print(f"  - 当前 COMPLETED 数量: {current_completed_count}")
    print(f"  - 变化: {current_completed_count - historical_count:+d}")

    if not regressed:
        print("\n✅ 未检测到状态回退")
        print("   所有历史上为 COMPLETED 的数据集仍保持 COMPLETED 状态")
    else:
        print(f"\n⚠️  检测到 {len(regressed)} 个状态回退:")

        # 按当前状态分组
        by_status = {}
        for item in regressed:
            status = item["current_status"]
            if status not in by_status:
                by_status[status] = []
            by_status[status].append(item["uuid"])

        for status, uuids in sorted(by_status.items()):
            print(f"\n  {status} ({len(uuids)} 个):")
            for uuid in sorted(uuids):
                print(f"    - {uuid}")

    print("\n" + "=" * 80 + "\n")


def record_mode(db_path: str, output_dir: str) -> int:
    """
    记录模式：保存当前所有 COMPLETED 状态的 UUID

    Args:
        db_path: 数据库文件路径
        output_dir: 输出目录

    Returns:
        退出码
    """
    try:
        # 获取 COMPLETED 的 UUID
        uuids = get_completed_uuids(db_path)

        # 保存到文件
        output_file = save_uuids_to_file(uuids, output_dir)

        # 打印摘要
        print("\n" + "=" * 80)
        print("记录模式 - 完成")
        print("=" * 80)
        print(f"\n✅ 已记录 {len(uuids)} 个 visualize_check_status=COMPLETED 的数据集")
        print(f"📁 输出文件: {output_file}")
        print("\n💡 提示: 使用以下命令进行比较检测:")
        print(f"   python scripts/hub_upload/{Path(__file__).name} --db-path {db_path} --file {output_file}")
        print("=" * 80 + "\n")

        return 0

    except Exception as e:
        logger.error(f"记录模式失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


def compare_mode(db_path: str, file_path: str) -> int:
    """
    比较模式：检测状态回退

    Args:
        db_path: 数据库文件路径
        file_path: 历史记录文件路径

    Returns:
        退出码（0=无回退, 1=有回退, 2=错误）
    """
    try:
        # 加载历史数据
        historical_uuids, historical_timestamp = load_uuids_from_file(file_path)

        # 获取当前 COMPLETED 数量
        current_completed_uuids = get_completed_uuids(db_path)

        # 比较并检测回退
        regressed = compare_and_detect_regression(
            historical_uuids, db_path, historical_timestamp
        )

        # 打印报告
        print_regression_report(
            regressed,
            historical_timestamp,
            len(historical_uuids),
            len(current_completed_uuids),
        )

        # 返回退出码
        if regressed:
            return 1  # 发现回退
        return 0  # 无回退

    except Exception as e:
        logger.error(f"比较模式失败: {e}")
        import traceback
        traceback.print_exc()
        return 2


def main() -> int:
    # 获取脚本所在目录作为默认输出目录
    script_dir = Path(__file__).parent.absolute()

    parser = argparse.ArgumentParser(
        description="追踪和检测 visualize_check_status 状态变化",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:

  # 记录模式：保存当前所有 COMPLETED 状态的 UUID
  python %(prog)s --db-path /mnt/db/datasets_new.db
  python %(prog)s --db-path /mnt/db/datasets_new.db --output-dir ./tracking

  # 比较模式：检测状态回退
  python %(prog)s --db-path /mnt/db/datasets_new.db --file 20241117_120000_visual_completed_count.json

退出码:
  0 - 成功（记录模式）或无状态回退（比较模式）
  1 - 检测到状态回退（比较模式）
  2 - 执行失败
        """,
    )

    parser.add_argument(
        "--db-path",
        type=str,
        default="/mnt/db/datasets_new.db",
        help="数据库文件路径 (默认: /mnt/db/datasets_new.db)",
    )

    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="历史记录文件路径 (指定后进入比较模式)",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(script_dir),
        help=f"输出目录，用于保存记录文件 (默认: 脚本所在目录 {script_dir})",
    )

    args = parser.parse_args()

    # 验证数据库路径
    db_path = Path(args.db_path).expanduser().absolute()
    if not db_path.exists():
        logger.error(f"数据库文件不存在: {db_path}")
        return 2
    if not db_path.is_file():
        logger.error(f"数据库路径不是文件: {db_path}")
        return 2

    # 根据是否提供 --file 参数选择模式
    if args.file:
        # 比较模式
        file_path = Path(args.file).expanduser().absolute()
        if not file_path.exists():
            logger.error(f"历史记录文件不存在: {file_path}")
            return 2
        if not file_path.is_file():
            logger.error(f"历史记录路径不是文件: {file_path}")
            return 2

        return compare_mode(str(db_path), str(file_path))
    # 记录模式
    return record_mode(str(db_path), args.output_dir)


if __name__ == "__main__":
    sys.exit(main())
