#!/usr/bin/env python3
"""
乐聚机器人数据集预转换验证器 v2
Pre-conversion validator for Leju Robot datasets

功能 / Features:
- 自动发现device_model_annotation.yaml并提取device_model和version
- 通过converter_factory_config.yaml自动查找对应的config文件
- 并行验证episode的完整性(metadata.json, MP4视频, H5数据, parameter JSONs)
- 区分配置问题(≥90%失败率)和数据问题(<90%失败率)
- 可选自动移动有问题的episode到error文件夹(仅数据问题)
- 生成详细的验证报告和配置问题建议

数据结构 / Data Structure:
/乐聚2/任务类别/具体任务/子任务/
├── device_model_annotation.yaml (设备模型配置)
└── UUID_folder/ (episode目录,如 000e9786-afb8-4f67-b749-ef87f7de0fde/)
    ├── metadata.json (episode元数据)
    ├── camera/
    │   ├── video/
    │   │   ├── head_cam_h.mp4 (头部相机)
    │   │   ├── wrist_cam_l.mp4 (左腕相机)
    │   │   └── wrist_cam_r.mp4 (右腕相机)
    │   └── depth/ (深度视频,可选)
    │       ├── head_cam_h_depth.mkv
    │       ├── wrist_cam_l_depth.mkv
    │       └── wrist_cam_r_depth.mkv
    ├── proprio_stats/
    │   └── proprio_stats.hdf5 (本体感觉数据)
    └── parameters/ (相机参数)
        ├── head_cam_h_extrinsic.json
        ├── head_cam_h_intrinsic.json
        ├── wrist_cam_l_extrinsic.json
        ├── wrist_cam_l_intrinsic.json
        ├── wrist_cam_r_extrinsic.json
        └── wrist_cam_r_intrinsic.json

使用方法 / Usage:
    python3 leju_preconversion_validator_v2.py \\
        --dataset-path /path/to/leju/dataset \\
        --workers 8 \\
        --move-errors

作者: GitHub Copilot
日期: 2025-01-20
"""

import argparse
import json
import shutil
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import h5py
import yaml


