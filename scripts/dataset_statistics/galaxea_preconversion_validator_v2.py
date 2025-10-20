#!/usr/bin/env python3
"""
Galaxea R1 Lite (星海图) H5+MP4 Pre-Conversion Validator V2

验证galaxea r1 lite (星海图) 数据集的H5+MP4格式episode，在转换前检测潜在问题。
支持通过converter_factory_config.yaml自动发现配置文件。

数据格式：
- H5文件: qpos (14D), action (14D)
- MP4视频: *_cam_high.mp4, *_cam_left_wrist.mp4, *_cam_right_wrist.mp4
- Parquet文件: *.parquet (可选)

主要功能：
1. 自动从device_model_annotation.yaml读取device_model和version
2. 通过factory config自动匹配对应的converter config
3. 验证H5文件和MP4视频完整性
4. 多进程并行处理提升性能
5. 智能区分config问题和data问题
6. 自动移动有问题的episode到error文件夹（可选）

使用示例：
    # 基础验证
    python3 galaxea_preconversion_validator_v2.py --dataset-path /path/to/galaxea

    # 完整验证+自动移动错误
    python3 galaxea_preconversion_validator_v2.py --dataset-path /path/to/galaxea --workers 8 --move-errors --verbose

    # 快速测试前10个episode
    python3 galaxea_preconversion_validator_v2.py --dataset-path /path/to/galaxea --max-episodes 10
"""

import argparse
import h5py
import json
import shutil
import sys
import time
import yaml
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional


