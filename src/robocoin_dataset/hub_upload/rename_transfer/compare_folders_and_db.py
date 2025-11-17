"""
对比文件系统中的硬链接文件夹和数据库中的记录，找出差异。

只读操作，不修改任何数据。
"""


def compare_folders_and_database() -> None:
    """
    对比 /mnt/nas/synnas/docker2/robocoin-datasets/ 下的文件夹和数据库记录。

    步骤：
    1. 列出文件系统中所有以 _qced_hardlink 结尾的子文件夹
    2. 从 dataset_hard_link 表中读取所有 hard_link_path
    3. 对比并输出差异
    """
    from pathlib import Path

    from robocoin_dataset.database.database import DatasetDatabase
    from robocoin_dataset.database.models import DatasetHardLinkDB

    # 硬链接基础路径
    base_path = Path("/mnt/nas/synnas/docker2/robocoin-datasets")
    db_path = Path("/mnt/db/datasets_new.db")

    print("=" * 80)
    print("对比文件系统中的硬链接文件夹和数据库记录")
    print("=" * 80)

    # 步骤1: 列出文件系统中所有以 _qced_hardlink 结尾的子文件夹
    print(f"\n步骤1: 扫描文件系统 {base_path}")
    filesystem_folders = set()

    if base_path.exists() and base_path.is_dir():
        for item in base_path.iterdir():
            if item.is_dir() and item.name.endswith("_qced_hardlink"):
                filesystem_folders.add(str(item))
        print(f"  找到 {len(filesystem_folders)} 个 _qced_hardlink 文件夹")
    else:
        print(f"  错误: 基础路径不存在: {base_path}")
        return

    # 步骤2: 从数据库中读取所有 hard_link_path
    print(f"\n步骤2: 读取数据库 {db_path}")
    db = DatasetDatabase(db_path)
    database_paths = set()

    with db.with_session() as session:
        hardlink_records = session.query(DatasetHardLinkDB).all()

        for record in hardlink_records:
            if record.hard_link_path and record.hard_link_path.endswith("_qced_hardlink"):
                database_paths.add(record.hard_link_path)

        print(f"  找到 {len(database_paths)} 个 _qced_hardlink 记录")

    # 步骤3: 对比并输出差异
    print("\n步骤3: 对比差异")
    print("=" * 80)

    # 文件系统中有，但数据库中没有
    only_in_filesystem = filesystem_folders - database_paths
    print(f"\n【文件系统中有，但数据库中没有】: {len(only_in_filesystem)} 个")
    if only_in_filesystem:
        for path in sorted(only_in_filesystem):
            folder_name = Path(path).name
            print(f"  - {folder_name}")
    else:
        print("  (无)")

    # 数据库中有，但文件系统中没有
    only_in_database = database_paths - filesystem_folders
    print(f"\n【数据库中有，但文件系统中没有】: {len(only_in_database)} 个")
    if only_in_database:
        for path in sorted(only_in_database):
            folder_name = Path(path).name if Path(path).is_absolute() else path
            print(f"  - {folder_name}")
    else:
        print("  (无)")

    # 两者都有（一致的）
    in_both = filesystem_folders & database_paths
    print(f"\n【两者都有（一致）】: {len(in_both)} 个")

    # 总结
    print("\n" + "=" * 80)
    print("总结:")
    print(f"  文件系统文件夹总数: {len(filesystem_folders)}")
    print(f"  数据库记录总数: {len(database_paths)}")
    print(f"  一致的数量: {len(in_both)}")
    print(f"  仅在文件系统: {len(only_in_filesystem)}")
    print(f"  仅在数据库: {len(only_in_database)}")
    print("=" * 80)


if __name__ == "__main__":
    compare_folders_and_database()
