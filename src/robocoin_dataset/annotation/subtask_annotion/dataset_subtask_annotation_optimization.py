import json
import logging
import re
import traceback
from pathlib import Path

import requests
import tqdm
from sqlalchemy import and_, or_

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
    TaskStatus,
    VideoOptStAnnotationDB,
    VideoStAnnotationDB,
)


def _detect_language(text: str) -> str:
    """
    检测文本语言
    Returns: 'zh' (中文), 'en' (英文), or 'unknown'
    """
    # 中文检测：包含中文字符
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    # 英文检测：主要包含英文字母
    if re.search(r"[a-zA-Z]", text) and not re.search(r"[\u4e00-\u9fff]", text):
        return "en"
    return "unknown"


def optimize_annotation(annotation_set: set[str], ds_api_key: str) -> dict[str, str]:
    # 分类指令
    zh_annotations = list()
    annotation_list = list(annotation_set)
    result = dict()

    for annotation in annotation_list:
        lang = _detect_language(annotation)
        if lang == "zh":
            zh_annotations.append(annotation)
        else:
            result[annotation] = annotation

    # 准备提示词
    prompt_parts = []

    if zh_annotations:
        zh_text = "\n".join(f"{idx + 1}. {cmd}" for idx, cmd in enumerate(zh_annotations))
        prompt_parts.append(f"""
            请将以下中文动作指令逐条翻译为自然的英文语句，保持语义准确：
            {zh_text}
        """)

    if not prompt_parts:
        return result

    prompt = "\n".join(prompt_parts)
    prompt += "\n\n请按顺序给出处理结果，不要编号，每行一个结果："

    # DeepSeek API配置
    api_url = "https://api.deepseek.com/v1/chat/completions"

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ds_api_key}"}

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "top_p": 0.8,
        "max_tokens": 1024,
        "stream": False,
    }

    try:
        print("Tring to call DeepSeek API to translate Chinese annotations to English")
        response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=100)

        if response.status_code == 200:
            response_data = response.json()
            processed_text = response_data["choices"][0]["message"]["content"].strip()

            # 处理结果
            result_lines = [line.strip() for line in processed_text.split("\n") if line.strip()]

            # 清理可能的编号
            cleaned_results = []
            for line in result_lines:
                if ". " in line and line.split(". ")[0].isdigit():
                    cleaned_results.append(line.split(". ", 1)[-1])
                else:
                    cleaned_results.append(line)

            # 验证结果数量
            expected_count = len(zh_annotations)
            if len(cleaned_results) != expected_count:
                raise ValueError(
                    f"处理结果数量({len(cleaned_results)})与预期数量({expected_count})不匹配"
                )
            result.update(
                {
                    zh_annotation: cleaned_annotation
                    for zh_annotation, cleaned_annotation in zip(zh_annotations, cleaned_results)
                }
            )

            return result

        raise Exception(f"API请求失败: {response.status_code} - {response.text}")

    except Exception as e:
        raise Exception(f"处理指令时出错: {str(e)}")


