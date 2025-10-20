#!/usr/bin/env python3
"""
银河通用(Yinhe/Galaxea) 数据集预转换验证工具 (高性能版)

核心优化:
1. 以 device_model_annotation.yaml 为基准定位数据集
2. 使用 subprocess find 命令快速定位 data.json (episode特征文件)
3. 多进程并行验证 (ProcessPoolExecutor)
4. 只读取必要信息，不完整加载大文件
5. 从 converter config 读取required fields，而非硬编码

数据集结构:
银河通用/
├── fold_clothe/                # Task 1
│   ├── device_model_annotation.yaml  # 版本标识文件
│   ├── local_dataset_info.yaml
│   └── robot_id/YYYYMMDD_recordN/
│       ├── data.json           # Episode特征文件 ⭐
│       ├── camera_*.mp4
│       └── report.txt
"""

import argparse
import json
import subprocess
import sys
import yaml
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """验证结果"""
    episode_path: str
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    task_name: str
    robot_id: str
    episode_name: str


class YinheValidatorV2:
    """银河数据集验证器 (高性能版)"""
    
    def __init__(self, data_root: str, config_path: str = None, config_dir: str = None, verbose: bool = False, max_workers: int = 4):
        self.data_root = Path(data_root)
        self.config_path = Path(config_path) if config_path else None
        self.config_dir = Path(config_dir) if config_dir else Path(__file__).parent.parent / "format_converters" / "tolerobot" / "configs"
        self.verbose = verbose
        self.max_workers = max_workers
        
        # 从config加载验证规则（如果已指定config）
        self.required_topics = []
        self.required_fields = []
        
        if self.config_path and self.config_path.exists():
            self._load_config_from_path(self.config_path)
        # 否则等待 discover_datasets() 后自动加载
    
    def _load_config_from_path(self, config_path: Path):
        """从指定路径加载config"""
        try:
            with open(config_path, encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 从 camera_paths 提取视频文件名
            camera_paths = config.get('camera_paths', {})
            self.required_videos = [Path(p).name for p in camera_paths.values() if p]
            
            # 从 h5_paths 提取 JSON 字段名
            h5_paths = config.get('h5_paths', {})
            self.required_json_fields = []
            for section in ['state', 'action']:
                section_paths = h5_paths.get(section, {})
                for key in section_paths.keys():
                    # 移除h5前缀，转换为JSON字段名
                    if isinstance(section_paths[key], str):
                        field_name = section_paths[key].split('/')[-1] if '/' in section_paths[key] else key
                        self.required_json_fields.append(field_name)
            
            if self.verbose:
                print(f"✅ 从config加载: {len(self.required_videos)} 个视频, {len(self.required_json_fields)} 个字段")
                print(f"   配置文件: {config_path.name}")
        
        except Exception as e:
            print(f"⚠️  加载config失败: {e}")
            self._use_default_config()
    
    def _use_default_config(self):
        """使用默认配置"""
        self.required_videos = [
            "camera_front_head_rgb.mp4",
            "camera_left_wrist.mp4",
            "camera_right_wrist.mp4"
        ]
        self.required_json_fields = [
            "state_left_arm_joint_position",
            "state_right_arm_joint_position",
            "state_left_arm_gripper_width",
            "state_right_arm_gripper_width",
            "cmd_left_joint_state",
            "cmd_right_joint_state"
        ]
        if self.verbose:
            print("  使用默认配置")
    
    def _load_factory_config(self) -> dict:
        """加载converter_factory_config.yaml文件"""
        factory_config_path = self.config_dir / "converter_factory_config.yaml"
        if not factory_config_path.exists():
            if self.verbose:
                print(f"⚠️  未找到factory配置: {factory_config_path}")
            return {}
        
        try:
            with open(factory_config_path, encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            if self.verbose:
                print(f"⚠️  加载factory配置失败: {e}")
            return {}
    
    def _auto_find_config(self, device_model: str, version: str) -> Optional[Path]:
        """根据device_model和version从factory配置自动查找config文件"""
        # 首先尝试从factory配置查找
        factory_config = self._load_factory_config()
        
        # 查找对应的device_model配置
        if device_model in factory_config:
            versions = factory_config[device_model]
            if isinstance(versions, list):
                # 查找匹配的version
                for ver_config in versions:
                    if ver_config.get('version') == version:
                        config_name = ver_config.get('converter_config_path')
                        if config_name:
                            config_file = self.config_dir / config_name
                            if config_file.exists():
                                if self.verbose:
                                    print(f"  从factory配置匹配: {config_name}")
                                return config_file
                
                # 如果没有精确匹配，尝试使用default_version
                for ver_config in versions:
                    if ver_config.get('version') == 'default_version':
                        config_name = ver_config.get('converter_config_path')
                        if config_name:
                            config_file = self.config_dir / config_name
                            if config_file.exists():
                                if self.verbose:
                                    print(f"  使用default_version配置: {config_name}")
                                return config_file
        
        # Factory配置查找失败，回退到文件名模式匹配
        if self.verbose:
            print("  Factory配置未找到，尝试文件名匹配...")
        
        patterns = [
            f"converter_config_{device_model}_{version}.yaml",
            f"converter_config_{device_model}.yaml",
            "converter_config_yinhe.yaml"
        ]
        
        for pattern in patterns:
            config_file = self.config_dir / pattern
            if config_file.exists():
                return config_file
        
        return None
    
    def discover_datasets(self) -> list[tuple[Path, str]]:
        """
        发现所有数据集（通过 device_model_annotation.yaml）
        
        对于银河数据集：device_model_annotation.yaml 在任务目录级别
        银河通用/fold_clothe/device_model_annotation.yaml
        
        Returns:
            [(yaml_path, version), ...]
        """
        print("🔍 查找 device_model_annotation.yaml 文件...")
        
        # 银河数据集：只需遍历一级子目录（任务目录）
        yaml_files = []
        try:
            for task_dir in self.data_root.iterdir():
                if not task_dir.is_dir():
                    continue
                
                yaml_path = task_dir / "device_model_annotation.yaml"
                if yaml_path.exists():
                    yaml_files.append(yaml_path)
        
        except Exception as e:
            print(f"⚠️  遍历目录失败: {e}")
            return []
        
        # 读取版本信息
        datasets = []
        for yaml_path in yaml_files:
            try:
                with open(yaml_path, encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    version = data.get('device_model_version', 'default_version')
                    device_model = data.get('device_model', 'yinhe')
                    datasets.append((yaml_path, version, device_model))
            except Exception as e:
                print(f"⚠️  读取 {yaml_path} 失败: {e}")
                continue
        
        # 如果未指定config，尝试自动加载第一个数据集的config
        if not self.config_path and datasets:
            first_yaml, first_version, first_device = datasets[0]
            auto_config = self._auto_find_config(first_device, first_version)
            if auto_config:
                print(f"✅ 自动匹配config: {auto_config.name}")
                self._load_config_from_path(auto_config)
            else:
                print("⚠️  未找到匹配的config文件，使用默认配置")
                print(f"   尝试查找: converter_config_{first_device}_{first_version}.yaml")
                self._use_default_config()
        elif not self.config_path:
            print("⚠️  未指定config文件且未找到数据集，使用默认配置")
            self._use_default_config()
        
        print(f"✅ 找到 {len(datasets)} 个任务目录")
        # 转换回旧格式（为了保持兼容性）
        return [(yaml, ver) for yaml, ver, _ in datasets]
    
    def find_episodes_fast(self, dataset_base: Path, max_episodes: Optional[int] = None) -> list[Path]:
        """
        快速查找episodes（通过 data.json 特征文件）
        
        银河数据集结构: task_dir/robot_id/YYYYMMDD_recordN/data.json
        
        Args:
            dataset_base: device_model_annotation.yaml 所在目录（任务目录）
            max_episodes: 最大episode数量
            
        Returns:
            Episode目录列表（包含data.json的目录）
        """
        episodes = []
        
        try:
            # 遍历 robot_id 目录
            for robot_dir in dataset_base.iterdir():
                if not robot_dir.is_dir():
                    continue
                
                # 遍历 episode 目录
                for episode_dir in robot_dir.iterdir():
                    if not episode_dir.is_dir():
                        continue
                    
                    # 检查是否有 data.json（episode特征文件）
                    if (episode_dir / "data.json").exists():
                        episodes.append(episode_dir)
                        
                        if max_episodes and len(episodes) >= max_episodes:
                            return episodes
        
        except Exception as e:
            print(f"  ⚠️  遍历失败: {e}")
        
        return episodes
    
    def validate_episode(self, episode_dir: Path) -> ValidationResult:
        """
        验证单个episode（静态方法，可多进程调用）
        """
        errors = []
        warnings = []
        
        # 解析路径结构
        try:
            episode_name = episode_dir.name
            robot_id = episode_dir.parent.name
            task_name = episode_dir.parent.parent.name
        except Exception as e:
            errors.append(f"路径结构错误: {e}")
            return ValidationResult(
                episode_path=str(episode_dir),
                is_valid=False,
                errors=errors,
                warnings=warnings,
                task_name="unknown",
                robot_id="unknown",
                episode_name=str(episode_dir.name)
            )
        
        # 1. 检查视频文件
        for video_name in self.required_videos:
            video_path = episode_dir / video_name
            if not video_path.exists():
                errors.append(f"缺失: {video_name}")
            elif video_path.stat().st_size == 0:
                errors.append(f"空文件: {video_name}")
        
        # 2. 检查 data.json
        json_path = episode_dir / "data.json"
        if not json_path.exists():
            errors.append("缺失: data.json")
        else:
            # 完整读取JSON文件（之前的10MB限制会导致大文件被截断）
            try:
                with open(json_path, encoding='utf-8') as f:
                    data = json.load(f)  # 直接使用json.load()而不是读取字符串
                
                if 'data' not in data:
                    errors.append("JSON缺少'data'字段")
                else:
                    data_section = data['data']
                    for field in self.required_json_fields:
                        if field not in data_section:
                            errors.append(f"JSON缺少: {field}")
                        elif not isinstance(data_section[field], list):
                            errors.append(f"JSON字段类型错误: {field}")
                        elif len(data_section[field]) == 0:
                            errors.append(f"JSON字段为空: {field}")
            
            except json.JSONDecodeError as e:
                errors.append(f"JSON解析失败: {e}")
            except Exception as e:
                errors.append(f"读取JSON失败: {e}")
        
        # 3. report.txt（可选）
        if not (episode_dir / "report.txt").exists():
            warnings.append("缺失report.txt(可选)")
        
        return ValidationResult(
            episode_path=str(episode_dir),
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            task_name=task_name,
            robot_id=robot_id,
            episode_name=episode_name
        )
    
    def validate_all(self, max_episodes: Optional[int] = None) -> list[ValidationResult]:
        """
        验证所有episodes（并行）
        """
        # 1. 发现数据集
        datasets = self.discover_datasets()
        if not datasets:
            print("❌ 未找到任何数据集")
            return []
        
        # 2. 查找所有episodes
        all_episodes = []
        for yaml_path, version in datasets:
            dataset_base = yaml_path.parent
            print(f"  📂 {dataset_base.name} (version: {version})")
            
            remaining = None if not max_episodes else (max_episodes - len(all_episodes))
            episodes = self.find_episodes_fast(dataset_base, max_episodes=remaining)
            print(f"    找到 {len(episodes)} 个episodes")
            all_episodes.extend(episodes)
            
            if max_episodes and len(all_episodes) >= max_episodes:
                break
        
        print(f"\n📊 总计: {len(all_episodes)} 个episodes")
        
        if not all_episodes:
            print("❌ 未找到任何episodes")
            return []
        
        # 3. 并行验证
        print(f"\n🧪 开始验证 (使用 {self.max_workers} 个进程)...")
        results = []
        
        # 准备参数：(episode_dir, required_videos, required_json_fields)
        tasks = [(ep, self.required_videos, self.required_json_fields) for ep in all_episodes]
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(_validate_episode_worker, task): task[0] for task in tasks}
            
            for i, future in enumerate(as_completed(futures), 1):
                try:
                    result = future.result()
                    results.append(result)
                    
                    # 打印进度
                    if self.verbose or not result.is_valid:
                        status = "✅" if result.is_valid else "❌"
                        print(f"  [{i}/{len(all_episodes)}] {status} {result.task_name}/{result.episode_name}")
                        if result.errors:
                            for error in result.errors[:3]:
                                print(f"      • {error}")
                    elif i % 100 == 0:
                        print(f"  进度: {i}/{len(all_episodes)} episodes")
                
                except Exception as e:
                    episode = futures[future]
                    print(f"  [{i}/{len(all_episodes)}] ❌ {episode.name} - 验证异常: {e}")
        
        return results
    
    def move_error_episodes(self, results: list[ValidationResult], error_threshold: float = 0.9) -> tuple[int, int]:
        """
        移动有问题的episodes到error文件夹
        
        Args:
            results: 验证结果列表
            error_threshold: 错误率阈值，超过此值的错误类型被认为是配置问题，不移动文件
            
        Returns:
            (moved_count, skipped_count): 移动的数量和跳过的数量
        """
        if not results:
            return 0, 0
        
        # 1. 先检测配置问题
        total = len(results)
        invalid_results = [r for r in results if not r.is_valid]
        
        # 统计错误类型
        error_types = {}
        for result in invalid_results:
            for error in result.errors:
                error_types[error] = error_types.get(error, 0) + 1
        
        # 识别配置问题（错误率>=阈值）
        config_error_patterns = set()
        for error, count in error_types.items():
            if count / total >= error_threshold:
                config_error_patterns.add(error)
        
        # 2. 移动非配置问题的episode
        moved_count = 0
        skipped_count = 0
        
        for result in invalid_results:
            # 检查是否所有错误都是配置问题
            is_config_issue = all(err in config_error_patterns for err in result.errors)
            
            if is_config_issue:
                skipped_count += 1
                if self.verbose:
                    print(f"  ⏭️  跳过（配置问题）: {result.task_name}/{result.robot_id}/{result.episode_name}")
                continue
            
            # 移动到error文件夹
            try:
                episode_path = Path(result.episode_path)
                if not episode_path.exists():
                    continue
                
                # 创建error目录
                error_dir = episode_path.parent / "error"
                error_dir.mkdir(exist_ok=True)
                
                # 移动整个episode目录
                dest = error_dir / episode_path.name
                if dest.exists():
                    if self.verbose:
                        print(f"  ⚠️  目标已存在: {dest}")
                    continue
                
                import shutil
                shutil.move(str(episode_path), str(dest))
                moved_count += 1
                
                if self.verbose:
                    print(f"  📦 已移动: {result.task_name}/{result.robot_id}/{result.episode_name} -> error/")
            
            except Exception as e:
                print(f"  ❌ 移动失败 {result.episode_path}: {e}")
        
        return moved_count, skipped_count
    
    def print_summary(self, results: list[ValidationResult], output_file: Optional[str] = None):
        """打印验证总结并检测配置问题"""
        if not results:
            print("\n📊 验证总结: 没有结果")
            return
        
        total = len(results)
        valid = sum(1 for r in results if r.is_valid)
        invalid = total - valid
        
        print("\n" + "="*70)
        print("📊 验证总结")
        print("="*70)
        print(f"总Episodes: {total}")
        print(f"✅ 有效: {valid} ({valid/total*100:.1f}%)")
        print(f"❌ 无效: {invalid} ({invalid/total*100:.1f}%)")
        
        # 按任务统计
        task_stats = {}
        for result in results:
            task = result.task_name
            if task not in task_stats:
                task_stats[task] = {"total": 0, "valid": 0}
            task_stats[task]["total"] += 1
            if result.is_valid:
                task_stats[task]["valid"] += 1
        
        if task_stats:
            print("\n📋 按任务统计:")
            for task, stats in sorted(task_stats.items()):
                v, t = stats["valid"], stats["total"]
                print(f"  {task}: {v}/{t} ({v/t*100:.1f}%)")
        
        # 错误类型统计和配置问题检测
        config_issues = []
        if invalid > 0:
            error_types = {}
            for result in results:
                if not result.is_valid:
                    for error in result.errors:
                        error_types[error] = error_types.get(error, 0) + 1
            
            print("\n❌ 常见错误类型 (Top 10):")
            for error, count in sorted(error_types.items(), key=lambda x: -x[1])[:10]:
                print(f"  [{count:4d}] {error}")
            
            # 检测配置问题：如果某个错误出现在所有或大部分episode中
            for error, count in error_types.items():
                error_rate = count / total
                # 如果错误率 >= 90%，认为是配置问题
                if error_rate >= 0.9:
                    config_issues.append({
                        'error': error,
                        'count': count,
                        'rate': error_rate,
                        'total': total
                    })
        
        # 输出配置问题到文件
        if config_issues and output_file:
            print(f"\n⚠️  检测到配置问题（错误率>=90%），写入到: {output_file}")
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("="*70 + "\n")
                f.write("配置问题检测报告 - 银河数据集\n")
                f.write("="*70 + "\n\n")
                f.write(f"数据集路径: {self.data_root}\n")
                f.write(f"总Episodes: {total}\n")
                f.write(f"有效Episodes: {valid}\n")
                f.write(f"无效Episodes: {invalid}\n\n")
                
                f.write("检测到以下配置问题（所有或大部分episode都有相同错误）：\n")
                f.write("-"*70 + "\n\n")
                
                for issue in config_issues:
                    f.write(f"错误类型: {issue['error']}\n")
                    f.write(f"出现次数: {issue['count']}/{issue['total']} ({issue['rate']*100:.1f}%)\n")
                    f.write(f"问题分析: 此错误出现在{issue['rate']*100:.1f}%的episodes中，")
                    f.write("很可能是device_model_annotation.yaml或converter config配置错误\n")
                    f.write("\n建议措施:\n")
                    
                    if "缺失" in issue['error'] and "mp4" in issue['error'].lower():
                        video_name = issue['error'].split(':')[1].strip() if ':' in issue['error'] else "未知视频"
                        f.write(f"  1. 检查 converter config 中的 camera_paths 配置\n")
                        f.write(f"  2. 检查 device_model_annotation.yaml 中的 device_model_version\n")
                        f.write(f"  3. 确认该数据集是否真的包含 {video_name}\n")
                    elif "JSON字段缺失" in issue['error']:
                        field_name = issue['error'].split(':')[1].strip() if ':' in issue['error'] else "未知字段"
                        f.write(f"  1. 检查 converter config 中的 h5_paths 配置\n")
                        f.write(f"  2. 查看实际的 data.json 文件结构\n")
                        f.write(f"  3. 确认 device_model_version 是否正确\n")
                    else:
                        f.write("  1. 检查 device_model_annotation.yaml 配置\n")
                        f.write("  2. 检查 converter config 文件\n")
                        f.write("  3. 确认 device_model 和 version 的对应关系\n")
                    
                    f.write("\n" + "-"*70 + "\n\n")
                
                f.write("\n注意: 这些episode不应该移动到error文件夹，应该修正配置文件后重新验证\n")
            
            print(f"   配置问题已记录，包含 {len(config_issues)} 个问题")
            for issue in config_issues:
                print(f"   - {issue['error']} ({issue['rate']*100:.1f}%)")
        
        print("="*70)


def _validate_episode_worker(task: tuple) -> ValidationResult:
    """
    验证单个episode的worker函数（用于多进程）
    
    Args:
        task: (episode_dir, required_videos, required_json_fields)
    
    Returns:
        ValidationResult
    
    注意：必须是模块级函数才能被pickle
    """
    episode_dir, required_videos, required_json_fields = task
    episode_dir = Path(episode_dir) if not isinstance(episode_dir, Path) else episode_dir
    
    errors = []
    warnings = []
    
    try:
        episode_name = episode_dir.name
        robot_id = episode_dir.parent.name
        task_name = episode_dir.parent.parent.name
    except Exception as e:
        return ValidationResult(
            episode_path=str(episode_dir),
            is_valid=False,
            errors=[f"路径错误: {e}"],
            warnings=[],
            task_name="unknown",
            robot_id="unknown",
            episode_name=str(episode_dir.name)
        )
    
    # 检查视频
    for video_name in required_videos:
        video_path = episode_dir / video_name
        if not video_path.exists():
            errors.append(f"缺失: {video_name}")
        elif video_path.stat().st_size == 0:
            errors.append(f"空文件: {video_name}")
    
    # 检查JSON
    json_path = episode_dir / "data.json"
    if not json_path.exists():
        errors.append("缺失: data.json")
    else:
        try:
            with open(json_path, encoding='utf-8') as f:
                data = json.load(f)  # 完整读取JSON文件
            
            if 'data' not in data:
                errors.append("JSON缺少'data'字段")
            else:
                data_section = data['data']
                for field in required_json_fields:
                    if field not in data_section:
                        errors.append(f"JSON缺少: {field}")
                    elif not isinstance(data_section[field], list):
                        errors.append(f"字段类型错误: {field}")
                    elif len(data_section[field]) == 0:
                        errors.append(f"字段为空: {field}")
        except Exception as e:
            errors.append(f"JSON错误: {e}")
    
    if not (episode_dir / "report.txt").exists():
        warnings.append("缺失report.txt")
    
    return ValidationResult(
        episode_path=str(episode_dir),
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        task_name=task_name,
        robot_id=robot_id,
        episode_name=episode_name
    )


def main():
    parser = argparse.ArgumentParser(
        description="银河数据集预转换验证工具 (高性能版)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=Path("/mnt/nas/synnas/docker/外部数据/银河通用"),
        help="数据集根目录"
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="converter config yaml路径"
    )
    parser.add_argument(
        "--max-episodes",
        type=int,
        help="最大验证数量（测试用）"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="并行进程数（默认8）"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细模式"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="配置问题报告输出文件路径（默认：validation_config_issues.txt）"
    )
    parser.add_argument(
        "--move-errors",
        action="store_true",
        help="自动移动有问题的episodes到error文件夹（配置问题除外）"
    )
    
    args = parser.parse_args()
    
    if not args.dataset_path.exists():
        print(f"❌ 路径不存在: {args.dataset_path}")
        sys.exit(1)
    
    # 设置默认输出文件
    output_file = args.output if args.output else args.dataset_path / "validation_config_issues.txt"
    
    print(f"🚀 银河数据集验证器 v2 (高性能版)")
    print(f"📁 数据集: {args.dataset_path}")
    print(f"⚙️  并行度: {args.workers}")
    if args.move_errors:
        print("🔧 错误移动模式: 开启")
    print()
    
    validator = YinheValidatorV2(
        str(args.dataset_path),
        config_path=str(args.config) if args.config else None,
        verbose=args.verbose,
        max_workers=args.workers
    )
    
    results = validator.validate_all(max_episodes=args.max_episodes)
    validator.print_summary(results, output_file=str(output_file))
    
    # 移动错误文件
    if args.move_errors:
        print("\n📦 开始移动错误episodes...")
        moved, skipped = validator.move_error_episodes(results)
        print(f"✅ 移动完成: {moved} 个episodes已移动到error文件夹")
        print(f"⏭️  跳过: {skipped} 个episodes（配置问题）")
    
    invalid_count = sum(1 for r in results if not r.is_valid)
    sys.exit(0 if invalid_count == 0 else 1)


if __name__ == "__main__":
    main()
