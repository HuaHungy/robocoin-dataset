#!/usr/bin/env python3
"""
比较 uploadComp.json 和 path.json 中的数据集名称差异

从 path.json 中提取每个路径的 Path(item).name.removesuffix('_qced_hardlink')，
与 uploadComp.json 中的名称进行比较，输出差异项到 diff.json。

使用方法:
    python scripts/compare_upload_paths.py [--upload-comp uploadComp.json] [--path path.json] [--output diff.json]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "src"))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_upload_comp(file_path: Path) -> set[str]:
    """加载 uploadComp.json 文件，返回数据集名称集合"""
    logger.info(f"正在加载 {file_path}...")

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"{file_path} 应该是一个字符串数组")

    names = set(data)
    logger.info(f"从 {file_path} 加载了 {len(names)} 个数据集名称")
    return names


def load_path_names(file_path: Path) -> set[str]:
    """加载 path.json 文件，提取每个路径的名称（移除 _qced_hardlink 后缀）"""
    logger.info(f"正在加载 {file_path}...")

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"{file_path} 应该是一个字符串数组")

    names = set()
    for item in data:
        if not isinstance(item, str):
            continue

        # 提取路径名称并移除 _qced_hardlink 后缀
        path_name = Path(item).name
        if path_name.endswith("_qced_hardlink"):
            name = path_name.removesuffix("_qced_hardlink")
        else:
            name = path_name

        names.add(name)

    logger.info(f"从 {file_path} 提取了 {len(names)} 个数据集名称")
    return names


def compare_and_save_diff(
    upload_comp_names: set[str],
    path_names: set[str],
    output_path: Path
) -> None:
    """比较两个集合，找出差异并保存到文件"""
    logger.info("正在比较数据集名称...")

    # 找出差异项
    only_in_upload_comp = sorted(upload_comp_names - path_names)
    only_in_path = sorted(path_names - upload_comp_names)
    common = sorted(upload_comp_names & path_names)

    logger.info(f"仅在 uploadComp.json 中: {len(only_in_upload_comp)} 个")
    logger.info(f"仅在 path.json 中: {len(only_in_path)} 个")
    logger.info(f"两者共有: {len(common)} 个")

    # 构建差异结果
    diff_result = {
        "only_in_upload_comp": only_in_upload_comp,
        "only_in_path": only_in_path,
        "common": common,
        "summary": {
            "total_in_upload_comp": len(upload_comp_names),
            "total_in_path": len(path_names),
            "only_in_upload_comp_count": len(only_in_upload_comp),
            "only_in_path_count": len(only_in_path),
            "common_count": len(common),
        }
    }

    # 保存到文件
    logger.info(f"正在保存差异结果到 {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(diff_result, f, indent=2, ensure_ascii=False)

    logger.info(f"✅ 已保存差异结果到: {output_path}")

    # 打印摘要
    logger.info("")
    logger.info("=" * 60)
    logger.info("差异摘要")
    logger.info("=" * 60)
    logger.info(f"uploadComp.json 总数: {len(upload_comp_names)}")
    logger.info(f"path.json 总数: {len(path_names)}")
    logger.info(f"仅在 uploadComp.json 中: {len(only_in_upload_comp)}")
    logger.info(f"仅在 path.json 中: {len(only_in_path)}")
    logger.info(f"两者共有: {len(common)}")
    logger.info("=" * 60)

    if only_in_upload_comp:
        logger.info("")
        logger.info("仅在 uploadComp.json 中的数据集:")
        for name in only_in_upload_comp[:20]:  # 只显示前20个
            logger.info(f"  - {name}")
        if len(only_in_upload_comp) > 20:
            logger.info(f"  ... 还有 {len(only_in_upload_comp) - 20} 个")

    if only_in_path:
        logger.info("")
        logger.info("仅在 path.json 中的数据集:")
        for name in only_in_path[:20]:  # 只显示前20个
            logger.info(f"  - {name}")
        if len(only_in_path) > 20:
            logger.info(f"  ... 还有 {len(only_in_path) - 20} 个")


def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(
        description="比较 uploadComp.json 和 path.json 中的数据集名称差异",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--upload-comp",
        type=str,
        default=None,
        help="uploadComp.json 文件路径 (默认: 项目根目录/uploadComp.json)",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="path.json 文件路径 (默认: 项目根目录/path.json)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出 diff.json 文件路径 (默认: 项目根目录/diff.json)",
    )

    args = parser.parse_args()

    # 确定文件路径
    upload_comp_path = Path(args.upload_comp).expanduser().absolute() if args.upload_comp else project_root / "uploadComp.json"
    path_file_path = Path(args.path).expanduser().absolute() if args.path else project_root / "path.json"
    output_path = Path(args.output).expanduser().absolute() if args.output else project_root / "diff.json"

    # 检查文件是否存在
    if not upload_comp_path.exists():
        logger.error(f"文件不存在: {upload_comp_path}")
        sys.exit(1)

    if not path_file_path.exists():
        logger.error(f"文件不存在: {path_file_path}")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("比较 uploadComp.json 和 path.json")
    logger.info("=" * 60)
    logger.info(f"uploadComp.json 路径: {upload_comp_path}")
    logger.info(f"path.json 路径: {path_file_path}")
    logger.info(f"输出路径: {output_path}")
    logger.info("")

    try:
        # 加载数据
        upload_comp_names = load_upload_comp(upload_comp_path)
        path_names = load_path_names(path_file_path)

        # 比较并保存差异
        compare_and_save_diff(upload_comp_names, path_names, output_path)

    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