class GalaxeaPreconversionValidator:
    """Galaxea R1 Lite (星海图) H5+MP4格式数据集预转换验证器"""

    def __init__(
        self,
        dataset_path: str,
        factory_config_path: Optional[str] = None,
        verbose: bool = False
    ):
        """
        初始化验证器
        
        Args:
            dataset_path: 数据集根目录（通常是videos/train）
            factory_config_path: factory config文件路径（可选，默认自动查找）
            verbose: 是否打印详细日志
        """
        self.dataset_path = Path(dataset_path)
        self.verbose = verbose
        
        # Factory config路径
        if factory_config_path:
            self.factory_config_path = Path(factory_config_path)
        else:
            # 默认路径：相对于脚本位置
            script_dir = Path(__file__).parent
            default_path = script_dir / "../format_converters/tolerobot/configs/converter_factory_config.yaml"
            self.factory_config_path = default_path.resolve()
        
        # 加载factory config
        self.factory_config = self._load_factory_config()
        
        # 数据结构
        self.task_folders = []  # [(task_path, device_model, version, config)]
        self.config_cache = {}  # 缓存已加载的config
        
    def _load_factory_config(self) -> dict:
        """加载factory config文件"""
        if not self.factory_config_path.exists():
            print(f"警告: Factory config未找到: {self.factory_config_path}")
            return {}
        
        try:
            with open(self.factory_config_path, encoding='utf-8') as f:
                config = yaml.safe_load(f)
            if self.verbose:
                print(f"✓ 已加载factory config: {self.factory_config_path}")
            return config or {}
        except Exception as e:
            print(f"错误: 无法加载factory config: {e}")
            return {}
    
    def _auto_find_config(self, device_model: str, version: str) -> Optional[Path]:
        """
        通过factory config自动查找converter config路径
        
        Args:
            device_model: 设备型号
            version: 版本号
            
        Returns:
            config文件路径，如果未找到返回None
        """
        if device_model not in self.factory_config:
            if self.verbose:
                print(f"警告: device_model '{device_model}' 不在factory config中")
            return None
        
        versions = self.factory_config[device_model]
        if not isinstance(versions, list):
            if self.verbose:
                print(f"警告: device_model '{device_model}' 的版本配置格式错误")
            return None
        
        # 查找匹配的version
        for ver_config in versions:
            if ver_config.get('version') == version:
                config_filename = ver_config.get('converter_config_path')
                if not config_filename:
                    if self.verbose:
                        print(f"警告: version '{version}' 没有converter_config_path")
                    return None
                
                # 构建完整路径（相对于factory config）
                config_dir = self.factory_config_path.parent
                config_path = config_dir / config_filename
                
                if not config_path.exists():
                    if self.verbose:
                        print(f"警告: Config文件不存在: {config_path}")
                    return None
                
                if self.verbose:
                    print(f"✓ 找到config: {device_model} + {version} -> {config_filename}")
                return config_path
        
        if self.verbose:
            print(f"警告: 未找到匹配的version '{version}' for device_model '{device_model}'")
        return None
    
    def _load_config_from_path(self, config_path: Path) -> Optional[dict]:
        """从路径加载converter config"""
        # 检查缓存
        cache_key = str(config_path)
        if cache_key in self.config_cache:
            return self.config_cache[cache_key]
        
        try:
            with open(config_path, encoding='utf-8') as f:
                config = yaml.safe_load(f)
            self.config_cache[cache_key] = config
            return config
        except Exception as e:
            print(f"错误: 无法加载config {config_path}: {e}")
            return None
    
    def discover_datasets(self) -> int:
        """
        发现所有task文件夹及其配置
        
        Returns:
            发现的task数量
        """
        print(f"正在扫描数据集: {self.dataset_path}")
        
        if not self.dataset_path.exists():
            print(f"错误: 数据集路径不存在: {self.dataset_path}")
            return 0
        
        # 查找所有包含device_model_annotation.yaml的文件夹（只搜索一级子目录）
        task_count = 0
        for task_folder in self.dataset_path.iterdir():
            if not task_folder.is_dir():
                continue
            
            yaml_file = task_folder / "device_model_annotation.yaml"
            if not yaml_file.exists():
                continue
            
            # 读取device_model和version
            try:
                with open(yaml_file, encoding='utf-8') as f:
                    device_info = yaml.safe_load(f)
                
                device_model = device_info.get('device_model')
                version = device_info.get('device_model_version')
                
                if not device_model or not version:
                    print(f"警告: {yaml_file} 缺少device_model或device_model_version")
                    continue
                
                # 自动查找config
                config_path = self._auto_find_config(device_model, version)
                if not config_path:
                    print(f"警告: 未找到config for {device_model} + {version}，跳过 {task_folder}")
                    continue
                
                # 加载config
                config = self._load_config_from_path(config_path)
                if not config:
                    print(f"警告: 无法加载config，跳过 {task_folder}")
                    continue
                
                # 添加到列表
                self.task_folders.append((task_folder, device_model, version, config))
                task_count += 1
                
                if self.verbose:
                    print(f"  发现task: {task_folder.name} ({device_model}, {version})")
                    
            except Exception as e:
                print(f"警告: 处理 {yaml_file} 时出错: {e}")
                continue
        
        print(f"✓ 发现 {task_count} 个task文件夹")
        return task_count
    
    def find_episodes(self, task_folder: Path) -> list[Path]:
        """
        在task文件夹中查找所有episode（包含.hdf5文件的子文件夹）
        
        Args:
            task_folder: task文件夹路径
            
        Returns:
            episode文件夹列表
        """
        episodes = []
        
        # 查找包含.hdf5文件的子文件夹
        for hdf5_file in task_folder.glob("*/*.hdf5"):
            episode_folder = hdf5_file.parent
            
            # 确保episode文件夹是task的直接子文件夹
            if episode_folder.parent == task_folder:
                if episode_folder not in episodes:
                    episodes.append(episode_folder)
        
        return sorted(episodes)
    
    def validate_episode(
        self,
        episode_folder: Path,
        config: dict,
        device_model: str,
        version: str
    ) -> tuple[bool, list[str]]:
        """
        验证单个episode
        
        Args:
            episode_folder: episode文件夹路径
            config: converter config
            device_model: 设备型号
            version: 版本号
            
        Returns:
            (是否通过, 错误列表)
        """
        errors = []
        
        # 1. 检查H5文件
        hdf5_files = list(episode_folder.glob("*.hdf5"))
        if not hdf5_files:
            errors.append("缺少.hdf5文件")
        elif len(hdf5_files) > 1:
            errors.append(f"找到多个.hdf5文件: {[f.name for f in hdf5_files]}")
        else:
            hdf5_file = hdf5_files[0]
            
            # 验证H5文件内容
            h5_errors = self._validate_h5_content(hdf5_file, config)
            errors.extend(h5_errors)
        
        # 2. 检查MP4视频文件
        images_config = config.get('features', {}).get('observation', {}).get('images', [])
        for img_cfg in images_config:
            video_pattern = img_cfg.get('args', {}).get('video_file_pattern', '')
            if video_pattern:
                # 查找匹配的视频文件
                video_files = list(episode_folder.glob(video_pattern))
                if not video_files:
                    errors.append(f"缺少视频文件: {video_pattern}")
                elif len(video_files) > 1:
                    errors.append(f"找到多个视频文件 {video_pattern}: {[f.name for f in video_files]}")
        
        # 3. 检查parquet文件（可选）
        parquet_files = list(episode_folder.glob("*.parquet"))
        if not parquet_files and self.verbose:
            # Parquet文件是可选的，不作为错误
            pass
        
        return len(errors) == 0, errors
    
    def _validate_h5_content(self, hdf5_file: Path, config: dict) -> list[str]:
        """
        验证H5文件内部内容
        
        Args:
            hdf5_file: H5文件路径
            config: converter config
            
        Returns:
            错误列表
        """
        errors = []
        
        try:
            with h5py.File(hdf5_file, 'r') as f:
                # 检查state路径
                state_config = config.get('features', {}).get('observation', {}).get('state', {})
                sub_states = state_config.get('sub_state', [])
                for sub in sub_states:
                    h5_path = sub.get('args', {}).get('h5_path')
                    if h5_path and h5_path not in f:
                        errors.append(f"H5缺少路径: {h5_path}")
                
                # 检查action路径
                action_config = config.get('features', {}).get('action', {})
                sub_actions = action_config.get('sub_action', [])
                for sub in sub_actions:
                    h5_path = sub.get('args', {}).get('h5_path')
                    if h5_path and h5_path not in f:
                        errors.append(f"H5缺少路径: {h5_path}")
                        
        except Exception as e:
            errors.append(f"H5读取失败: {str(e)}")
        
        return errors
    
    def validate_all(
        self,
        max_workers: int = 4,
        max_episodes: Optional[int] = None
    ) -> dict[str, list[dict]]:
        """
        验证所有task中的所有episodes
        
        Args:
            max_workers: 并行进程数
            max_episodes: 最大验证episode数（用于测试）
            
        Returns:
            验证结果字典
        """
        if not self.task_folders:
            print("错误: 没有发现任何task文件夹")
            return {}
        
        print(f"\n开始验证，使用 {max_workers} 个并行进程...")
        
        all_results = {}
        total_episodes = 0
        
        for task_folder, device_model, version, config in self.task_folders:
            print(f"\n处理task: {task_folder.name} ({device_model}, {version})")
            
            # 查找episodes
            episodes = self.find_episodes(task_folder)
            
            if max_episodes and total_episodes + len(episodes) > max_episodes:
                episodes = episodes[:max_episodes - total_episodes]
            
            print(f"  找到 {len(episodes)} 个episodes")
            
            if not episodes:
                continue
            
            # 准备验证任务
            tasks = [
                (ep, config, device_model, version)
                for ep in episodes
            ]
            
            # 多进程验证
            results = []
            start_time = time.time()
            
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _validate_episode_worker,
                        episode_folder,
                        config,
                        device_model,
                        version
                    ): episode_folder
                    for episode_folder, config, device_model, version in tasks
                }
                
                completed = 0
                for future in as_completed(futures):
                    episode_folder = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                        completed += 1
                        
                        if completed % 100 == 0 or self.verbose:
                            print(f"  进度: {completed}/{len(episodes)}")
                            
                    except Exception as e:
                        print(f"  错误: {episode_folder.name} 验证失败: {e}")
                        results.append({
                            'episode': str(episode_folder),
                            'episode_name': episode_folder.name,
                            'passed': False,
                            'errors': [f"验证进程异常: {str(e)}"],
                            'device_model': device_model,
                            'version': version
                        })
            
            elapsed = time.time() - start_time
            print(f"  完成验证 {len(episodes)} episodes，耗时 {elapsed:.1f}s")
            
            all_results[task_folder.name] = results
            total_episodes += len(episodes)
            
            if max_episodes and total_episodes >= max_episodes:
                print(f"\n已达到最大episode数 {max_episodes}，停止验证")
                break
        
        return all_results
    
    def print_summary(self, results: dict[str, list[dict]]) -> None:
        """
        打印验证结果摘要
        
        Args:
            results: 验证结果字典
        """
        print("\n" + "="*80)
        print("验证结果摘要")
        print("="*80)
        
        total_episodes = 0
        total_passed = 0
        total_failed = 0
        error_stats = defaultdict(int)
        
        for task_name, task_results in results.items():
            task_passed = sum(1 for r in task_results if r['passed'])
            task_failed = len(task_results) - task_passed
            
            total_episodes += len(task_results)
            total_passed += task_passed
            total_failed += task_failed
            
            print(f"\nTask: {task_name}")
            print(f"  总计: {len(task_results)} episodes")
            print(f"  通过: {task_passed} episodes ({task_passed/len(task_results)*100:.1f}%)")
            print(f"  失败: {task_failed} episodes ({task_failed/len(task_results)*100:.1f}%)")
            
            # 统计错误类型
            for result in task_results:
                if not result['passed']:
                    for error in result['errors']:
                        error_stats[error] += 1
        
        print(f"\n总体统计:")
        print(f"  总计: {total_episodes} episodes")
        print(f"  通过: {total_passed} episodes ({total_passed/total_episodes*100:.1f}%)")
        print(f"  失败: {total_failed} episodes ({total_failed/total_episodes*100:.1f}%)")
        
        if error_stats:
            print(f"\n错误类型统计:")
            sorted_errors = sorted(error_stats.items(), key=lambda x: x[1], reverse=True)
            
            # 判断config问题
            config_problems = []
            data_problems = []
            error_threshold = 0.9  # 90%以上认为是config问题
            
            for error, count in sorted_errors:
                error_rate = count / total_failed if total_failed > 0 else 0
                is_config_problem = error_rate >= error_threshold
                
                if is_config_problem:
                    config_problems.append((error, count, error_rate))
                else:
                    data_problems.append((error, count, error_rate))
                
                marker = "⚠️ [配置问题]" if is_config_problem else ""
                print(f"  {marker} {error}: {count} 次 ({error_rate*100:.1f}%)")
            
            # 输出配置问题建议
            if config_problems:
                print(f"\n{'='*80}")
                print("🔧 检测到配置问题（影响≥90%的失败episodes）:")
                print("="*80)
                for error, count, rate in config_problems:
                    print(f"\n问题: {error}")
                    print(f"  影响: {count}/{total_failed} 失败episodes ({rate*100:.1f}%)")
                    print(f"  建议: 检查device_model_annotation.yaml或converter config配置")
                print(f"\n💡 这些问题应该修改配置文件，而不是移动episode到error文件夹")
        
        print("="*80)
    
    def move_error_episodes(
        self,
        results: dict[str, list[dict]],
        error_threshold: float = 0.9,
        output_dir: Optional[Path] = None
    ) -> tuple[int, int]:
        """
        移动有问题的episodes到error文件夹，但排除config问题
        
        Args:
            results: 验证结果
            error_threshold: 错误率阈值，超过此值的错误类型被视为config问题
            output_dir: 输出目录，如果提供则在此目录生成报告
            
        Returns:
            (移动的episode数, 跳过的episode数)
        """
        print(f"\n{'='*80}")
        print("开始移动问题episodes...")
        print("="*80)
        
        # 1. 统计所有错误类型，识别config问题
        total_failed = sum(
            1 for task_results in results.values()
            for r in task_results if not r['passed']
        )
        
        if total_failed == 0:
            print("没有失败的episodes，无需移动")
            return 0, 0
        
        error_stats = defaultdict(int)
        for task_results in results.values():
            for result in task_results:
                if not result['passed']:
                    for error in result['errors']:
                        error_stats[error] += 1
        
        # 识别config问题
        config_errors = set()
        for error, count in error_stats.items():
            error_rate = count / total_failed
            if error_rate >= error_threshold:
                config_errors.add(error)
                print(f"识别为配置问题: {error} ({error_rate*100:.1f}%)")
        
        # 2. 移动非config问题的episodes
        moved_count = 0
        skipped_count = 0
        config_issue_episodes = []
        
        for task_name, task_results in results.items():
            for result in task_results:
                if result['passed']:
                    continue
                
                # 检查是否全是config问题
                has_data_error = False
                episode_errors = []
                
                for error in result['errors']:
                    if error not in config_errors:
                        has_data_error = True
                    episode_errors.append({
                        'error': error,
                        'is_config_issue': error in config_errors
                    })
                
                episode_folder = Path(result['episode'])
                
                if has_data_error:
                    # 有数据问题，移动到error文件夹
                    try:
                        error_folder = episode_folder.parent / "error"
                        error_folder.mkdir(exist_ok=True)
                        
                        dest = error_folder / episode_folder.name
                        if dest.exists():
                            print(f"  跳过（目标已存在）: {episode_folder.name}")
                            skipped_count += 1
                        else:
                            shutil.move(str(episode_folder), str(dest))
                            moved_count += 1
                            if self.verbose:
                                print(f"  已移动: {episode_folder.name} -> error/")
                    except Exception as e:
                        print(f"  移动失败 {episode_folder.name}: {e}")
                        skipped_count += 1
                else:
                    # 只有config问题，不移动，记录到列表
                    config_issue_episodes.append({
                        'episode': result['episode_name'],
                        'task': task_name,
                        'errors': episode_errors,
                        'device_model': result.get('device_model', 'unknown'),
                        'version': result.get('version', 'unknown')
                    })
                    skipped_count += 1
        
        print(f"\n移动统计:")
        print(f"  已移动到error/: {moved_count} episodes")
        print(f"  跳过（配置问题）: {skipped_count} episodes")
        
        # 3. 生成配置问题报告
        if config_issue_episodes:
            report_file = output_dir / "validation_config_issues.txt" if output_dir else Path("validation_config_issues.txt")
            
            try:
                with open(report_file, 'w', encoding='utf-8') as f:
                    f.write("="*80 + "\n")
                    f.write("配置问题报告\n")
                    f.write("="*80 + "\n\n")
                    f.write(f"检测到 {len(config_issue_episodes)} 个episodes存在配置问题\n")
                    f.write("这些episodes未被移动到error文件夹，需要修改配置文件\n\n")
                    
                    # 按task分组
                    by_task = defaultdict(list)
                    for ep in config_issue_episodes:
                        by_task[ep['task']].append(ep)
                    
                    for task_name, episodes in sorted(by_task.items()):
                        f.write(f"\n{'='*80}\n")
                        f.write(f"Task: {task_name}\n")
                        f.write(f"{'='*80}\n")
                        f.write(f"Device Model: {episodes[0]['device_model']}\n")
                        f.write(f"Version: {episodes[0]['version']}\n")
                        f.write(f"问题Episodes数量: {len(episodes)}\n\n")
                        
                        # 统计错误类型
                        task_errors = defaultdict(int)
                        for ep in episodes:
                            for err in ep['errors']:
                                if err['is_config_issue']:
                                    task_errors[err['error']] += 1
                        
                        f.write("配置问题统计:\n")
                        for error, count in sorted(task_errors.items(), key=lambda x: x[1], reverse=True):
                            f.write(f"  - {error}: {count} episodes\n")
                        
                        f.write("\n建议修改:\n")
                        f.write("  1. 检查 device_model_annotation.yaml 文件\n")
                        f.write("  2. 检查对应的 converter config 文件\n")
                        f.write("  3. 确认配置中的H5路径、视频文件模式等是否正确\n")
                        
                        f.write(f"\n受影响的Episodes（前10个）:\n")
                        for ep in episodes[:10]:
                            f.write(f"  - {ep['episode']}\n")
                        
                        if len(episodes) > 10:
                            f.write(f"  ... 还有 {len(episodes)-10} 个episodes\n")
                
                print(f"\n✓ 配置问题报告已保存: {report_file}")
                
            except Exception as e:
                print(f"警告: 无法保存配置问题报告: {e}")
        
        print("="*80)
        return moved_count, skipped_count


