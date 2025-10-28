from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from robocoin_dataset.database.models import (
    TaskStatus,
)


def upsert_leformat_convert(
    session: Session,
    ds_uuid: str,
    convert_status: TaskStatus,
    err_message: str | None = None,
    leformat_path: str | None = None,
    device_model: str | None = None,
    device_model_version: str | None = None,
    total_episodes: int | None = None,
    converted_episodes: int | None = None,
    skipped_episodes: int | None = None,
    is_test: bool = False,
) -> None:
    """
    Upsert LeFormatConvertDB 或 LeFormatConvertTestDB 记录。

    :param session: 已打开的 SQLAlchemy Session（由调用方管理生命周期）
    :param ds_uuid: 数据集 UUID
    :param convert_status: 转换状态
    :param err_message: 可选，错误消息或状态更新信息
    :param leformat_path: 可选，转换输出路径
    :param device_model: 可选，设备型号
    :param device_model_version: 可选，设备型号版本
    :param total_episodes: 可选，总episode数
    :param converted_episodes: 可选，成功转换的episode数
    :param skipped_episodes: 可选，跳过的episode数
    :param is_test: 是否为测试模式（True=使用 LeFormatConvertTestDB，False=使用 LeFormatConvertDB）
    """

    # 重试机制：处理并发INSERT导致的IntegrityError
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 查询是否存在
            item = (
                session.query(leformat_convert_db)
                .filter(leformat_convert_db.dataset_uuid == ds_uuid)
                .first()
            )

            if item is None:
                # 创建新记录
                item = leformat_convert_db(
                    dataset_uuid=ds_uuid,
                    convert_status=convert_status,
                    convert_path=leformat_path,
                    version_uuid="v0",  # 🆕 明确提供version_uuid
                    err_message=err_message,
                    device_model=device_model,
                    device_model_version=device_model_version,
                    total_episodes=total_episodes,
                    converted_episodes=converted_episodes,
                    skipped_episodes=skipped_episodes,
                    updated_at=datetime.now(),
                )
            else:
                # 更新现有记录
                item.convert_status = convert_status
                item.updated_at = datetime.now()
                # convert_version_uuid = (convert_version_uuid,)
                if err_message is not None:
                    item.err_message = err_message
                if leformat_path is not None:
                    item.convert_path = leformat_path
                # 🆕 更新 device_model 和 device_model_version（如果提供）
                if device_model is not None:
                    item.device_model = device_model
                if device_model_version is not None:
                    item.device_model_version = device_model_version
                # 🆕 更新统计信息（如果提供）
                if total_episodes is not None:
                    item.total_episodes = total_episodes
                if converted_episodes is not None:
                    item.converted_episodes = converted_episodes
                if skipped_episodes is not None:
                    item.skipped_episodes = skipped_episodes

            session.add(item)
            session.commit()
            return  # 成功，退出

        except IntegrityError as e:
            # 并发INSERT冲突，回滚并重试
            session.rollback()
            if attempt < max_retries - 1:
                # 重新查询并更新（其他进程已经插入了）
                continue
            # 最后一次尝试仍然失败
            raise RuntimeError(
                f"Failed to upsert LeFormatConvertDB record for dataset {ds_uuid} "
                f"after {max_retries} attempts: {e}"
            ) from e

        except Exception as e:
            session.rollback()
            raise RuntimeError(
                f"Failed to upsert LeFormatConvertDB record for dataset {ds_uuid}: {e}"
            ) from e
