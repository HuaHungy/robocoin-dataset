#!/usr/bin/env python3
"""
软通天擎(Ruantong) 数据集预转换验证工具 (高性能版)

核心优化:
1. 以 device_model_annotation.yaml 为基准定位数据集
2. 使用 aligned_joints.h5 作为episode特征文件快速定位
3. 多进程并行验证
4. 只检查文件存在性和基本结构，不完整加载
5. 从 converter config 读取required paths

数据集结构:
软通天擎/
├── gt01/zy/21_备料区场景5/375/
│   ├── device_model_annotation.yaml  # 版本标识文件
│   ├── local_dataset_info.yaml
│   └── A2D0015AC00066/
│       └── 39476/  # Episode目录
│           ├── aligned_joints.h5  # Episode特征文件 ⭐
│           ├── camera/
│           │   ├── 1/
│           │   │   ├── camera_D415-1_color.jpg
│           │   │   └── camera_D415-2_color.jpg
│           │   └── 2/
│           └── meta_info.json
"""

import argparse
import h5py
import json
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
    dataset_name: str
    robot_id: str
    episode_id: str


class RuantongValidatorV2:
    """软通天擎数据集验证器 (高性能版)"""
    
    def __init__(self, data_root: str, config_path: str = None, config_dir: str = None, verbose: bool = False, max_workers: int = 4):
        self.data_root = Path(data_root)
        self.config_path = Path(config_path) if config_path else None
        self.config_dir = Path(config_dir) if config_dir else Path(__file__).parent.parent / "format_converters" / "tolerobot" / "configs"
        self.verbose = verbose
        self.max_workers = max_workers
        
        # 从config加载验证规则（如果已指定config）
        self.required_h5_paths = []
        self.required_cameras = []
        
        if self.config_path and self.config_path.exists():
            self._load_config_from_path(self.config_path)
        # 否则等待 discover_datasets() 后自动加载
    
    def _load_config_from_path(self, config_path: Path):
        """从指定路径加载config"""
        try:
            with open(config_path, encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 从 features 提取
            features = config.get('features', {})
            observation = features.get('observation', {})
            
            # 提取 H5 paths (从 action 和 state)
            self.required_h5_paths = []
            action = features.get('action', {})
            sub_actions = action.get('sub_action', [])
            for sub in sub_actions:
                h5_path = sub.get('args', {}).get('h5_path')
                if h5_path and '{' not in h5_path:  # 排除包含{frame_idx}的路径
                    self.required_h5_paths.append(h5_path)
            
            state = observation.get('state', {})
            sub_states = state.get('sub_state', [])
            for sub in sub_states:
                h5_path = sub.get('args', {}).get('h5_path')
                if h5_path and '{' not in h5_path:
                    self.required_h5_paths.append(h5_path)
            
            # 提取相机文件名 (从 images 的 h5_path 中提取文件名部分)
            self.required_cameras = []
            images = observation.get('images', [])
            for img in images:
                h5_path = img.get('args', {}).get('h5_path', '')
                # h5_path 格式: camera/{frame_idx}/head_color.jpg
                if '{frame_idx}' in h5_path:
                    # 提取文件名部分（不带扩展名）
                    filename = h5_path.split('/')[-1].split('.')[0]
                    self.required_cameras.append(filename)
            
            if self.verbose:
                print(f"✅ 从config加载: {len(self.required_h5_paths)} 个H5路径, {len(self.required_cameras)} 个相机")
                print(f"   配置文件: {config_path.name}")
        
        except Exception as e:
            print(f"⚠️  加载config失败: {e}")
            self._use_default_config()
    
    def _use_default_config(self):
        """使用默认配置"""
        self.required_h5_paths = [
            "action/joint",
            "state/joint",
            "timestamp"
        ]
        self.required_cameras = [
            "head_color",
            "hand_left_color", 
            "hand_right_color"
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
            print(f"  Factory配置未找到，尝试文件名匹配...")
        
        patterns = [
            f"converter_config_{device_model}_{version}.yaml",
            f"converter_config_{device_model}.yaml",
            f"converter_config_ruantong_{version}.yaml",
            "converter_config_ruantong.yaml"
        ]
        
        for pattern in patterns:
            config_file = self.config_dir / pattern
            if config_file.exists():
                return config_file
        
        return None
    
    def discover_datasets(self) -> list[tuple[Path, str]]:
        """
        发现所有数据集（通过 device_model_annotation.yaml）
        
        软通天擎结构: gt01/zy/21_备料区场景5/375/device_model_annotation.yaml
        已知版本目录: gt01, gt02, jx01, jx02
        
        Returns:
            [(yaml_path, version), ...]
        """
        print("🔍 查找 device_model_annotation.yaml 文件...")
        
        yaml_files = []
        
        # 软通天擎：优先搜索已知版本目录
        known_versions = ['gt01', 'gt02', 'jx01', 'jx02']
        for version_dir_name in known_versions:
            version_dir = self.data_root / version_dir_name
            if version_dir.exists() and version_dir.is_dir():
                self._find_yaml_recursive(version_dir, yaml_files, max_depth=4, current_depth=0)
        
        # 读取版本信息
        datasets = []
        for yaml_path in yaml_files:
            try:
                with open(yaml_path, encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    version = data.get('device_model_version', 'default_version')
                    device_model = data.get('device_model', 'ruantong')
                    datasets.append((yaml_path, version, device_model))
            except Exception as e:
                if self.verbose:
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
                print(f"⚠️  未找到匹配的config文件，使用默认配置")
                print(f"   尝试查找: converter_config_{first_device}_{first_version}.yaml")
                self._use_default_config()
        elif not self.config_path:
            print("⚠️  未指定config文件且未找到数据集，使用默认配置")
            self._use_default_config()
        
        print(f"✅ 找到 {len(datasets)} 个数据集")
        # 转换回旧格式（为了保持兼容性）
        return [(yaml, ver) for yaml, ver, _ in datasets]
    
    def _find_yaml_recursive(self, directory: Path, results: list, max_depth: int, current_depth: int):
        """递归查找yaml文件"""
        if current_depth > max_depth:
            return
        
        try:
            for item in directory.iterdir():
                if item.is_file() and item.name == 'device_model_annotation.yaml':
                    results.append(item)
                elif item.is_dir() and item.name not in ['error', 'config', 'lost+found']:
                    self._find_yaml_recursive(item, results, max_depth, current_depth + 1)
        except PermissionError:
            pass
        except Exception:
            pass
    
    def find_episodes_fast(self, dataset_base: Path, max_episodes: Optional[int] = None) -> list[Path]:
        """
        快速查找episodes（通过 aligned_joints.h5 特征文件）
        
        软通天擎结构: dataset_base/robot_id/episode_id/aligned_joints.h5
        
        Args:
            dataset_base: device_model_annotation.yaml 所在目录
            max_episodes: 最大episode数量
            
        Returns:
            Episode目录列表
        """
        episodes = []
        
        # 递归搜索 aligned_joints.h5
        self._find_episodes_recursive(dataset_base, episodes, max_depth=4, max_episodes=max_episodes)
        
        return episodes
    
    def _find_episodes_recursive(self, directory: Path, episodes: list, max_depth: int, 
                                 max_episodes: Optional[int] = None, current_depth: int = 0):
        """递归查找episode目录"""
        if current_depth > max_depth:
            return
        
        if max_episodes and len(episodes) >= max_episodes:
            return
        
        try:
            for item in directory.iterdir():
                if max_episodes and len(episodes) >= max_episodes:
                    return
                
                if item.is_dir():
                    # 检查是否是episode目录（包含 aligned_joints.h5）
                    h5_file = item / "aligned_joints.h5"
                    if h5_file.exists():
                        episodes.append(item)
                    else:
                        # 继续递归搜索
                        self._find_episodes_recursive(item, episodes, max_depth, max_episodes, current_depth + 1)
        except PermissionError:
            pass
        except Exception:
            pass
    
    def validate_all(self, max_episodes: Optional[int] = None) -> list[ValidationResult]:
        """验证所有episodes（并行）"""
        # 1. 发现数据集
        datasets = self.discover_datasets()
        if not datasets:
            print("❌ 未找到任何数据集")
            return []
        
        # 2. 查找所有episodes
        all_episodes = []
        for yaml_path, version in datasets:
            dataset_base = yaml_path.parent
            dataset_name = dataset_base.name
            print(f"  📂 {dataset_name} (version: {version})")
            
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
        
        tasks = [(ep, self.required_h5_paths, self.required_cameras) for ep in all_episodes]
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(_validate_episode_worker, task): task[0] for task in tasks}
            
            for i, future in enumerate(as_completed(futures), 1):
                try:
                    result = future.result()
                    results.append(result)
                    
                    if self.verbose or not result.is_valid:
                        status = "✅" if result.is_valid else "❌"
                        print(f"  [{i}/{len(all_episodes)}] {status} {result.dataset_name}/{result.episode_id}")
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
                    print(f"  ⏭️  跳过（配置问题）: {result.dataset_name}/{result.episode_id}")
                continue
            
            # 移动到error文件夹
            try:
                episode_path = Path(result.episode_path)
                if not episode_path.exists():
                    continue
                
                # 创建error目录
                error_dir = episode_path.parent / "error"
                try:
                    error_dir.mkdir(exist_ok=True)
                except PermissionError:
                    print(f"  ❌ 无权限创建error目录: {error_dir}")
                    print(f"     请检查目录权限或使用sudo运行")
                    continue
                
                # 移动整个episode目录
                dest = error_dir / episode_path.name
                if dest.exists():
                    if self.verbose:
                        print(f"  ⚠️  目标已存在: {dest}")
                    continue
                
                import shutil
                try:
                    shutil.move(str(episode_path), str(dest))
                    moved_count += 1
                    
                    if self.verbose:
                        print(f"  📦 已移动: {result.dataset_name}/{result.episode_id} -> error/")
                except PermissionError:
                    print(f"  ❌ 无权限移动: {episode_path}")
                    print(f"     源: {episode_path}")
                    print(f"     目标: {dest}")
                    print(f"     请检查目录权限或使用sudo运行")
            
            except PermissionError as e:
                print(f"  ❌ 权限错误 {result.episode_path}: {e}")
                print(f"     提示: 可能需要使用 sudo 或修改目录权限")
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
        
        # 按数据集统计
        dataset_stats = {}
        for result in results:
            ds = result.dataset_name
            if ds not in dataset_stats:
                dataset_stats[ds] = {"total": 0, "valid": 0}
            dataset_stats[ds]["total"] += 1
            if result.is_valid:
                dataset_stats[ds]["valid"] += 1
        
        if dataset_stats:
            print("\n📋 按数据集统计:")
            for ds, stats in sorted(dataset_stats.items()):
                v, t = stats["valid"], stats["total"]
                print(f"  {ds}: {v}/{t} ({v/t*100:.1f}%)")
        
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
                f.write("配置问题检测报告\n")
                f.write("="*70 + "\n\n")
                f.write(f"数据集路径: {self.data_root}\n")
                f.write(f"验证时间: {Path(__file__).stat().st_mtime}\n")
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
                    
                    if "缺失" in issue['error'] and "jpg" in issue['error'].lower():
                        # 相机图片配置问题
                        camera_name = issue['error'].split(':')[1].strip().split()[0] if ':' in issue['error'] else "未知相机"
                        f.write(f"  ❌ 相机配置问题: {camera_name}\n")
                        f.write(f"  1. 检查 converter config 的 observation.images 中是否错误配置了 {camera_name}\n")
                        f.write("  2. 检查 device_model_annotation.yaml 中的 device_model_version\n")
                        f.write(f"  3. 确认该数据集是否真的包含 {camera_name} 相机\n")
                        f.write("  4. 对比其他正常的数据集版本，看是否版本标注错误\n")
                    elif "H5缺少路径" in issue['error']:
                        # H5路径配置问题
                        h5_path = issue['error'].split(':')[1].strip() if ':' in issue['error'] else "未知路径"
                        f.write(f"  ❌ H5路径配置问题: {h5_path}\n")
                        f.write(f"  1. 检查 converter config 的 action/state 配置中的 h5_path: {h5_path}\n")
                        f.write("  2. 使用以下命令查看实际的H5文件结构:\n")
                        f.write("     python3 -c \"import h5py; f=h5py.File('aligned_joints.h5'); f.visit(print)\"\n")
                        f.write("  3. 确认 device_model_version 是否正确对应了该数据的H5结构\n")
                        f.write("  4. 如果H5结构已变更，需要更新converter config或创建新版本配置\n")
                    elif "H5读取失败" in issue['error']:
                        # H5文件损坏
                        f.write("  ❌ H5文件问题（可能是数据采集或存储问题）\n")
                        f.write("  1. 这可能不是配置问题，而是数据质量问题\n")
                        f.write("  2. 检查H5文件是否完整或损坏\n")
                        f.write("  3. 如果大量episode都有此问题，可能是采集过程有误\n")
                    else:
                        # 其他配置问题
                        f.write("  ❌ 一般配置问题\n")
                        f.write("  1. 检查 device_model_annotation.yaml 配置\n")
                        f.write("  2. 检查 converter config 文件\n")
                        f.write("  3. 确认 device_model 和 version 的对应关系\n")
                        f.write("  4. 查看factory config (converter_factory_config.yaml)的映射关系\n")
                    
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
        task: (episode_dir, required_h5_paths, required_cameras)
    """
    episode_dir, required_h5_paths, required_cameras = task
    episode_dir = Path(episode_dir) if not isinstance(episode_dir, Path) else episode_dir
    
    errors = []
    warnings = []
    
    try:
        episode_id = episode_dir.name
        robot_id = episode_dir.parent.name
        # 向上查找数据集名称（375这一级）
        dataset_name = "unknown"
        parent = episode_dir.parent
        for _ in range(10):
            if (parent / "device_model_annotation.yaml").exists():
                dataset_name = parent.name
                break
            parent = parent.parent
            if parent == parent.parent:
                break
    except Exception as e:
        return ValidationResult(
            episode_path=str(episode_dir),
            is_valid=False,
            errors=[f"路径错误: {e}"],
            warnings=[],
            dataset_name="unknown",
            robot_id="unknown",
            episode_id=str(episode_dir.name)
        )
    
    # 1. 检查 aligned_joints.h5
    h5_file = episode_dir / "aligned_joints.h5"
    if not h5_file.exists():
        errors.append("缺失: aligned_joints.h5")
    elif h5_file.stat().st_size == 0:
        errors.append("空文件: aligned_joints.h5")
    else:
        # 检查H5内部结构（只检查keys，不加载数据）
        try:
            with h5py.File(h5_file, 'r') as f:
                for path in required_h5_paths:
                    if path not in f:
                        errors.append(f"H5缺少路径: {path}")
        except Exception as e:
            errors.append(f"H5读取失败: {e}")
    
    # 2. 检查 camera 目录
    camera_dir = episode_dir / "camera"
    if not camera_dir.exists():
        errors.append("缺失: camera/")
    elif not camera_dir.is_dir():
        errors.append("camera不是目录")
    else:
        # 检查至少有一个帧目录
        try:
            frame_dirs = [d for d in camera_dir.iterdir() if d.is_dir()]
            if len(frame_dirs) == 0:
                errors.append("camera/目录为空")
            else:
                # 检查第一帧的相机图片
                first_frame = sorted(frame_dirs)[0]
                for camera_name in required_cameras:
                    image_file = first_frame / f"{camera_name}.jpg"
                    if not image_file.exists():
                        errors.append(f"缺失: {camera_name}.jpg (第1帧)")
        except Exception as e:
            errors.append(f"camera目录检查失败: {e}")
    
    # 3. 检查 meta_info.json（可选）
    meta_file = episode_dir / "meta_info.json"
    if not meta_file.exists():
        warnings.append("缺失meta_info.json(可选)")
    else:
        try:
            with open(meta_file, encoding='utf-8') as f:
                meta = json.load(f)
            
            required_fields = ['camera_list', 'camera_type', 'fps']
            missing = [f for f in required_fields if f not in meta]
            if missing:
                warnings.append(f"meta_info缺少字段: {', '.join(missing)}")
        except Exception as e:
            warnings.append(f"meta_info解析失败: {e}")
    
    return ValidationResult(
        episode_path=str(episode_dir),
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        dataset_name=dataset_name,
        robot_id=robot_id,
        episode_id=episode_id
    )


def main():
    parser = argparse.ArgumentParser(
        description="软通天擎数据集预转换验证工具 (高性能版)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=Path("/mnt/nas/synnas/docker2/外部数据/软通天擎"),
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
    
    print("🚀 软通天擎数据集验证器 v2 (高性能版)")
    print(f"📁 数据集: {args.dataset_path}")
    print(f"⚙️  并行度: {args.workers}")
    if args.move_errors:
        print("🔧 错误移动模式: 开启")
    print()
    
    validator = RuantongValidatorV2(
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
