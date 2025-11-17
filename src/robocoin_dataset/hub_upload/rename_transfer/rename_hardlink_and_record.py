

def _update_hardlink_table_and_rename_folders() -> None:
    '''
    函数根据配置文件的映射关系更新数据表中的记录然后重命名硬链接文件夹。
    首先，根据数据表(/mte/db/datasets_new.db中的dataset_hard_link表格)找到一个对应的记录，
    用一个暂时变量存储他的uuid和他的原本的硬链接路径。（用于最后重命名）
    然后读取datasets数据表中的数据（使用超键dataset_uuid），然后根据convert_path的结尾字符串（文件夹名称）
    将对应uuid的记录的硬链接路径修改成 结尾字符串 + <_qced_hardlink>
    同时将原本的实际路径指向的硬链接文件夹的名字改成数据表中对应的名称。

    安全保证：
    1. 绝对不删除硬链接文件夹（只使用rename，不使用delete）
    2. 只重命名以 _qced_hardlink 结尾的文件夹
    3. 只更改 dataset_hard_link 数据表，不修改 datasets 表
    '''
    from pathlib import Path

    from robocoin_dataset.database.database import DatasetDatabase
    from robocoin_dataset.database.models import DatasetDB, DatasetHardLinkDB

    # 硬链接基础路径（用于修复被破坏的路径）
    hardlink_base_path = Path("/mnt/nas/synnas/docker2/robocoin-datasets")

    db_path = Path("/mnt/db/datasets_new.db")
    db = DatasetDatabase(db_path)

    with db.with_session() as session:
        # 查询所有硬链接记录
        hardlink_records = session.query(DatasetHardLinkDB).all()

        for hardlink_record in hardlink_records:
            # 安全检查1：必须有硬链接路径
            if not hardlink_record.hard_link_path:
                continue

            # 修复被破坏的路径（缺少前缀的情况）
            original_path = Path(hardlink_record.hard_link_path)
            if not original_path.is_absolute():
                # 路径不是绝对路径，说明被之前的错误更新破坏了，需要添加前缀
                print(f"检测到损坏的路径（缺少前缀）: {hardlink_record.hard_link_path}")
                hardlink_record.hard_link_path = str(hardlink_base_path / hardlink_record.hard_link_path)
                print(f"已修复为: {hardlink_record.hard_link_path}")

            # 安全检查2：只处理以 _qced_hardlink 结尾的文件夹
            if not hardlink_record.hard_link_path.endswith("_qced_hardlink"):
                continue

            # 获取对应的数据集记录
            dataset = session.query(DatasetDB).filter_by(
                dataset_uuid=hardlink_record.dataset_uuid
            ).first()

            if not dataset or not dataset.convert_path:
                continue

            # 提取convert_path的文件夹名称
            folder_name = Path(dataset.convert_path).name
            # 保留原始路径的父目录，只修改最后的文件夹名称
            old_hardlink_path = Path(hardlink_record.hard_link_path)
            new_hardlink_path = str(old_hardlink_path.parent / f"{folder_name}_qced_hardlink")

            # 如果路径已经正确，跳过
            if hardlink_record.hard_link_path == new_hardlink_path:
                continue

            # 保存原始路径（绝对路径）
            old_path = Path(hardlink_record.hard_link_path).resolve()

            # 安全检查3：确保源文件夹存在且是目录
            if not old_path.exists() or not old_path.is_dir():
                print(f"警告: 源文件夹不存在或不是目录: {old_path}")
                continue

            # 计算新路径（new_hardlink_path 已经是完整路径）
            new_path = Path(new_hardlink_path)

            # 安全检查4：确保目标路径不存在，避免覆盖
            if new_path.exists():
                print(f"警告: 目标路径已存在，跳过: {new_path}")
                continue

            # 只更新 dataset_hard_link 表（不修改 datasets 表）
            hardlink_record.hard_link_path = new_hardlink_path

            # 重命名实际文件夹（只重命名，不删除）
            try:
                old_path.rename(new_path)
                print(f"已重命名: {old_path.name} -> {new_path.name}")
            except Exception as e:
                print(f"重命名失败 {old_path} -> {new_path}: {e}")
                # 如果重命名失败，回滚数据库更改
                session.rollback()
                raise

        # 提交所有更改
        session.commit()
        print("数据库更新完成")


if __name__ == "__main__":
    _update_hardlink_table_and_rename_folders()
