#!/usr/bin/env python3
"""
检查数据库中的 hard_link_path 是否包含 name_mapping.json 中的右侧值（非法值）
"""

import json
import sqlite3
from pathlib import Path

# 数据库路径
DB_PATH = "/mnt/db/datasets_new.db"

# name_mapping.json 路径（与脚本同目录）
SCRIPT_DIR = Path(__file__).parent
NAME_MAPPING_PATH = SCRIPT_DIR / "name_mapping.json"


def main() -> None:
    # 读取 name_mapping.json
    with open(NAME_MAPPING_PATH, encoding='utf-8') as f:
        name_mapping = json.load(f)

    # 获取所有右侧值（非法值）
    illegal_values = set(name_mapping.values())
    print(f"检查的非法值: {illegal_values}\n")

    # 连接数据库
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 查询所有 hard_link_path
    cursor.execute("SELECT hard_link_path FROM dataset_hard_link")
    rows = cursor.fetchall()

    print(f"总共查询到 {len(rows)} 条记录\n")

    # 检查每个 hard_link_path
    found_illegal = False
    for row in rows:
        hard_link_path = row[0]
        if hard_link_path:
            # 检查是否包含任何非法值
            for illegal_value in illegal_values:
                if illegal_value in hard_link_path:
                    print(f"发现非法路径: {hard_link_path}")
                    print(f"  包含非法值: {illegal_value}\n")
                    found_illegal = True
                    break

    if not found_illegal:
        print("✓ 没有发现包含非法值的路径")

    # 关闭数据库连接
    conn.close()


if __name__ == "__main__":
    main()