class LejuPreconversionValidator:
    """乐聚机器人数据集预转换验证器"""

    def __init__(
        self,
        dataset_path: str,
        max_episodes: int | None = None,
        workers: int = 4,
        move_errors: bool = False,
        config_error_threshold: float = 0.9,
    ):
        """
        初始化验证器

        Args:
            dataset_path: 数据集根目录路径
            max_episodes: 最大验证episode数量(None表示全部)
            workers: 并行worker数量
            move_errors: 是否移动有问题的episode到error文件夹
            config_error_threshold: 配置问题阈值(错误率>=此值认为是配置问题)
        """
        self.dataset_path = Path(dataset_path)
        self.max_episodes = max_episodes
        self.workers = workers
        self.move_errors = move_errors
        self.config_error_threshold = config_error_threshold

        # 验证结果统计
        self.total_episodes = 0
        self.passed_episodes = 0
        self.failed_episodes = 0
        self.validation_errors = []

        # 错误统计(用于区分配置问题和数据问题)
        self.error_counter = Counter()

        # Factory config路径(相对于脚本所在目录)
        script_dir = Path(__file__).parent
        self.factory_config_path = (
            script_dir.parent
            / "format_converters"
            / "tolerobot"
            / "configs"
            / "converter_factory_config.yaml"
        )

        print(f"📁 数据集路径: {self.dataset_path}")
        print(f"👷 并行workers: {self.workers}")
        print(f"🚚 移动错误episode: {'是' if self.move_errors else '否'}")
        print(f"⚙️ 配置问题阈值: {self.config_error_threshold * 100}%")
        print(f"🏭 Factory配置: {self.factory_config_path}")
        print("-" * 80)

    def _load_yaml(self, yaml_path: Path) -> dict[str, Any]:
        """加载YAML文件"""
        try:
            with open(yaml_path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"无法加载YAML文件 {yaml_path}: {e}")

    def _auto_find_config(self, device_model: str, device_version: str) -> Path | None:
        """
        通过factory config自动查找对应的converter config文件

        Args:
            device_model: 设备模型名称
            device_version: 设备版本

        Returns:
            config文件的绝对路径,如果未找到返回None
        """
        if not self.factory_config_path.exists():
            print(f"⚠️ Factory配置文件不存在: {self.factory_config_path}")
            return None

        try:
            factory_config = self._load_yaml(self.factory_config_path)

            # 查找匹配的converter配置
            if device_model not in factory_config:
                print(f"⚠️ Factory配置中未找到设备模型: {device_model}")
                return None

            model_configs = factory_config[device_model]
            
            # 新factory config结构是列表形式
            if isinstance(model_configs, list):
                # 在列表中查找匹配的version
                for config_item in model_configs:
                    if config_item.get("version") == device_version:
                        config_rel_path = config_item.get("converter_config_path")
                        if not config_rel_path:
                            print(f"⚠️ Factory配置中缺少converter_config_path字段")
                            return None
                        
                        # config路径相对于factory_config_path所在目录
                        config_path = self.factory_config_path.parent / config_rel_path
                        
                        if not config_path.exists():
                            print(f"⚠️ 配置文件不存在: {config_path}")
                            return None
                        
                        return config_path
                
                # 未找到匹配的版本
                available_versions = [item.get("version") for item in model_configs]
                print(f"⚠️ Factory配置中未找到版本: {device_version}")
                print(f"   可用版本: {available_versions}")
                return None
            
            # 旧factory config结构是字典形式(保留兼容性)
            else:
                if device_version not in model_configs:
                    print(f"⚠️ Factory配置中未找到版本: {device_version}")
                    available_versions = list(model_configs.keys())
                    print(f"   可用版本: {available_versions}")
                    return None

                config_rel_path = model_configs[device_version]
                # config路径相对于factory_config_path所在目录
                config_path = self.factory_config_path.parent / config_rel_path

                if not config_path.exists():
                    print(f"⚠️ 配置文件不存在: {config_path}")
                    return None

                return config_path

        except Exception as e:
            print(f"⚠️ 查找配置文件时出错: {e}")
            return None

    def discover_tasks(self) -> list[dict[str, Any]]:
        """
        发现所有任务(每个device_model_annotation.yaml所在目录为一个任务)

        由于乐聚数据集目录嵌套非常深,我们手动遍历目录层级查找device文件

        Returns:
            任务列表,每个任务包含device_path, config_path, task_name等信息
        """
        print("🔍 正在搜索device_model_annotation.yaml文件...")
        print(f"   (手动遍历目录层级,预计需要1-2分钟...)")

        device_file_paths = []
        
        # 遍历所有子目录查找device文件
        # 根目录 -> 任务类别 -> 具体任务 -> 子任务 -> device_model_annotation.yaml
        for category_dir in self.dataset_path.iterdir():
            if not category_dir.is_dir() or category_dir.name.startswith("."):
                continue
                
            print(f"   扫描类别: {category_dir.name}...")
            
            for task_dir in category_dir.iterdir():
                if not task_dir.is_dir() or task_dir.name.startswith("."):
                    continue
                    
                for subtask_dir in task_dir.iterdir():
                    if not subtask_dir.is_dir() or subtask_dir.name.startswith("."):
                        continue
                        
                    # 检查是否有device文件
                    device_file = subtask_dir / "device_model_annotation.yaml"
                    if device_file.exists():
                        device_file_paths.append(device_file)

        if not device_file_paths:
            print("❌ 未找到任何device_model_annotation.yaml文件")
            return []

        print(f"✅ 找到 {len(device_file_paths)} 个device文件")

        tasks = []
        for device_file in device_file_paths:
            try:
                # 加载device配置
                device_config = self._load_yaml(device_file)
                device_model = device_config.get("device_model", "")
                device_version = device_config.get("device_model_version", "")

                if not device_model or not device_version:
                    print(f"⚠️ Device文件缺少必要字段: {device_file}")
                    continue

                # 通过factory config查找对应的converter config
                config_path = self._auto_find_config(device_model, device_version)

                if config_path is None:
                    print(
                        f"⚠️ 跳过任务(未找到config): {device_file.parent.name} "
                        f"[{device_model}@{device_version}]"
                    )
                    continue

                # 任务路径为device文件所在目录
                task_path = device_file.parent
                task_name = task_path.relative_to(self.dataset_path)

                tasks.append(
                    {
                        "task_name": str(task_name),
                        "task_path": task_path,
                        "device_path": device_file,
                        "device_model": device_model,
                        "device_version": device_version,
                        "config_path": config_path,
                    }
                )

                print(
                    f"✅ 发现任务: {task_name} [{device_model}@{device_version}]"
                )

            except Exception as e:
                print(f"⚠️ 处理device文件时出错 {device_file}: {e}")
                continue

        print(f"\n📊 共发现 {len(tasks)} 个任务")
        return tasks

    def discover_episodes_in_task(self, task_info: dict[str, Any]) -> list[Path]:
        """
        发现任务中的所有episode

        Episode识别标准:
        - 目录名称为UUID格式(8-4-4-4-12)
        - 包含metadata.json文件

        Args:
            task_info: 任务信息字典

        Returns:
            episode路径列表
        """
        task_path = task_info["task_path"]
        episodes = []

        # 乐聚数据集中,episode文件夹在task_path下多级子目录中
        # 结构: task_path/子任务目录/UUID/
        # 使用手动遍历代替rglob(在大型目录中更快)
        def is_uuid_format(name: str) -> bool:
            """检查是否为UUID格式"""
            return (
                len(name) == 36
                and name.count("-") == 4
                and all(c in "0123456789abcdefABCDEF-" for c in name)
            )

        # 遍历task_path下的所有子目录(如single_FMCG_loading)
        try:
            for subdir in task_path.iterdir():
                if not subdir.is_dir() or subdir.name.startswith("."):
                    continue
                
                # 跳过非任务目录
                if subdir.name in ["@eaDir", "error"]:
                    continue

                # 在子目录中查找UUID格式的episode目录
                try:
                    for item in subdir.iterdir():
                        if not item.is_dir() or item.name.startswith("."):
                            continue

                        # 检查是否为UUID格式的目录
                        if is_uuid_format(item.name):
                            # 检查是否包含metadata.json
                            if (item / "metadata.json").exists():
                                episodes.append(item)
                except (PermissionError, OSError):
                    # 跳过无权限或无法访问的目录
                    continue
                    
        except Exception as e:
            print(f"   ⚠️ 搜索episode时出错: {e}")

        return episodes

    def validate_episode(
        self, episode_path: Path, config_data: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """
        验证单个episode的完整性

        Args:
            episode_path: episode目录路径
            config_data: converter配置数据

        Returns:
            (是否通过, 错误信息列表)
        """
        errors = []

        try:
            # 1. 验证metadata.json
            metadata_path = episode_path / "metadata.json"
            if not metadata_path.exists():
                errors.append(f"缺少文件: metadata.json")
            else:
                try:
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                        # 验证必要字段
                        required_fields = ["episode_id", "task_name"]
                        for field in required_fields:
                            if field not in metadata:
                                errors.append(
                                    f"metadata.json缺少字段: {field}"
                                )
                except json.JSONDecodeError as e:
                    errors.append(f"metadata.json格式错误: {e}")

            # 2. 验证MP4视频文件
            video_dir = episode_path / "camera" / "video"
            required_videos = ["head_cam_h.mp4", "wrist_cam_l.mp4", "wrist_cam_r.mp4"]

            for video_name in required_videos:
                video_path = video_dir / video_name
                if not video_path.exists():
                    errors.append(f"缺少视频: camera/video/{video_name}")
                elif video_path.stat().st_size == 0:
                    errors.append(f"视频文件为空: camera/video/{video_name}")

            # 3. 验证H5文件
            h5_path = episode_path / "proprio_stats" / "proprio_stats.hdf5"
            if not h5_path.exists():
                errors.append("缺少文件: proprio_stats/proprio_stats.hdf5")
            else:
                # 验证H5内部路径
                try:
                    with h5py.File(h5_path, "r") as hf:
                        # 根据config验证observation paths
                        observations = config_data.get("observations", {})

                        # 验证state paths
                        for obs_key, obs_config in observations.items():
                            if obs_key.startswith("observation.state"):
                                h5_path_str = obs_config.get("path", "")
                                if h5_path_str:
                                    if h5_path_str not in hf:
                                        errors.append(
                                            f"H5缺少路径: {h5_path_str}"
                                        )
                                    else:
                                        # 验证数据维度
                                        expected_shape = obs_config.get("shape", [])
                                        if expected_shape:
                                            actual_shape = hf[h5_path_str].shape
                                            if len(actual_shape) != 2:
                                                errors.append(
                                                    f"H5路径维度错误: {h5_path_str} "
                                                    f"(期望2D, 实际{len(actual_shape)}D)"
                                                )
                                            elif (
                                                expected_shape
                                                and actual_shape[1]
                                                != expected_shape[0]
                                            ):
                                                errors.append(
                                                    f"H5路径形状不匹配: {h5_path_str} "
                                                    f"(期望[*, {expected_shape[0]}], "
                                                    f"实际{actual_shape})"
                                                )

                        # 验证action paths
                        actions = config_data.get("actions", {})
                        for action_key, action_config in actions.items():
                            h5_path_str = action_config.get("path", "")
                            if h5_path_str:
                                if h5_path_str not in hf:
                                    errors.append(f"H5缺少路径: {h5_path_str}")
                                else:
                                    # 验证数据维度
                                    expected_shape = action_config.get("shape", [])
                                    if expected_shape:
                                        actual_shape = hf[h5_path_str].shape
                                        if len(actual_shape) != 2:
                                            errors.append(
                                                f"H5路径维度错误: {h5_path_str} "
                                                f"(期望2D, 实际{len(actual_shape)}D)"
                                            )
                                        elif (
                                            expected_shape
                                            and actual_shape[1] != expected_shape[0]
                                        ):
                                            errors.append(
                                                f"H5路径形状不匹配: {h5_path_str} "
                                                f"(期望[*, {expected_shape[0]}], "
                                                f"实际{actual_shape})"
                                            )

                except Exception as e:
                    errors.append(f"H5文件读取错误: {e}")

            # 4. 验证camera parameter JSON文件
            param_dir = episode_path / "parameters"
            required_params = [
                "head_cam_h_extrinsic.json",
                "head_cam_h_intrinsic.json",
                "wrist_cam_l_extrinsic.json",
                "wrist_cam_l_intrinsic.json",
                "wrist_cam_r_extrinsic.json",
                "wrist_cam_r_intrinsic.json",
            ]

            for param_name in required_params:
                param_path = param_dir / param_name
                if not param_path.exists():
                    errors.append(f"缺少参数文件: parameters/{param_name}")
                else:
                    try:
                        with open(param_path, "r", encoding="utf-8") as f:
                            json.load(f)  # 验证JSON格式
                    except json.JSONDecodeError as e:
                        errors.append(f"参数文件格式错误: parameters/{param_name}: {e}")

        except Exception as e:
            errors.append(f"验证过程出错: {e}")
            errors.append(f"Traceback: {traceback.format_exc()}")

        return len(errors) == 0, errors

    def _validate_single_episode(
        self, args: tuple[Path, Path, str]
    ) -> dict[str, Any]:
        """
        验证单个episode(用于多进程)

        Args:
            args: (episode_path, config_path, task_name)

        Returns:
            验证结果字典
        """
        episode_path, config_path, task_name = args

        try:
            # 加载config
            config_data = self._load_yaml(config_path)

            # 验证episode
            passed, errors = self.validate_episode(episode_path, config_data)

            return {
                "episode_path": episode_path,
                "task_name": task_name,
                "passed": passed,
                "errors": errors,
            }

        except Exception as e:
            return {
                "episode_path": episode_path,
                "task_name": task_name,
                "passed": False,
                "errors": [f"验证失败: {e}"],
            }

    def validate_all_episodes(self, tasks: list[dict[str, Any]]) -> None:
        """
        并行验证所有episode

        Args:
            tasks: 任务列表
        """
        print(f"\n🔍 正在收集所有episode...")

        # 收集所有episode
        all_episode_args = []
        for task_info in tasks:
            episodes = self.discover_episodes_in_task(task_info)
            print(f"  📂 {task_info['task_name']}: {len(episodes)} episodes")

            for episode_path in episodes:
                all_episode_args.append(
                    (
                        episode_path,
                        task_info["config_path"],
                        task_info["task_name"],
                    )
                )

        # 限制episode数量
        if self.max_episodes is not None:
            all_episode_args = all_episode_args[: self.max_episodes]

        self.total_episodes = len(all_episode_args)
        print(f"\n📊 共找到 {self.total_episodes} 个episodes")

        if self.total_episodes == 0:
            print("⚠️ 没有找到任何episode,退出验证")
            return

        print(f"\n🚀 开始并行验证 (workers={self.workers})...")
        start_time = time.time()

        # 多进程并行验证
        with ProcessPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self._validate_single_episode, args): args
                for args in all_episode_args
            }

            for idx, future in enumerate(as_completed(futures), 1):
                try:
                    result = future.result()

                    episode_path = result["episode_path"]
                    passed = result["passed"]
                    errors = result["errors"]
                    task_name = result["task_name"]

                    # 相对路径(用于显示)
                    rel_path = episode_path.relative_to(self.dataset_path)

                    if passed:
                        self.passed_episodes += 1
                        print(f"  [{idx}/{self.total_episodes}] ✅ {rel_path}")
                    else:
                        self.failed_episodes += 1
                        print(f"  [{idx}/{self.total_episodes}] ❌ {rel_path}")
                        for error in errors:
                            print(f"      • {error}")
                            # 统计错误类型
                            self.error_counter[error] += 1

                        # 记录验证错误
                        self.validation_errors.append(
                            {
                                "episode_path": episode_path,
                                "task_name": task_name,
                                "errors": errors,
                            }
                        )

                except Exception as e:
                    self.failed_episodes += 1
                    print(f"  [{idx}/{self.total_episodes}] ❌ 验证出错: {e}")

        elapsed_time = time.time() - start_time
        print(f"\n⏱️ 验证完成,耗时: {elapsed_time:.2f}秒")

    def analyze_config_problems(self) -> dict[str, Any]:
        """
        分析配置问题(错误率>=阈值的错误类型)

        Returns:
            配置问题分析结果
        """
        if self.total_episodes == 0:
            return {"config_problems": [], "data_problems": []}

        config_problems = []
        data_problems = []

        for error_msg, count in self.error_counter.most_common():
            error_rate = count / self.total_episodes

            if error_rate >= self.config_error_threshold:
                config_problems.append(
                    {
                        "error": error_msg,
                        "count": count,
                        "rate": error_rate,
                    }
                )
            else:
                data_problems.append(
                    {
                        "error": error_msg,
                        "count": count,
                        "rate": error_rate,
                    }
                )

        return {
            "config_problems": config_problems,
            "data_problems": data_problems,
        }

    def move_error_episodes(self) -> int:
        """
        移动有问题的episode到error文件夹

        只移动数据问题的episode,配置问题不移动

        Returns:
            移动的episode数量
        """
        if not self.move_errors or not self.validation_errors:
            return 0

        print(f"\n🚚 开始移动错误episodes...")

        # 分析配置问题
        analysis = self.analyze_config_problems()
        config_problem_errors = {
            item["error"] for item in analysis["config_problems"]
        }

        moved_count = 0

        for error_info in self.validation_errors:
            episode_path = error_info["episode_path"]
            errors = error_info["errors"]

            # 检查是否所有错误都是配置问题
            is_config_problem = all(
                error in config_problem_errors for error in errors
            )

            if is_config_problem:
                # 配置问题,不移动
                print(
                    f"  ⏭️ 跳过(配置问题): {episode_path.relative_to(self.dataset_path)}"
                )
                continue

            # 数据问题,移动到error文件夹
            try:
                # error文件夹与episode同级
                error_dir = episode_path.parent / "error"
                error_dir.mkdir(exist_ok=True)

                # 移动episode
                target_path = error_dir / episode_path.name
                if target_path.exists():
                    # 如果目标已存在,添加时间戳
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    target_path = error_dir / f"{episode_path.name}_{timestamp}"

                shutil.move(str(episode_path), str(target_path))
                moved_count += 1
                print(
                    f"  ✅ 已移动: {episode_path.relative_to(self.dataset_path)} -> {target_path.relative_to(self.dataset_path)}"
                )

            except Exception as e:
                print(
                    f"  ❌ 移动失败: {episode_path.relative_to(self.dataset_path)}: {e}"
                )

        return moved_count

    def generate_report(self) -> None:
        """生成验证报告"""
        print("\n" + "=" * 80)
        print("📊 验证报告")
        print("=" * 80)

        # 基本统计
        print(f"\n总计episodes: {self.total_episodes}")
        print(f"✅ 通过: {self.passed_episodes}")
        print(f"❌ 失败: {self.failed_episodes}")

        if self.total_episodes > 0:
            pass_rate = self.passed_episodes / self.total_episodes * 100
            print(f"📈 通过率: {pass_rate:.2f}%")

        # 错误统计
        if self.error_counter:
            print(f"\n🔍 错误统计 (Top 20):")
            for error_msg, count in self.error_counter.most_common(20):
                error_rate = count / self.total_episodes * 100
                print(f"  [{count:4d}次, {error_rate:5.2f}%] {error_msg}")

        # 配置问题分析
        analysis = self.analyze_config_problems()
        config_problems = analysis["config_problems"]

        if config_problems:
            print(f"\n⚙️ 配置问题 (错误率>={self.config_error_threshold * 100}%):")
            for item in config_problems:
                print(
                    f"  [{item['count']:4d}次, {item['rate'] * 100:5.2f}%] {item['error']}"
                )

            # 生成配置问题建议文件
            report_path = self.dataset_path / "validation_config_issues.txt"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("=" * 80 + "\n")
                f.write("乐聚数据集配置问题报告\n")
                f.write("=" * 80 + "\n\n")

                f.write("⚠️ 以下错误在大量episode中出现,可能是配置文件问题:\n\n")

                for item in config_problems:
                    f.write(
                        f"[{item['count']:4d}次, {item['rate'] * 100:5.2f}%] {item['error']}\n"
                    )

                f.write("\n" + "=" * 80 + "\n")
                f.write("建议:\n")
                f.write("=" * 80 + "\n\n")

                f.write(
                    "1. 检查device_model_annotation.yaml中的device_model和device_model_version\n"
                )
                f.write("2. 确认converter_factory_config.yaml中存在对应的映射\n")
                f.write("3. 检查converter config文件中的路径配置是否正确\n")
                f.write("4. 验证H5文件路径、视频文件名、参数文件名是否与config匹配\n")
                f.write("\n")
                f.write(
                    "如果这些错误确实是配置问题,请修改相应的YAML配置文件,而不是移动episode。\n"
                )

            print(f"\n📝 配置问题报告已写入: {report_path}")

        print("\n" + "=" * 80)

    def run(self) -> None:
        """运行完整的验证流程"""
        print("🚀 乐聚机器人数据集预转换验证器 v2")
        print("=" * 80)

        # 1. 发现所有任务
        tasks = self.discover_tasks()

        if not tasks:
            print("❌ 未发现任何任务,退出")
            sys.exit(1)

        # 2. 并行验证所有episodes
        self.validate_all_episodes(tasks)

        # 3. 移动错误episodes(如果启用)
        if self.move_errors:
            moved_count = self.move_error_episodes()
            print(f"\n✅ 共移动 {moved_count} 个错误episodes")

        # 4. 生成报告
        self.generate_report()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="乐聚机器人数据集预转换验证器 v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本验证
  python3 leju_preconversion_validator_v2.py --dataset-path /path/to/leju

  # 使用8个worker并行验证
  python3 leju_preconversion_validator_v2.py --dataset-path /path/to/leju --workers 8

  # 验证并自动移动错误episodes
  python3 leju_preconversion_validator_v2.py --dataset-path /path/to/leju --workers 8 --move-errors

  # 只验证前10个episodes(测试用)
  python3 leju_preconversion_validator_v2.py --dataset-path /path/to/leju --max-episodes 10
        """,
    )

    parser.add_argument(
        "--dataset-path",
        type=str,
        required=True,
        help="数据集根目录路径",
    )

    parser.add_argument(
        "--max-episodes",
        type=int,
        default=None,
        help="最大验证episode数量(默认:全部)",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="并行worker数量(默认:4)",
    )

    parser.add_argument(
        "--move-errors",
        action="store_true",
        help="自动移动有问题的episode到error文件夹",
    )

    parser.add_argument(
        "--config-error-threshold",
        type=float,
        default=0.9,
        help="配置问题阈值,错误率>=此值认为是配置问题(默认:0.9)",
    )

    args = parser.parse_args()

    # 创建验证器并运行
    validator = LejuPreconversionValidator(
        dataset_path=args.dataset_path,
        max_episodes=args.max_episodes,
        workers=args.workers,
        move_errors=args.move_errors,
        config_error_threshold=args.config_error_threshold,
    )

    validator.run()


if __name__ == "__main__":
    main()
