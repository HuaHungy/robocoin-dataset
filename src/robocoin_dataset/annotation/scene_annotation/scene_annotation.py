import glob
import json
import logging
from pathlib import Path

import tqdm
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from robocoin_dataset.annotation.scene_annotation.dataset_scene_annotation_embedding import (
    SceneAnnotationEmbedding,
)
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, TaskStatus
from robocoin_dataset.distribution_computation.constant import (
    ERR_MSG,
    TASK_RESULT_STATUS,
    TASK_SUCCESS,
)
from robocoin_dataset.distribution_computation.task_client import TaskClient
from robocoin_dataset.distribution_computation.task_server import TaskServer


def _sync_scene_annotation_status(session: Session) -> None:
    query = session.query(DatasetDB).filter(
        and_(
            # 必要前提：convert必须成功
            DatasetDB.convert_status == TaskStatus.COMPLETED,
            # 两个触发分支
            or_(
                # 分支1: 正在排队
                DatasetDB.scene_annotation_status == TaskStatus.PENDING,
                # 分支2: 已完成但版本过期
                and_(
                    DatasetDB.scene_annotation_status == TaskStatus.COMPLETED,
                    DatasetDB.scene_annotation_version_ps < DatasetDB.convert_version,
                ),
            ),
        )
    )
    items = query.all()

    if not items:
        return
    for item in items:
        item.scene_annotation_status = TaskStatus.PENDING
        item.scene_annotation_version = item.scene_annotation_version + 1
        item.scene_annotation_version_ps = item.convert_version

    session.commit()


def _get_scene_annotation_task_num(session: Session) -> int:
    return (
        session.query(DatasetDB)
        .filter(
            DatasetDB.scene_annotation_status == TaskStatus.PENDING,
        )
        .filter(
            DatasetDB.convert_status == TaskStatus.COMPLETED,
        )
        .count()
    )


def _gen_one_scene_annotation_task(session: Session) -> tuple[str | None, str | None]:
    query = (
        session.query(DatasetDB)
        .filter(
            DatasetDB.scene_annotation_status == TaskStatus.PENDING,
        )
        .filter(
            DatasetDB.convert_status == TaskStatus.COMPLETED,
        )
    )
    item = query.first()
    if not item:
        return None, None
    item.scene_annotation_status = TaskStatus.PROCESSING
    session.commit()
    return (
        item.dataset_uuid,
        item.convert_path,
    )


