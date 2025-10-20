import logging
from pathlib import Path

import torch
import torch.utils.data
from sqlalchemy import and_, not_
from sqlalchemy.orm import Session

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DmvAnnotationDB,
    LeFormatConvertDB,
    LeformatDatasetFormatCheckStatusDB,
    TaskStatus,
)


class LerobotDataFormatCheck:
    def __init__(
        self,
        db_file_path: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)

    def _check_dataset(self, dataset_uuid: str) -> None:
        """检查单个数据集的核心方法 - 遍历所有episode和frame"""
        # 延迟导入以避免循环依赖
        from lerobot.datasets.lerobot_dataset import LeRobotDataset

        convert_path = self._get_convert_path(dataset_uuid)
        if not convert_path:
            raise RuntimeError(f"No convert path found for dataset {dataset_uuid}")

        self.logger.info(f"Loading dataset from {convert_path}")
        dataset = LeRobotDataset(convert_path)

        total_episodes = dataset.num_episodes
        self.logger.info(f"Dataset has {total_episodes} episodes")

        # 遍历每个 episode
        for episode_idx in range(total_episodes):
            self.logger.info(f"Checking episode {episode_idx + 1}/{total_episodes}")

            # 获取该 episode 的数据范围
            from_idx = dataset.episode_data_index["from"][episode_idx].item()
            to_idx = dataset.episode_data_index["to"][episode_idx].item()
            frame_ids = range(from_idx, to_idx)

            self.logger.info(f"Episode {episode_idx} has {len(frame_ids)} frames")

            # 遍历该 episode 的每一帧（这是核心循环，类似 visualize_dataset.py 的逻辑）
            for frame_idx in frame_ids:
                try:
                    # 获取单帧数据
                    frame_data = dataset[frame_idx]

                    # 检查必要的键是否存在
                    required_keys = ["frame_index", "timestamp"]
                    for key in required_keys:
                        if key not in frame_data:
                            raise ValueError(
                                f"Episode {episode_idx}, Frame {frame_idx}: Missing required key '{key}'"
                            )

                    # 检查相机图像（对应 visualize_dataset.py 中的 display camera images）
                    for camera_key in dataset.meta.camera_keys:
                        if camera_key not in frame_data:
                            raise ValueError(
                                f"Episode {episode_idx}, Frame {frame_idx}: Missing camera key '{camera_key}'"
                            )
                        image = frame_data[camera_key]
                        if not isinstance(image, torch.Tensor):
                            raise TypeError(
                                f"Episode {episode_idx}, Frame {frame_idx}: Camera '{camera_key}' is not a torch.Tensor"
                            )
                        if image.ndim != 3:
                            raise ValueError(
                                f"Episode {episode_idx}, Frame {frame_idx}: Camera '{camera_key}' image shape is {image.shape}, expected 3D tensor (C, H, W)"
                            )
                        # 检查图像数据范围
                        if image.min() < 0 or image.max() > 1:
                            raise ValueError(
                                f"Episode {episode_idx}, Frame {frame_idx}: Camera '{camera_key}' image values out of range [0, 1]: min={image.min()}, max={image.max()}"
                            )

                    # 检查 action（对应 visualize_dataset.py 中的 action space）
                    if "action" in frame_data:
                        action = frame_data["action"]
                        if not isinstance(action, torch.Tensor):
                            raise TypeError(
                                f"Episode {episode_idx}, Frame {frame_idx}: 'action' is not a torch.Tensor"
                            )
                        if action.ndim != 1:
                            raise ValueError(
                                f"Episode {episode_idx}, Frame {frame_idx}: 'action' shape is {action.shape}, expected 1D tensor"
                            )
                        # 检查是否有 NaN 或 Inf
                        if torch.isnan(action).any():
                            raise ValueError(
                                f"Episode {episode_idx}, Frame {frame_idx}: 'action' contains NaN values"
                            )
                        if torch.isinf(action).any():
                            raise ValueError(
                                f"Episode {episode_idx}, Frame {frame_idx}: 'action' contains Inf values"
                            )

                    # 检查 observation.state（对应 visualize_dataset.py 中的 state space）
                    if "observation.state" in frame_data:
                        state = frame_data["observation.state"]
                        if not isinstance(state, torch.Tensor):
                            raise TypeError(
                                f"Episode {episode_idx}, Frame {frame_idx}: 'observation.state' is not a torch.Tensor"
                            )
                        if state.ndim != 1:
                            raise ValueError(
                                f"Episode {episode_idx}, Frame {frame_idx}: 'observation.state' shape is {state.shape}, expected 1D tensor"
                            )
                        # 检查是否有 NaN 或 Inf
                        if torch.isnan(state).any():
                            raise ValueError(
                                f"Episode {episode_idx}, Frame {frame_idx}: 'observation.state' contains NaN values"
                            )
                        if torch.isinf(state).any():
                            raise ValueError(
                                f"Episode {episode_idx}, Frame {frame_idx}: 'observation.state' contains Inf values"
                            )

                    # 检查其他可选字段（对应 visualize_dataset.py 中的 next.done, next.reward, next.success）
                    optional_keys = ["next.done", "next.reward", "next.success"]
                    for key in optional_keys:
                        if key in frame_data:
                            value = frame_data[key]
                            if not isinstance(value, (torch.Tensor, int, float, bool)):
                                raise TypeError(
                                    f"Episode {episode_idx}, Frame {frame_idx}: '{key}' has invalid type {type(value)}"
                                )

                except Exception as e:  # noqa: PERF203
                    raise RuntimeError(
                        f"Error checking episode {episode_idx}, frame {frame_idx}: {str(e)}"
                    ) from e

            self.logger.info(f"Episode {episode_idx} check completed successfully")

        self.logger.info(f"Dataset {dataset_uuid} check completed successfully")

    def _get_convert_path(self, dataset_uuid: str) -> str:
        with self.db.with_session() as session:
            item = (
                session.query(LeFormatConvertDB)
                .filter(LeFormatConvertDB.dataset_uuid == dataset_uuid)
                .first()
            )
            if item:
                return item.convert_path
            return None

    def _upsert_leformat_dataset_check_status(
        self,
        session: Session,
        dataset_uuid: str,
        convert_path: str,
        status: TaskStatus,
        err_msg: str = "",
    ) -> None:
        item = (
            session.query(LeformatDatasetFormatCheckStatusDB)
            .filter(LeformatDatasetFormatCheckStatusDB.dataset_uuid == dataset_uuid)
            .first()
        )
        if item:
            item.convert_path = convert_path
            item.status = status
            item.err_msg = err_msg
        else:
            item = LeformatDatasetFormatCheckStatusDB(
                dataset_uuid=dataset_uuid,
                convert_path=convert_path,
                status=status,
                err_msg=err_msg,
            )
            session.add(item)
        session.commit()

    def _sync_check_tasks(self, device_model: str | None = None) -> None:
        """同步检查任务：为所有已完成转换但未检查的数据集创建检查任务"""
        with self.db.with_session() as session:
            if device_model is not None:
                items = (
                    session.query(LeFormatConvertDB)
                    .join(
                        DmvAnnotationDB,
                        LeFormatConvertDB.dataset_uuid == DmvAnnotationDB.dataset_uuid,
                    )
                    .filter(LeFormatConvertDB.convert_status == TaskStatus.COMPLETED)
                    .filter(
                        not_(
                            session.query(LeformatDatasetFormatCheckStatusDB)
                            .filter(
                                LeformatDatasetFormatCheckStatusDB.dataset_uuid
                                == LeFormatConvertDB.dataset_uuid
                            )
                            .exists()
                        )
                    )
                    .filter(DmvAnnotationDB.device_model == device_model)
                ).all()
            else:
                items = (
                    session.query(LeFormatConvertDB)
                    .filter(LeFormatConvertDB.convert_status == TaskStatus.COMPLETED)
                    .filter(
                        not_(
                            session.query(LeformatDatasetFormatCheckStatusDB)
                            .filter(
                                LeformatDatasetFormatCheckStatusDB.dataset_uuid
                                == LeFormatConvertDB.dataset_uuid
                            )
                            .exists()
                        )
                    )
                ).all()

        items = list(items)
        for item in items:
            with self.db.with_session() as session:
                self._upsert_leformat_dataset_check_status(
                    session,
                    dataset_uuid=item.dataset_uuid,
                    convert_path=item.convert_path,
                    status=TaskStatus.PENDING,
                )
        self.logger.info(f"Synced {len(items)} check tasks")

    def _gen_one_check_task(self, device_model: str | None = None) -> str | None:
        """生成一个待检查的任务"""
        with self.db.with_session() as session:
            if device_model is not None:
                item = (
                    session.query(LeformatDatasetFormatCheckStatusDB)
                    .join(
                        DmvAnnotationDB,
                        LeformatDatasetFormatCheckStatusDB.dataset_uuid == DmvAnnotationDB.dataset_uuid,
                    )
                    .filter(
                        and_(
                            LeformatDatasetFormatCheckStatusDB.status == TaskStatus.PENDING,
                            DmvAnnotationDB.device_model == device_model,
                        )
                    )
                    .first()
                )
            else:
                item = (
                    session.query(LeformatDatasetFormatCheckStatusDB)
                    .filter(LeformatDatasetFormatCheckStatusDB.status == TaskStatus.PENDING)
                    .first()
                )

            if not item:
                return None
            item.status = TaskStatus.PROCESSING
            session.commit()
            return item.dataset_uuid

    def check_datasets(self, device_model: str | None = None) -> None:
        """检查数据集的主方法 - 参考 sim_replay_datasets 的结构"""
        # 同步任务
        self._sync_check_tasks(device_model)

        # 循环处理任务
        while True:
            dataset_uuid = self._gen_one_check_task(device_model=device_model)
            if dataset_uuid is None:
                self.logger.info("No more datasets to check")
                return

            convert_path = self._get_convert_path(dataset_uuid)
            self.logger.info(f"Checking dataset {dataset_uuid} at {convert_path}")

            try:
                # 核心检查方法 - 对应 sim_replay 中的 _sim_replay_dataset
                self._check_dataset(dataset_uuid)
                with self.db.with_session() as session:
                    self._upsert_leformat_dataset_check_status(
                        session=session,
                        dataset_uuid=dataset_uuid,
                        convert_path=convert_path,
                        status=TaskStatus.COMPLETED,
                    )
                self.logger.info(f"Dataset {dataset_uuid} check completed successfully")

            except Exception as e:
                self.logger.error(f"Dataset {dataset_uuid} check failed: {str(e)}")
                with self.db.with_session() as session:
                    self._upsert_leformat_dataset_check_status(
                        session=session,
                        dataset_uuid=dataset_uuid,
                        convert_path=convert_path,
                        status=TaskStatus.FAILED,
                        err_msg=str(e),
                    )
