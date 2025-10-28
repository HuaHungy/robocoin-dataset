import logging

from sqlalchemy import select

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    AtomicActionDB,
    DatasetDB,
    ObjectDB,
    SceneTypeDB,
    TaskDescriptionDB,
    dataset_atomic_actions,
    dataset_objects,
    dataset_scene_types,
    dataset_task_descriptions,
)

logger = logging.getLogger(__name__)


def upsert_dataset_info(yaml_data: dict[str, any], db_path: str) -> None:
    """
    将 YAML 字典写入数据库。
    每次调用内部自己创建 Session、自己提交，保证线程安全。
    """
    db = DatasetDatabase(db_path)
    with db.with_session() as session:
        try:
            # 1. 基础字段
            dataset_data = {
                "dataset_name": yaml_data["dataset_name"],
                "dataset_uuid": yaml_data["dataset_uuid"],
                "end_effector_type": yaml_data.get("end_effector_type"),
                "operation_platform_height": yaml_data.get("operation_platform_height"),
                "yaml_file_path": yaml_data.get("yaml_file_path"),
            }
            device_model = yaml_data.get("device_model")
            if isinstance(device_model, list):
                dataset_data["device_model"] = device_model[0] if device_model else None
            else:
                dataset_data["device_model"] = device_model
            dataset_data = {k: v for k, v in dataset_data.items() if v is not None}

            # 2. 多对多字段
            scene_type_names = yaml_data.get("scene_type", [])
            task_descs = (
                yaml_data.get("task_descriptions", [])
                or yaml_data.get("task_description", [])
                or yaml_data.get("task_desc", [])
            )
            yaml_objects = yaml_data.get("objects", [])

            # 3. scene_type —— 存在就复用
            scene_types = []
            for name in scene_type_names:
                st = session.query(SceneTypeDB).filter_by(name=name).first()
                if not st:
                    st = SceneTypeDB(name=name)
                    session.add(st)
                scene_types.append(st)

            # 4. task_descriptions —— 存在就复用（核心修复点）
            task_desc_map = {}
            for desc in task_descs:
                td = session.query(TaskDescriptionDB).filter_by(desc=desc).first()
                if not td:
                    td = TaskDescriptionDB(desc=desc)
                    session.add(td)
                    # 立即 flush，让 td.id 生成，同时避免并发重复
                    session.flush()
                task_desc_map[td.id] = td
            task_descriptions = list(task_desc_map.values())

            # 5. objects
            db_objects = []
            for obj in yaml_objects:
                if not isinstance(obj, dict):
                    continue
                name = obj.get("object_name")
                if not name:
                    continue
                ob = session.query(ObjectDB).filter_by(object_name=name).first()
                if not ob:
                    ob = ObjectDB(object_name=name)
                ob.level1_category = obj.get("level1")
                ob.level2_category = obj.get("level2")
                ob.level3_category = obj.get("level3")
                ob.level4_category = obj.get("level4")
                ob.level5_category = obj.get("level5")
                session.add(ob)
                db_objects.append(ob)

            # 6. dataset 本体 —— uuid 主键冲突则更新
            ds = (
                session.query(DatasetDB)
                .filter_by(dataset_uuid=dataset_data["dataset_uuid"])
                .first()
            )
            if not ds:
                ds = DatasetDB(**dataset_data)
                session.add(ds)
            else:
                for k, v in dataset_data.items():
                    setattr(ds, k, v)
            session.flush()

            # 7. 建立多对多关联
            for obj in db_objects:
                exists = (
                    session.execute(
                        select(dataset_objects.c.object_id)
                        .where(dataset_objects.c.dataset_id == ds.id)
                        .where(dataset_objects.c.object_id == obj.id)
                    ).first()
                    is not None
                )

                if not exists:
                    session.execute(
                        dataset_objects.insert().values(dataset_id=ds.id, object_id=obj.id)
                    )

            for st in scene_types:
                exists = (
                    session.execute(
                        select(dataset_scene_types.c.scene_type_id)
                        .where(dataset_scene_types.c.dataset_id == ds.id)
                        .where(dataset_scene_types.c.scene_type_id == st.id)
                    ).first()
                    is not None
                )

                if not exists:
                    session.execute(
                        dataset_scene_types.insert().values(dataset_id=ds.id, scene_type_id=st.id)
                    )

            for td in task_descriptions:
                exists = (
                    session.execute(
                        select(dataset_task_descriptions.c.task_description_id)
                        .where(dataset_task_descriptions.c.dataset_id == ds.id)
                        .where(dataset_task_descriptions.c.task_description_id == td.id)
                    ).first()
                    is not None
                )

                if not exists:
                    session.execute(
                        dataset_task_descriptions.insert().values(
                            dataset_id=ds.id, task_description_id=td.id
                        )
                    )

            # 8. 处理 atomic_actions：建立 dataset 与 atomic_action 的多对多关联
            atomic_actions = yaml_data.get("atomic_actions", [])
            for action_name in atomic_actions:
                if not action_name or not isinstance(action_name, str):
                    continue

                # 步骤1: 获取或创建 AtomicActionDB 记录（全局唯一）
                atomic_action = (
                    session.query(AtomicActionDB).filter_by(action_name=action_name).first()
                )
                if not atomic_action:
                    atomic_action = AtomicActionDB(action_name=action_name)
                    session.add(atomic_action)
                    session.flush()  # 立即生成 id，供后续使用

                # 步骤2: 检查是否已关联（查询中间表）
                exists = (
                    session.execute(
                        select(dataset_atomic_actions.c.atomic_actions_id)
                        .where(dataset_atomic_actions.c.dataset_id == ds.id)
                        .where(dataset_atomic_actions.c.atomic_actions_id == atomic_action.id)
                    ).first()
                    is not None
                )

                # 步骤3: 如果未关联，则插入中间表
                if not exists:
                    session.execute(
                        dataset_atomic_actions.insert().values(
                            dataset_id=ds.id, atomic_actions_id=atomic_action.id
                        )
                    )

            # 8. 一次性提交
            session.commit()
            logger.info("Upsert completed for dataset: %s", yaml_data.get("dataset_name"))

        except Exception as e:
            session.rollback()
            logger.error("Upsert failed for %s: %s", yaml_data.get("dataset_name"), e)
            raise