class DatasetSubtaskAnnotationOptimization:
    def __init__(
        self,
        db_file_path: str | Path,
        ds_api_key: str,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db_file_path: Path = Path(db_file_path).expanduser().absolute()
        self.db = DatasetDatabase(self.db_file_path)
        self.logger = logger or logging.getLogger(__name__)
        self.ds_api_key = ds_api_key

    def sync_dataset_subtask_annotation_optimization_status(self) -> None:
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                and_(
                    # 必要前提：convert必须成功
                    DatasetDB.video_ori_subtask_annotation_status == TaskStatus.COMPLETED,
                    # 两个触发分支
                    or_(
                        # 分支1: 正在排队
                        DatasetDB.video_opt_subtask_annotation_status == TaskStatus.PENDING,
                        # 分支2: 已完成但版本过期
                        and_(
                            DatasetDB.video_opt_subtask_annotation_status == TaskStatus.COMPLETED,
                            DatasetDB.video_opt_subtask_annotation_version_ps
                            < DatasetDB.video_ori_subtask_annotation_version,
                        ),
                    ),
                )
            )

            print(query.count())

            for item in query.all():
                item.video_opt_subtask_annotation_status = TaskStatus.PENDING
                item.video_opt_subtask_annotation_version_ps = (
                    item.video_ori_subtask_annotation_version
                )
            session.commit()

    def gen_one_dataset_subtask_annotation_optimization_task(self) -> str:
        with self.db.with_session() as session:
            query = session.query(DatasetDB).filter(
                and_(
                    DatasetDB.video_ori_subtask_annotation_status == TaskStatus.COMPLETED,
                    DatasetDB.video_opt_subtask_annotation_status == TaskStatus.PENDING,
                )
            )
            item = query.first()
            if not item:
                return None

            item.video_opt_subtask_annotation_version = (
                item.video_opt_subtask_annotation_version + 1
            )
            item.video_opt_subtask_annotation_status = TaskStatus.PROCESSING
            return item.dataset_uuid

    def _optimize_subtask_annotation(self, dataset_uuid: str) -> None:
        with self.db.with_session() as session:
            items = (
                session.query(VideoStAnnotationDB)
                .filter(VideoStAnnotationDB.dataset_uuid == dataset_uuid)
                .all()
            )
            if not items:
                return
            original_subtask_annotations = set([item.annotation for item in items])

        try:
            optimized_annotation_dict = optimize_annotation(
                annotation_set=original_subtask_annotations, ds_api_key=self.ds_api_key
            )
            with self.db.with_session() as session:
                session.query(VideoOptStAnnotationDB).filter(
                    VideoOptStAnnotationDB.dataset_uuid == dataset_uuid
                ).delete()

                ori_items = (
                    session.query(VideoStAnnotationDB)
                    .filter(VideoStAnnotationDB.dataset_uuid == dataset_uuid)
                    .all()
                )
                for ori_item in ori_items:
                    new_annotation = optimized_annotation_dict.get(ori_item.annotation)
                    if new_annotation:
                        session.add(
                            VideoOptStAnnotationDB(
                                dataset_uuid=dataset_uuid,
                                episode_idx=ori_item.episode_idx,
                                start_frame_idx=ori_item.start_frame_idx,
                                end_frame_idx=ori_item.end_frame_idx,
                                annotation=optimized_annotation_dict[ori_item.annotation],
                            )
                        )
                session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).update(
                    {
                        DatasetDB.video_opt_subtask_annotation_status: TaskStatus.COMPLETED,
                    }
                )
                session.commit()

        except Exception as e:
            self.logger.error(f"Failed to optimize annotation for {dataset_uuid}: {e}")
            with self.db.with_session() as session:
                session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).update(
                    {
                        DatasetDB.video_opt_subtask_annotation_status: TaskStatus.FAILED,
                        DatasetDB.video_opt_subtask_annotation_err_msg: traceback.format_exc(),
                    }
                )
                session.commit()

    def optimize_subtask_annotation(self) -> None:
        self.sync_dataset_subtask_annotation_optimization_status()
        with self.db.with_session() as session:
            task_num = (
                session.query(DatasetDB)
                .filter(
                    and_(
                        DatasetDB.video_ori_subtask_annotation_status == TaskStatus.COMPLETED,
                        DatasetDB.video_opt_subtask_annotation_status == TaskStatus.PENDING,
                    )
                )
                .count()
            )
        pbar = tqdm.tqdm(total=task_num, desc="Annotate subtask for datasets", unit="dataset")
        while True:
            dataset_uuid = self.gen_one_dataset_subtask_annotation_optimization_task()
            if dataset_uuid is None:
                break
            self._optimize_subtask_annotation(dataset_uuid=dataset_uuid)
            pbar.update(1)

        pbar.close()