def _validate_episode_worker(
    episode_folder: Path,
    config: dict,
    device_model: str,
    version: str
) -> dict:
    """
    Worker函数用于多进程验证
    
    Args:
        episode_folder: episode文件夹路径
        config: converter config
        device_model: 设备型号
        version: str
            
    Returns:
        验证结果字典
    """
    # 创建临时验证器实例（不需要初始化整个validator）
    validator = GalaxeaPreconversionValidator.__new__(GalaxeaPreconversionValidator)
    validator.verbose = False
    
    passed, errors = validator.validate_episode(
        episode_folder,
        config,
        device_model,
        version
    )
    
    return {
        'episode': str(episode_folder),
        'episode_name': episode_folder.name,
        'passed': passed,
        'errors': errors,
        'device_model': device_model,
        'version': version
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Galaxea R1 Lite (星海图) H5+MP4 Pre-Conversion Validator V2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础验证
  %(prog)s --dataset-path /path/to/galaxea/videos/train

  # 完整验证+自动移动错误
  %(prog)s --dataset-path /path/to/galaxea/videos/train --workers 8 --move-errors --verbose

  # 快速测试
  %(prog)s --dataset-path /path/to/galaxea/videos/train --max-episodes 10
        """
    )
    
    parser.add_argument(
        '--dataset-path',
        type=str,
        required=True,
        help='数据集根目录路径（通常是videos/train目录）'
    )
    
    parser.add_argument(
        '--factory-config',
        type=str,
        help='Factory config文件路径（可选，默认自动查找）'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=4,
        help='并行进程数（默认: 4）'
    )
    
    parser.add_argument(
        '--max-episodes',
        type=int,
        help='最大验证episode数，用于测试（可选）'
    )
    
    parser.add_argument(
        '--move-errors',
        action='store_true',
        help='自动移动有问题的episodes到error文件夹'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='输出目录，用于保存报告（默认: 当前目录）'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='打印详细日志'
    )
    
    args = parser.parse_args()
    
    # 创建输出目录
    output_dir = Path(args.output) if args.output else Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建验证器
    validator = GalaxeaPreconversionValidator(
        dataset_path=args.dataset_path,
        factory_config_path=args.factory_config,
        verbose=args.verbose
    )
    
    # 发现数据集
    task_count = validator.discover_datasets()
    if task_count == 0:
        print("未发现任何task，退出")
        sys.exit(1)
    
    # 验证所有episodes
    results = validator.validate_all(
        max_workers=args.workers,
        max_episodes=args.max_episodes
    )
    
    # 打印摘要
    validator.print_summary(results)
    
    # 移动错误episodes（如果启用）
    if args.move_errors:
        moved, skipped = validator.move_error_episodes(
            results,
            output_dir=output_dir
        )
        print(f"\n最终统计: 移动 {moved} episodes, 跳过 {skipped} episodes")
    
    # 保存完整结果到JSON
    results_file = output_dir / "validation_results.json"
    try:
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n完整结果已保存: {results_file}")
    except Exception as e:
        print(f"警告: 无法保存结果文件: {e}")


if __name__ == '__main__':
    main()
