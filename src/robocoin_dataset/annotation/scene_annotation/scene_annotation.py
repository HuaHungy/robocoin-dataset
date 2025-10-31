import logging
from pathlib import Path

import tqdm
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session


from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    TaskStatus
)

from robocoin_dataset.distribution_computation.constant import (
    DATASET_UUID,
    ERR_MSG,
    TASK_RESULT_CONTENT,
    TASK_RESULT_STATUS,
    TASK_SUCCESS,
)

from robocoin_dataset.distribution_computation.task_client import TaskClient
from robocoin_dataset.distribution_computation.task_server import TaskServer
from robocoin_dataset.format_converter.tolerobot.constant import (
    LEFORMAT_PATH,
)


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
        .count()
    )

def _gen_one_scene_annotation_task(session: Session) -> tuple[str | None, str | None]:
    query = session.query(DatasetDB).filter(
        DatasetDB.scene_annotation_status == TaskStatus.PENDING,
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
class SceneAnnotation:
    def __init__(
        self,
        db_file_path: str | Path,
        json_file_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.json_file_path: Path = Path(json_file_path).expanduser().absolute()
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
            print(f"在文件夹 {folder} 发现 {len(dataset_folders)} 个数据集文件夹:")
            print(f"开始处理所有数据集的JSON到parquet转换...")
            success_count = 0
            failed_count = 0
            for dataset_folder in tqdm(dataset_folders, desc="处理数据集", unit="数据集"):
                dataset_name = dataset_folder.name
                print(f"检查数据集 {dataset_name} 的完成状态...")
                with self.db.with_session() as session:
                    # 数据集名查找dataset_uuid
                    dataset_record = (
                        session.query(DatasetDB)
                        # 转换路径中包含数据集名 匹配正则表达式:*dataset_name*
                        .filter(DatasetDB.convert_path.like(f'%{dataset_name}%'))
                        .first()
                    )
                    if not dataset_record:
                        print(f"未找到数据集 {dataset_name} 的记录，跳过")
                        failed_count += 1
                        continue
                    if dataset_record.scene_annotation_embedding_status == TaskStatus.COMPLETED:
                        print(f"数据集 {dataset_name} 的场景注释已经完成，跳过")
                        continue

                
        except Exception as e:
            self.logger.error(f"处理文件夹 {folder} 时发生错误: {e}")
            return
if __name__ == "__main__":
    scene_annotation = SceneAnnotation(
        db_file_path="/mnt/nas/synnas/docker2/scene_annotation/dataset.db",
        json_file_path="/mnt/nas/synnas/docker2/scene_annotation/episode_*.json",
    )
    scene_annotation.process_folder("/mnt/nas/synnas/docker2/scene_annotation")
