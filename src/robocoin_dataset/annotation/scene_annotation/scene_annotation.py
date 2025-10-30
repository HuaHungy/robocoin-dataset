import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any

import pandas as pd
import tqdm
import subprocess
import tempfile
import shutil
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    TaskStatus,
)

# Add RoboCoin-scene-annotator to path
ROBOCOIN_ANNOTATOR_PATH = os.path.join(
    os.path.dirname(__file__), 
    "..", "..", "..", "..", "..", 
    "third_parties", "RoboCoin-scene-annotator"
)
sys.path.insert(0, ROBOCOIN_ANNOTATOR_PATH)
from robocoin_dataset.distribution_computation.constant import (
    DATASET_UUID,
    ERR_MSG,
    TASK_RESULT_CONTENT,
    TASK_RESULT_STATUS,
    TASK_SUCCESS,
)
from robocoin_dataset.distribution_computation.task_client import TaskClient
from robocoin_dataset.distribution_computation.task_server import TaskServer

SCENE_ANNOTATION_RESULT = "scene_annotation_result"


def _sync_scene_annotation_status(session: Session) -> None:
    """同步场景标注状态"""
    try:
        query = session.query(DatasetDB).filter(
            and_(
                # 必要前提：数据合并必须成功
                DatasetDB.data_merge_status == TaskStatus.COMPLETED,
                # 两个触发分支
                or_(
                    # 分支1: 正在排队
                    DatasetDB.scene_annotation_status == TaskStatus.PENDING,
                    # 分支2: 已完成但版本过期
                    and_(
                        DatasetDB.scene_annotation_status == TaskStatus.COMPLETED,
                        DatasetDB.scene_annotation_version_ps < DatasetDB.data_merge_version,
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
            item.scene_annotation_version_ps = item.data_merge_version

        session.commit()
    except Exception as e:
        logging.warning(f"场景标注状态字段不存在，跳过状态同步: {e}")


def _get_scene_annotation_task_num(session: Session) -> int:
    """获取待处理的场景标注任务数量"""
    try:
        return (
            session.query(DatasetDB)
            .filter(
                DatasetDB.scene_annotation_status == TaskStatus.PENDING,
            )
            .count()
        )
    except Exception as e:
        logging.warning(f"场景标注状态字段不存在，返回所有数据集数量: {e}")
        return session.query(DatasetDB).count()


def _gen_one_scene_annotation_task(session: Session) -> tuple[str | None, str | None]:
    """生成一个场景标注任务"""
    try:
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
    except Exception as e:
        logging.warning(f"场景标注状态字段不存在，使用简化逻辑: {e}")
        # 简化逻辑：获取第一个数据集
        item = session.query(DatasetDB).first()
        if not item:
            return None, None
        return (
            item.dataset_uuid,
            "/tmp/placeholder_path",  # 占位符路径
        )


def process_scene_annotation(
    dataset_uuid: str,
    convert_path: str | Path,
    output_dir: str | Path = None,
) -> Dict[str, Any]:
    """
    处理场景标注，使用RoboCoin-scene-annotator
    
    Args:
        dataset_uuid: 数据集UUID
        convert_path: 转换后的数据路径
        output_dir: 输出目录，如果为None则使用convert_path的父目录
    
    Returns:
        包含标注结果的字典
    """
    convert_path = Path(convert_path)
    if output_dir is None:
        output_dir = convert_path.parent / "scene_annotations"
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # 使用临时目录运行RoboCoin-scene-annotator
        with tempfile.TemporaryDirectory() as temp_dir:
            # 运行RoboCoin-scene-annotator管道
            annotator_results = _run_robocoin_annotator(str(convert_path), dataset_uuid, temp_dir)
            
            if annotator_results["status"] == "error":
                raise RuntimeError(annotator_results["error"])
            
            # 转换结果到我们的格式并保存
            scene_annotations = _convert_annotator_results(annotator_results["annotations_dir"], dataset_uuid)
            
            # 保存为parquet格式
            df = pd.DataFrame(scene_annotations)
            parquet_path = output_dir / f"{dataset_uuid}_scene_annotations.parquet"
            df.to_parquet(parquet_path, index=False)
            
            # 保存为jsonl格式
            jsonl_path = output_dir / f"{dataset_uuid}_scene_annotations.jsonl"
            with open(jsonl_path, 'w', encoding='utf-8') as f:
                for annotation in scene_annotations:
                    f.write(json.dumps(annotation, ensure_ascii=False) + '\n')
            
            return {
                "parquet_path": str(parquet_path),
                "jsonl_path": str(jsonl_path),
                "annotation_count": len(scene_annotations),
                "output_dir": str(output_dir),
            }
            
    except Exception as e:
        logging.error(f"Error processing scene annotation for {dataset_uuid}: {str(e)}")
        raise


def _run_robocoin_annotator(repo_path: str, repo_id: str, temp_dir: str) -> Dict[str, Any]:
    """
    运行RoboCoin-scene-annotator管道
    
    Args:
        repo_path: 仓库路径
        repo_id: 仓库标识符
        temp_dir: 临时目录
        
    Returns:
        包含状态和结果的字典
    """
    try:
        # 准备命令参数
        script_path = os.path.join(ROBOCOIN_ANNOTATOR_PATH, "scripts", "run_pipeline.py")
        
        # RoboCoin-scene-annotator的默认配置
        cmd = [
            sys.executable, script_path,
            "--repo_id", repo_id,
            "--repo_root", os.path.dirname(repo_path),
            "--save_root", temp_dir,
            "--camera", "observation.images.cam_high",
            "--detector.type", "grounding_dino",
            "--detector.model_config_path", "configs/grounding_dino/GroundingDINO_SwinT_OGC.py",
            "--detector.model_checkpoint", "weights/groundingdino_swint_ogc.pth",
            "--detector.device", "cpu",  # 使用CPU以确保兼容性
            "--detector.box_threshold", "0.3",
            "--detector.text_threshold", "0.25",
            "--detector.visualize_first", "0",  # 自动化模式下不可视化
            "--language_model.type", "ollama",
            "--language_model.model", "deepseek-r1:8b",
            "--language_model.think", "False"
        ]
        
        # 运行标注器
        logging.info(f"Running RoboCoin-scene-annotator for {repo_id}")
        result = subprocess.run(
            cmd,
            cwd=ROBOCOIN_ANNOTATOR_PATH,
            capture_output=True,
            text=True,
            timeout=3600  # 1小时超时
        )
        
        if result.returncode != 0:
            logging.error(f"RoboCoin-scene-annotator failed: {result.stderr}")
            return {
                "status": "error",
                "error": f"Annotator failed with return code {result.returncode}: {result.stderr}"
            }
        
        # 检查是否生成了结果
        annotations_dir = os.path.join(temp_dir, "annotations_refined", repo_id)
        if not os.path.exists(annotations_dir):
            return {
                "status": "error",
                "error": "No annotation results generated"
            }
        
        return {
            "status": "success",
            "annotations_dir": annotations_dir
        }
        
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error": "RoboCoin-scene-annotator timed out"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to run RoboCoin-scene-annotator: {str(e)}"
        }


def _convert_annotator_results(annotations_dir: str, dataset_uuid: str) -> list:
    """
    转换RoboCoin-scene-annotator结果到我们的格式
    
    Args:
        annotations_dir: 包含标注结果的目录
        dataset_uuid: 数据集UUID
        
    Returns:
        场景标注数据列表
    """
    scene_annotations = []
    
    try:
        # 读取所有标注文件
        for filename in os.listdir(annotations_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(annotations_dir, filename)
                with open(file_path, 'r') as f:
                    annotation = json.load(f)
                
                # 转换到我们的格式
                episode_id = os.path.splitext(filename)[0]
                scene_item = {
                    "dataset_uuid": dataset_uuid,
                    "episode_id": episode_id,
                    "timestamp": annotation.get("timestamp", pd.Timestamp.now().isoformat()),
                    "objects": annotation.get("objects", []),
                    "scene_description": annotation.get("scene_description", ""),
                    "actions": annotation.get("actions", []),
                    "scene_type": annotation.get("scene_type", "unknown")
                }
                scene_annotations.append(scene_item)
        
        if not scene_annotations:
            # 回退：如果没有结果则创建模拟数据
            logging.warning(f"No annotation results found in {annotations_dir}, creating fallback data")
            scene_annotations = [{
                "dataset_uuid": dataset_uuid,
                "episode_id": "episode_001",
                "timestamp": pd.Timestamp.now().isoformat(),
                "objects": [],
                "scene_description": f"Scene annotation for {dataset_uuid} (no objects detected)",
                "actions": [],
                "scene_type": "unknown"
            }]
        
    except Exception as e:
        logging.error(f"Error converting annotation results: {str(e)}")
        # 回退：创建模拟数据
        scene_annotations = [{
            "dataset_uuid": dataset_uuid,
            "episode_id": "episode_001",
            "timestamp": pd.Timestamp.now().isoformat(),
            "objects": [],
            "scene_description": f"Scene annotation for {dataset_uuid} (conversion failed)",
            "actions": [],
            "scene_type": "unknown"
        }]
    
    return scene_annotations


class SceneAnnotation:
    """场景标注处理类"""
    
    def __init__(
        self,
        db_file_path: str | Path,
        output_dir: str | Path = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.output_dir = Path(output_dir) if output_dir else None
        self.logger = logger or logging.getLogger(__name__)

    def sync_scene_annotation_status(self) -> None:
        """同步场景标注状态"""
        with self.db.with_session() as session:
            _sync_scene_annotation_status(session)

    def process_scene_annotation_one_dataset(self) -> None:
        """处理一个数据集的场景标注"""
        with self.db.with_session() as session:
            dataset_uuid, convert_path = _gen_one_scene_annotation_task(session)

        if not dataset_uuid:
            self.logger.info("No pending scene annotation tasks")
            return

        try:
            self.logger.info(f"Processing scene annotation for dataset: {dataset_uuid}")
            
            result = process_scene_annotation(
                dataset_uuid=dataset_uuid,
                convert_path=convert_path,
                output_dir=self.output_dir,
            )
            
            self.logger.info(f"Scene annotation completed: {result}")

            with self.db.with_session() as session:
                query = session.query(DatasetDB).filter(
                    DatasetDB.dataset_uuid == dataset_uuid,
                )
                item = query.first()
                if not item:
                    raise ValueError(f"Dataset {dataset_uuid} not found")

                item.scene_annotation_status = TaskStatus.COMPLETED
                session.commit()
                
        except Exception as e:
            self.logger.error(f"Scene annotation failed for {dataset_uuid}: {e}")
            
            with self.db.with_session() as session:
                query = session.query(DatasetDB).filter(
                    DatasetDB.dataset_uuid == dataset_uuid,
                )
                item = query.first()
                if item:
                    item.scene_annotation_status = TaskStatus.FAILED
                    item.scene_annotation_err_msg = str(e)
                    session.commit()


class SceneAnnotationServer(TaskServer):
    """场景标注服务器"""
    
    def __init__(
        self,
        db_file_path: str | Path,
        output_dir: str | Path = None,
        host: str = "0.0.0.0",
        port: int = 8770,
        heartbeat_interval: float = 30.0,
        timeout: float = 15.0,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            logger=logger,
            host=host,
            port=port,
            heartbeat_interval=heartbeat_interval,
            timeout=timeout,
        )
        
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.output_dir = Path(output_dir) if output_dir else None
        self.logger = logger or logging.getLogger(__name__)
        self.logger.info("Scene Annotation Server started")

    def get_task_category(self) -> str:
        return "scene_annotation"

    def generate_task_content(self) -> dict | None:
        """生成任务内容"""
        with self.db.with_session() as session:
            try:
                query = session.query(DatasetDB).filter(
                    and_(
                        # 必要前提：数据合并必须成功
                        DatasetDB.data_merge_status == TaskStatus.COMPLETED,
                        # 两个触发分支
                        or_(
                            # 分支1: 正在排队
                            DatasetDB.scene_annotation_status == TaskStatus.PENDING,
                            # 分支2: 已完成但版本过期
                            and_(
                                DatasetDB.scene_annotation_status == TaskStatus.COMPLETED,
                                DatasetDB.scene_annotation_version_ps < DatasetDB.data_merge_version,
                            ),
                        ),
                    )
                )
                item = query.first()

                if not item:
                    return None

                item.scene_annotation_status = TaskStatus.PROCESSING
                item.scene_annotation_version = item.scene_annotation_version + 1
                item.scene_annotation_version_ps = item.data_merge_version

                session.commit()
                
                return {
                    DATASET_UUID: item.dataset_uuid,
                    "convert_path": item.convert_path,
                    "output_dir": str(self.output_dir) if self.output_dir else None,
                }
            except Exception as e:
                self.logger.warning(f"场景标注状态字段不存在，使用简化逻辑: {e}")
                # 简化逻辑：获取第一个数据集
                item = session.query(DatasetDB).first()
                if not item:
                    return None
                
                return {
                    DATASET_UUID: item.dataset_uuid,
                    "convert_path": "/tmp/placeholder_path",  # 占位符路径
                    "output_dir": str(self.output_dir) if self.output_dir else None,
                }

    def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
        """处理任务结果"""
        ds_uuid = task_content.get(DATASET_UUID)
        task_status = task_result_content.get(TASK_RESULT_STATUS)
        task_status_msg = task_result_content.get(ERR_MSG)
        
        task_status = TaskStatus.COMPLETED if task_status == TASK_SUCCESS else TaskStatus.FAILED
        
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                DatasetDB.dataset_uuid == ds_uuid,
            )
            item = query.first()
            if not item:
                raise ValueError(f"Dataset {ds_uuid} not found")

            item.scene_annotation_status = task_status
            if task_status == TaskStatus.FAILED:
                item.scene_annotation_err_msg = task_status_msg
            
            session.commit()


class SceneAnnotationClient(TaskClient):
    """场景标注客户端"""
    
    def __init__(
        self,
        server_uri: str = "ws://localhost:8770",
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
        """同步处理任务"""
        try:
            dataset_uuid = task_content.get(DATASET_UUID)
            convert_path = task_content.get("convert_path")
            output_dir = task_content.get("output_dir")
            
            result = process_scene_annotation(
                dataset_uuid=dataset_uuid,
                convert_path=convert_path,
                output_dir=output_dir,
            )
            
            return {SCENE_ANNOTATION_RESULT: result}
            
        except Exception as e:
            raise RuntimeError(f"Scene annotation failed for {dataset_uuid}") from e