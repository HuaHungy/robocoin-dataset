import argparse
import json
import re
import shutil
from pathlib import Path

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    StAnnotationVideoDB,
    VideoMatchDB,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--json-dir", type=Path, required=True)
    parser.add_argument("--matched-json-dir", type=Path, required=True)
    parser.add_argument("--unmatched-json-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    matched_json_dir = Path(args.matched_json_dir)
    unmatched_json_dir = Path(args.unmatched_json_dir)
    if matched_json_dir.exists():
        shutil.rmtree(matched_json_dir)
        matched_json_dir.mkdir(parents=True)

    if unmatched_json_dir.exists():
        shutil.rmtree(unmatched_json_dir)
        unmatched_json_dir.mkdir(parents=True)

    db = DatasetDatabase(args.db)

    # 正则用于 observation.images.xxx
    pattern = re.compile(r"^observation\.images\.(.+)$")

    results = []
    for json_path in sorted(Path(args.json_dir).glob("*.json")):
        try:
            video_url = None
            anno_id = None
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    print(f"⚠️ 跳过无效 JSON（非列表）: {json_path.name}")
                    continue

                if len(data) == 0:
                    print(f"ℹ️ 空 JSON 文件: {json_path.name}")
                    continue

                for idx, ep in enumerate(data):
                    if not isinstance(ep, dict):
                        print(f"⚠️ 跳过非字典 episode #{idx} in {json_path.name}")
                        continue

                    # 1. 提取 video_url
                    if "video" in ep:
                        val = ep["video"]
                        if isinstance(val, str) and val.startswith("http"):
                            video_url = val

                    if video_url is None:
                        for key in ep:
                            if pattern.match(key):
                                val = ep[key]
                                if isinstance(val, str) and val.startswith("http"):
                                    video_url = val
                                    break  # 取第一个匹配的 observation.images.xxx

                    # 如果连 video_url 都没有，跳过该 episode（或仍记录？这里选择跳过）
                    if video_url is None:
                        # 可选：仍记录空 URL 行，但通常无意义
                        continue
                    else:
                        anno_id = ep["id"]
                        break
            if video_url is None or anno_id is None:
                print(f"⚠️ 跳过无效 JSON（无 video_url 或 anno_id）: {json_path.name}")
                continue
            frame_num = None
            with db.with_session() as session:
                item = (
                    session.query(StAnnotationVideoDB)
                    .join(VideoMatchDB, VideoMatchDB.url_video_id == StAnnotationVideoDB.id)
                    .filter(StAnnotationVideoDB.video_url == video_url)
                    .first()  # 只需一条，因为 video_url 唯一
                )
                if item is None:
                    print(f"⚠️ 跳过无效 JSON（无匹配的 video_url）: {json_path.name}")
                    shutil.move(json_path, unmatched_json_dir / json_path.name)
                    continue
                frame_num = item.frame_num

            results.append(
                {
                    "json_file": json_path.name,
                    "frame_num": frame_num,
                    "anno_id": anno_id,
                }
            )
            shutil.move(json_path, matched_json_dir / json_path.name)

        except Exception as e:
            print(f"❌ 解析失败 {json_path.name}: {e}")
            continue

    with open(args.output_dir / "annotation_json_framenum.csv", "w", encoding="utf-8") as f:
        f.write("json_file,anno_id,actual_frame_num,platform_frame_num\n")
        f.write(
            "\n".join(
                [
                    ",".join(
                        map(
                            str,
                            [
                                result["json_file"],
                                result["anno_id"],
                                result["frame_num"],
                            ],
                        )
                    )
                    for result in results
                ]
            )
        )

"""
python scripts/annotation/subtask_annotation_json_file_preprocessing.py --db ./db/datasets_new.db --json-dir ./datas/annotation/subtask_annotation/all_jsons/ --output-dir ./datas --matched-json-dir datas/annotation/subtask_annotation/all_matched_jsons --unmatched-json-dir ./datas/annotation/subtask_annotation/all_unmatched_json/
"""