# local converter
class SceneAnnotationLocal:
    def __init__(
        self,
        db_file_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def process_folder(self, folder: str | Path) -> None:
        folder = Path(folder).expanduser().absolute()
        try:
            if not folder.exists():
                raise FileNotFoundError(f"文件夹 {folder} 不存在")
            dataset_folders = [d for d in folder.iterdir() if d.is_dir()]
            if not dataset_folders:
                raise FileNotFoundError(f"文件夹 {folder} 下没有数据集文件夹")
            self.logger.info(f"在文件夹 {folder} 发现 {len(dataset_folders)} 个数据集文件夹:")
            self.logger.info("开始处理所有数据集的JSON到parquet转换...")

            success_count = 0
            failed_count = 0
            for dataset_folder in tqdm.tqdm(dataset_folders, desc="处理数据集", unit="数据集"):
                dataset_name = dataset_folder.name
                self.logger.info(f"检查数据集 {dataset_name} 的完成状态...")
                with self.db.with_session() as session:
                    # 数据集名查找dataset_uuid
                    dataset_record = (
                        session.query(DatasetDB)
                        # 转换路径中包含数据集名 匹配正则表达式:*dataset_name*
                        .filter(DatasetDB.convert_path.like(f"%{dataset_name}%"))
                        .first()
                    )
                    if not dataset_record:
                        self.logger.warning(f"未找到数据集 {dataset_name} 的记录，跳过")
                        failed_count += 1
                        continue
                    if dataset_record.scene_annotation_status == TaskStatus.COMPLETED:
                        self.logger.info(f"数据集 {dataset_name} 的场景注释已经完成，跳过")
                        continue

                    json_pattern = str(dataset_folder / "episode_*.json")
                    json_files = glob.glob(json_pattern)

                    if not json_files:
                        self.logger.warning(f"数据集 {dataset_name} 中没有找到JSON文件，跳过")
                        failed_count += 1
                        continue

                    descriptions = []
                    for json_file in json_files:
                        with open(json_file, encoding="utf-8") as f:
                            data = json.load(f)
                            if "description" in data:
                                descriptions.append(data["description"])

                    if not descriptions:
                        self.logger.warning(
                            f"数据集 {dataset_name} 中没有找到有效的description，跳过"
                        )
                        failed_count += 1
                        continue

                    # 调用场景注释嵌入
                    scene_embedding = SceneAnnotationEmbedding(self.db_file_path)
                    scene_embedding.dataset_scene_embedding(
                        dataset_uuid=dataset_record.dataset_uuid, scene_annotations=descriptions
                    )

                    # 更新状态为完成
                    dataset_record.scene_annotation_status = TaskStatus.COMPLETED
                    session.commit()

                    self.logger.info(f"数据集 {dataset_name} 场景注释处理完成")
                    success_count += 1

            self.logger.info(f"\n处理完成！成功: {success_count}, 失败: {failed_count}")

        except Exception as e:
            self.logger.error(f"处理文件夹 {folder} 时发生错误: {e}")
            return

    def syn_scene_annotation_task(self) -> None:
        try:
            with self.db.with_session() as session:
                _sync_scene_annotation_status(session)
        except Exception as e:
            raise RuntimeError("SYN TASK ERROR") from e

    def online_process(self) -> None:
        pass


class SceneAnnotationServer(TaskServer):
    def __init__(self, db_file_path: str | Path, **kwargs: dict) -> None:
        super().__init__(**kwargs)
        self.db = DatasetDatabase(Path(db_file_path).expanduser().absolute())

    def get_task_category(self) -> str:
        return "scene_annotation"

    def generate_task_content(self) -> dict | None:
        """获取下一个待处理任务"""
        try:
            with self.db.with_session() as session:
                # 先查看数据库中有多少条记录
                total_count = session.query(DatasetDB).count()
                print(f"数据库总记录数: {total_count}")

                # 查询待处理任务（只查询 PENDING 和 FAILED 状态）
                task = (
                    session.query(DatasetDB.dataset_uuid, DatasetDB.convert_path)
                    .filter(
                        DatasetDB.convert_status == TaskStatus.COMPLETED,
                        DatasetDB.scene_annotation_status.in_(
                            [
                                TaskStatus.PENDING,
                            ]
                        ),
                    )
                    .first()
                )

                if not task:
                    print("没有找到待处理的任务")
                    # 查看有哪些状态的任务
                    status_counts = (
                        session.query(
                            DatasetDB.scene_annotation_status,
                            session.query(DatasetDB)
                            .filter(
                                DatasetDB.scene_annotation_status
                                == DatasetDB.scene_annotation_status
                            )
                            .count(),
                        )
                        .group_by(DatasetDB.scene_annotation_status)
                        .all()
                    )
                    print(f"各状态任务数量: {status_counts}")
                    return None

                dataset_uuid, convert_path = task
                print(f"找到任务: dataset_uuid={dataset_uuid}, convert_path={convert_path}")

                # 更新状态为处理中
                updated = (
                    session.query(DatasetDB)
                    .filter(DatasetDB.dataset_uuid == dataset_uuid)
                    .update({DatasetDB.scene_annotation_status: TaskStatus.PROCESSING})
                )
                session.commit()

                print(f"更新了 {updated} 条记录状态为 PROCESSING")

                result = {"dataset_uuid": dataset_uuid, "leformat_path": convert_path}
                print(f"返回任务内容: {result}")
                return result

        except Exception as e:
            print(f"generate_task_content 错误: {e}")
            import traceback

            traceback.print_exc()
            return None

    def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
        """处理任务结果"""
        task_result_content = task_result_content.get("task_result_content")
        ds_uuid = task_content.get("dataset_uuid")
        task_status = task_result_content.get(TASK_RESULT_STATUS)
        print(task_result_content)
        print(task_status)
        status = TaskStatus.COMPLETED if task_status == TASK_SUCCESS else TaskStatus.FAILED

        with self.db.with_session() as session:
            update_data = {DatasetDB.scene_annotation_status: status}
            if status == TaskStatus.FAILED:
                update_data[DatasetDB.scene_annotation_err_msg] = task_result_content.get("task_result_content").get("error")

            updated_rows = (
                session.query(DatasetDB)
                .filter(DatasetDB.dataset_uuid == ds_uuid)
                .update(update_data)
            )

            if updated_rows == 0:
                raise ValueError(f"Dataset {ds_uuid} not found")
            session.commit()


class SceneAnnotationClient(TaskClient):
    def __init__(
        self,
        server_uri: str = "ws://localhost:8769",  # 匹配服务端端口
        heartbeat_interval: float = 10.0,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            server_uri=server_uri,
            heartbeat_interval=heartbeat_interval,
            logger=logger,
        )

    def get_task_category(self) -> str:
        return "scene_annotation"

    def generate_task_request_desc(self) -> dict:
        """客户端可自定义任务请求参数"""
        return {}

    def _sync_process_task(self, task_content: dict) -> dict:
        try:
            dataset_uuid = task_content.get("dataset_uuid")
            dataset_path = task_content.get("leformat_path")

            if not dataset_uuid or not dataset_path:
                raise ValueError("Missing required task parameters: dataset_uuid or dataset_path")

            # 使用SceneAnnotationEmbedding处理场景标注
            scene_annotation_embedding = SceneAnnotationEmbedding(
                database_file="/tmp/dummy.db"  # 客户端不需要数据库操作
            )

            # 从数据集路径提取场景描述
            dataset_path = Path(dataset_path)
            descriptions = []

            # 读取meta/episodes.jsonl文件获取场景描述
            episodes_file = dataset_path / "meta" / "episodes.jsonl"
            if episodes_file.exists():
                import json

                with open(episodes_file, encoding="utf-8") as f:
                    for line in f:
                        episode_data = json.loads(line.strip())
                        description = episode_data.get("scene_description", "")
                        if description:
                            descriptions.append(description)

            if not descriptions:
                self.logger.warning(f"No scene descriptions found for dataset {dataset_uuid}")
                return {"scene_annotations_processed": 0}

            # 处理场景标注嵌入
            scene_annotation_embedding.dataset_scene_embedding(dataset_uuid, descriptions)

            return {"scene_annotations_processed": len(descriptions), "dataset_uuid": dataset_uuid}

        except Exception as e:
            raise RuntimeError(f"Scene annotation processing for {dataset_path} failed") from e


if __name__ == "__main__":
    pass
