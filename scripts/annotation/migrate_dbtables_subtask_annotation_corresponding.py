from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

# 数据库路径
source_db_url = "sqlite:///db/datasets.db"
target_db_url = "sqlite:///db/datasets_senyu.db"

# 创建引擎
source_engine = create_engine(source_db_url)
target_engine = create_engine(target_db_url)

Session = sessionmaker()

# 表名列表，按依赖顺序排列：先父表，后子表
tables_in_order = [
    "leformat_episode_video_hash",
    "leformat_episode_video_hash_status",
    "url_video_subtask_annotation",
    "download_videos",
    "leformat_episode_url_video_match",
    "leformat_episode_url_video_match_status",
    "leformat_dataset_episode_original_subtask_annotation",
    "leformat_dataset_episode_original_subtask_annotation_status",
    "leformat_dataset_episode_optimized_subtask_annotation",
    "leformat_dataset_episode_optimized_subtask_annotation_status",
    "leformat_dataset_episode_subtask_range_annotation_embedding_status",
]


def migrate_tables() -> None:
    source_session = Session(bind=source_engine)
    target_session = Session(bind=target_engine)

    try:
        # 🔽 在目标数据库中临时禁用外键检查
        target_session.execute(text("PRAGMA foreign_keys = OFF"))
        target_session.commit()

        # 获取目标数据库中所有表的结构
        inspector = inspect(target_engine)

        for table_name in tables_in_order:
            print(f"迁移表: {table_name}")

            # ✅ 检查目标数据库中表是否存在
            target_tables = inspector.get_table_names()
            print(f"目标数据库中表: {target_tables}")
            if table_name not in target_tables:
                # 🔧 方案：从源数据库的 sqlite_master 获取 CREATE 语句
                print(
                    f"⚠️  目标数据库中表 '{table_name}' 不存在，尝试从源数据库中获取 CREATE 语句。"
                )
                result = source_session.execute(
                    text(
                        f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'"
                    )
                )
                row = result.fetchone()
                if not row or not row[0]:
                    raise Exception(f"无法获取表 {table_name} 的建表语句")

                create_sql = row[0]
                print(f"  在目标库创建表: {table_name}")
                target_session.execute(text(create_sql))
                target_session.commit()
                print(f"  表 {table_name} 创建成功")

            # 读取源表所有数据
            result = source_session.execute(text(f"SELECT * FROM {table_name}"))
            rows = result.fetchall()
            if not rows:
                print(f"  表 {table_name} 无数据")
                continue

            columns = result.keys()

            # 构造 INSERT 语句
            placeholders = ", ".join([":" + col for col in columns])
            insert_sql = f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"

            # 批量插入
            target_session.execute(text(insert_sql), [dict(row._mapping) for row in rows])
            target_session.commit()

            print(f"  成功插入 {len(rows)} 条记录")

        # ✅ 所有表迁移完成后，重新启用外键并检查
        target_session.execute(text("PRAGMA foreign_keys = ON"))
        target_session.commit()

        fk_check = target_session.execute(text("PRAGMA foreign_key_check")).fetchall()
        if fk_check:
            raise Exception(f"外键检查失败: {fk_check}")
        print("✅ 所有表迁移完成，外键检查通过")

    except Exception as e:
        target_session.rollback()
        print(f"❌ 迁移失败: {e}")
        raise
    finally:
        source_session.close()
        target_session.close()


# 执行迁移
migrate_tables()
