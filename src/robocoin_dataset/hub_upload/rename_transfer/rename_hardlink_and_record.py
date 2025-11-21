

def _update_hardlink_table_and_rename_folders() -> None:
    '''
    函数根据配置文件的映射关系更新数据表中的记录然后重命名硬链接文件夹。

    步骤：
    1. 存储字典，记录 dataset_uuid: [hard_link_path] 在 dataset_hard_link 数据表中
    2. 遍历所有项，读取 datasets 表格，根据对应的 uuid 查询到 convert_path，
       append 在字典的值后面，变成 dataset_uuid: [hard_link_path, convert_path]
    3-4. 对每个条目：
       - 先找原本的 hard_link_path 文件夹，如果存在就重命名并更新数据库
       - 如果不存在，找 convert_path + "_qced_hardlink" 文件夹，如果存在就只更新数据库
       - 如果两个都不存在，警告并跳过此条目

    安全保证：
    1. 绝对不删除硬链接文件夹（只使用rename，不使用delete）
    2. 只重命名以 _qced_hardlink 结尾的文件夹
    3. 只更改 dataset_hard_link 数据表，不修改 datasets 表
    4. 如果文件夹已经是正确名称，只更新数据库
    '''
    from pathlib import Path

    from robocoin_dataset.database.database import DatasetDatabase
    from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB

    # 硬链接基础路径（用于修复被破坏的路径）
    hardlink_base_path = Path("/mnt/nas/synnas/docker2/robocoin-datasets")

    db_path = Path("/mnt/db/datasets_new.db")
    db = DatasetDatabase(db_path)

    with db.with_session() as session:
        # 步骤1: 存储字典，记录 dataset_uuid: [hard_link_path]
        print("步骤1: 读取 dataset_hard_link 表格...")
        uuid_to_paths = {}  # dataset_uuid: [hard_link_path, convert_path]

        hardlink_records = session.query(DatasetHardLinkDB).all()

        for hardlink_record in hardlink_records:
            # 只处理有硬链接路径的记录
            if not hardlink_record.hard_link_path:
                continue

            # 修复被破坏的路径（缺少前缀的情况）
            original_path = Path(hardlink_record.hard_link_path)
            if not original_path.is_absolute():
                # 路径不是绝对路径，说明被之前的错误更新破坏了，需要添加前缀
                print(f"  检测到损坏的路径（缺少前缀）: {hardlink_record.hard_link_path}")
                fixed_path = str(hardlink_base_path / hardlink_record.hard_link_path)
                # 立即更新到数据库记录
                hardlink_record.hard_link_path = fixed_path
                print(f"  已修复为: {fixed_path}")

            # 只处理以 _qced_hardlink 结尾的文件夹
            if not hardlink_record.hard_link_path.endswith("_qced_hardlink"):
                continue

            uuid_to_paths[hardlink_record.dataset_uuid] = [hardlink_record.hard_link_path]

        print(f"  找到 {len(uuid_to_paths)} 个需要处理的硬链接记录")

        # 步骤2: 遍历所有项，读取 datasets 表格，查询 convert_path
        print("\n步骤2: 读取 datasets 表格，获取 convert_path...")

        for dataset_uuid in list(uuid_to_paths.keys()):
            dataset = session.query(DatasetDB).filter_by(
                dataset_uuid=dataset_uuid
            ).first()

            if not dataset or not dataset.convert_path:
                print(f"  警告: uuid {dataset_uuid} 没有找到对应的 convert_path，跳过")
                del uuid_to_paths[dataset_uuid]
                continue

            # append convert_path 到字典
            uuid_to_paths[dataset_uuid].append(dataset.convert_path)
            print(f"  uuid: {dataset_uuid}")
            print(f"    hard_link_path: {uuid_to_paths[dataset_uuid][0]}")
            print(f"    convert_path: {dataset.convert_path}")

        print(f"\n  共 {len(uuid_to_paths)} 个记录需要更新")

        # 步骤3 和 4: 重命名文件夹并更新数据库
        print("\n步骤3-4: 重命名文件夹并更新数据库...")

        success_rename_count = 0  # 重命名+更新的数量
        success_update_only_count = 0  # 只更新数据库的数量
        already_correct_count = 0  # 路径已经正确的数量
        not_found_count = 0  # 找不到文件夹的数量

        for dataset_uuid, paths in uuid_to_paths.items():
            hard_link_path = paths[0]
            convert_path = paths[1]

            # 提取 convert_path 的文件夹名称
            folder_name = Path(convert_path).name

            # 构建新的硬链接路径：保留父目录，修改文件夹名为 folder_name + _qced_hardlink
            old_path_obj = Path(hard_link_path)
            new_hardlink_path = str(old_path_obj.parent / f"{folder_name}_qced_hardlink")

            # 如果路径已经正确，跳过
            if hard_link_path == new_hardlink_path:
                print(f"  跳过（路径已正确）: {new_hardlink_path}")
                already_correct_count += 1
                continue

            print(f"\n  处理 uuid: {dataset_uuid}")
            print(f"    数据库中的路径: {hard_link_path}")
            print(f"    期望的新路径: {new_hardlink_path}")

            # 检查原路径是否存在
            old_path = Path(hard_link_path)
            new_path = Path(new_hardlink_path)

            # 逻辑1: 先找原本的 hard_link_path，如果有就重命名并更新数据库
            if old_path.exists() and old_path.is_dir():
                print("    找到原路径文件夹")

                # 安全检查：确保目标路径不存在，避免覆盖
                if new_path.exists():
                    print("    ✗ 警告: 目标路径已存在，跳过")
                    not_found_count += 1
                    continue

                # 重命名实际文件夹
                try:
                    old_path.rename(new_path)
                    print(f"    ✓ 文件夹重命名成功: {old_path.name} -> {new_path.name}")
                except Exception as e:
                    print(f"    ✗ 文件夹重命名失败: {e}")
                    session.rollback()
                    raise

                # 更新数据库
                hardlink_record = session.query(DatasetHardLinkDB).filter_by(
                    dataset_uuid=dataset_uuid
                ).first()

                if hardlink_record:
                    hardlink_record.hard_link_path = new_hardlink_path
                    print("    ✓ 数据库记录更新成功")
                    success_rename_count += 1
                else:
                    print("    ✗ 警告: 找不到对应的数据库记录")

            # 逻辑2: 如果原路径不存在，找 convert_path + "_qced_hardlink"，如果有就只更新数据库
            elif new_path.exists() and new_path.is_dir():
                print("    原路径不存在，但找到了期望的新路径文件夹")
                print("    只更新数据库（文件夹已经是正确的名字）")

                # 只更新数据库
                hardlink_record = session.query(DatasetHardLinkDB).filter_by(
                    dataset_uuid=dataset_uuid
                ).first()

                if hardlink_record:
                    hardlink_record.hard_link_path = new_hardlink_path
                    print("    ✓ 数据库记录更新成功")
                    success_update_only_count += 1
                else:
                    print("    ✗ 警告: 找不到对应的数据库记录")

            # 逻辑3: 两个都没找到，警告并跳过
            else:
                print("    ✗ 警告: 两个路径都不存在")
                print(f"       原路径: {old_path}")
                print(f"       新路径: {new_path}")
                print("    跳过此条目")
                not_found_count += 1
                continue

        # 提交所有更改
        session.commit()
        print("\n完成！")
        print(f"  重命名+更新数据库: {success_rename_count} 个")
        print(f"  仅更新数据库: {success_update_only_count} 个")
        print(f"  路径已正确（无需修改）: {already_correct_count} 个")
        print(f"  找不到文件夹（跳过）: {not_found_count} 个")
        print(f"  总成功: {success_rename_count + success_update_only_count} 个")
        print("  数据库更改已提交")


if __name__ == "__main__":
    _update_hardlink_table_and_rename_folders()
