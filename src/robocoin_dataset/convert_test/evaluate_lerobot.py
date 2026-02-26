import os
import json
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
import cv2

class LerobotDatasetEvaluator:
    """
    LeRobot 数据集转换质量评估工具
    """
    def __init__(self, dataset_path: str):
        self.dataset_path = Path(dataset_path)
        self.meta_path = self.dataset_path / "meta"
        self.data_path = self.dataset_path / "data"
        self.videos_path = self.dataset_path / "videos"
        self.report = []
        self.stats = {
            "passed": 0,
            "failed": 0,
            "warnings": 0
        }

    def log(self, section: str, message: str, level: str = "INFO"):
        emoji = {"INFO": "✅", "WARNING": "⚠️", "ERROR": "❌"}[level]
        if level == "ERROR": self.stats["failed"] += 1
        elif level == "WARNING": self.stats["warnings"] += 1
        else: self.stats["passed"] += 1
        self.report.append(f"| {section} | {emoji} {level} | {message} |")

    def evaluate(self):
        self.report.append("# LeRobot 数据集转换质量评估报告")
        self.report.append(f"**评估时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.report.append(f"**数据集路径**: `{self.dataset_path}`")
        self.report.append("\n| 检查项 | 状态 | 详细说明 |")
        self.report.append("| :--- | :--- | :--- |")

        # 1. 基础结构检查
        self._check_structure()
        
        # 2. 元数据与字段检查
        info = self._check_metadata()
        
        if info:
            # 3. 图像/视频完整性检查
            self._check_videos(info)
            
            # 4. 数据一致性检查 (Parquet vs Video)
            self._check_data_consistency(info)

        self._output_report()

    def _check_structure(self):
        section = "目录结构"
        required_dirs = ["meta", "data", "videos"]
        missing = [d for d in required_dirs if not (self.dataset_path / d).exists()]
        if missing:
            self.log(section, f"缺少关键目录: {', '.join(missing)}", "ERROR")
        else:
            self.log(section, "目录结构完整", "INFO")

    def _check_metadata(self) -> dict:
        section = "元数据与字段"
        info_file = self.meta_path / "info.json"
        if not info_file.exists():
            self.log(section, "缺少 meta/info.json", "ERROR")
            return None
        
        try:
            with open(info_file, 'r') as f:
                info = json.load(f)
            
            features = info.get("features", {})
            
            # 检查关键字段命名
            expected_grippers = ["left_gripper_open_scale", "right_gripper_open_scale"]
            state_names = features.get("observation.state", {}).get("names", [])
            missing_grippers = [g for f in expected_grippers if not any(f in name for name in state_names)]
            
            if missing_grippers:
                self.log(section, f"字段命名不规范，缺少或未更名: {', '.join(missing_grippers)}", "WARNING")
            else:
                self.log(section, "夹爪字段命名规范 (scale)", "INFO")

            # 检查相机命名
            image_keys = [k for k in features.keys() if k.startswith("observation.images.")]
            head_cams = [k for k in image_keys if "head" in k]
            if not head_cams:
                self.log(section, "未发现 head 相机字段 (预期 cam_*_head_rgb)", "WARNING")
            else:
                self.log(section, f"相机命名规范: {', '.join(head_cams)}", "INFO")
                
            return info
        except Exception as e:
            self.log(section, f"解析元数据失败: {str(e)}", "ERROR")
            return None

    def _check_videos(self, info: dict):
        section = "视频完整性"
        features = info.get("features", {})
        # Get full keys for video features
        image_keys = [k for k in features.keys() if k.startswith("observation.images.")]
        
        for cam_key in image_keys:
            # Check for directory using full key name (LeRobot standard) or short name
            cam_dir_full = self.videos_path / "chunk-000" / cam_key
            cam_dir_short = self.videos_path / "chunk-000" / cam_key.replace("observation.images.", "")
            
            if cam_dir_full.exists():
                cam_dir = cam_dir_full
                display_name = cam_key
            elif cam_dir_short.exists():
                cam_dir = cam_dir_short
                display_name = cam_key.replace("observation.images.", "")
            else:
                self.log(section, f"相机 {cam_key} 的视频目录不存在 (检查了 {cam_dir_full.name} 和 {cam_dir_short.name})", "ERROR")
                continue
            
            videos = list(cam_dir.glob("*.mp4"))
            if not videos:
                self.log(section, f"相机 {display_name} 下没有视频文件", "ERROR")
            else:
                # 随机抽查一个视频是否可读
                cap = cv2.VideoCapture(str(videos[0]))
                if not cap.isOpened():
                    self.log(section, f"视频文件损坏或无法读取: {videos[0].name}", "ERROR")
                else:
                    self.log(section, f"相机 {display_name} 视频可正常读取 (共 {len(videos)} 个)", "INFO")
                cap.release()

    def _check_data_consistency(self, info: dict):
        section = "数据一致性"
        total_episodes = info.get("total_episodes", 0)
        if total_episodes == 0: return

        # 检查第一个 episode 的 Parquet 和 Video 帧数
        try:
            parquet_file = self.data_path / "chunk-000" / "episode_000000.parquet"
            if not parquet_file.exists():
                self.log(section, "缺少数据文件 episode_000000.parquet", "ERROR")
                return

            df = pd.read_parquet(parquet_file)
            parquet_frames = len(df)

            features = info.get("features", {})
            image_keys = [k for k in features.keys() if k.startswith("observation.images.")]
            
            mismatch = False
            for cam_key in image_keys:
                # Determine correct video directory
                cam_dir_full = self.videos_path / "chunk-000" / cam_key
                cam_dir_short = self.videos_path / "chunk-000" / cam_key.replace("observation.images.", "")
                
                if cam_dir_full.exists():
                    video_file = cam_dir_full / "episode_000000.mp4"
                elif cam_dir_short.exists():
                    video_file = cam_dir_short / "episode_000000.mp4"
                else:
                    continue # Already reported in _check_videos

                if video_file.exists():
                    cap = cv2.VideoCapture(str(video_file))
                    video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    cap.release()
                    
                    if video_frames != parquet_frames:
                        self.log(section, f"帧数不一致 [{cam_key}]: Parquet({parquet_frames}) vs Video({video_frames})", "WARNING")
                        mismatch = True
            
            if not mismatch:
                self.log(section, f"帧数对齐一致 (共 {parquet_frames} 帧)", "INFO")

        except Exception as e:
            self.log(section, f"一致性检查失败: {str(e)}", "ERROR")

    def _output_report(self):
        report_file = self.dataset_path / "EVALUATION_REPORT.md"
        
        summary = f"\n## 评估摘要\n- **通过项**: {self.stats['passed']}\n- **警告项**: {self.stats['warnings']}\n- **失败项**: {self.stats['failed']}\n"
        if self.stats["failed"] == 0:
            summary += "\n### 结论: 🟢 数据集符合基础要求，可用于训练。"
        else:
            summary += "\n### 结论: 🔴 数据集存在关键错误，需修复后使用。"
            
        with open(report_file, 'w') as f:
            f.write("\n".join(self.report))
            f.write(summary)
        
        print(f"评估完成！报告已生成: {report_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_path", type=str, help="LeRobot 数据集根目录")
    args = parser.parse_args()
    
    evaluator = LerobotDatasetEvaluator(args.dataset_path)
    evaluator.evaluate()
