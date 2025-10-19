#!/usr/bin/env python3
"""
智平方(Zhipingfang) 数据集预转换验证工具 (高性能版)

核心优化:
1. 以 device_model_annotation.yaml 为基准定位数据集
2. 使用 .h5 文件作为episode特征文件快速定位
3. 多进程并行验证
4. 只检查H5文件keys，不加载完整数据
5. 从 converter config 读取required paths

数据集结构:
智平方/
├── dataset_collection/
│   ├── device_model_annotation.yaml  # 版本标识文件
│   ├── local_dataset_info.yaml
│   └── episode_*.h5  # Episode特征文件 ⭐
"""

import argparse
import h5py
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
    episode_name: str


class ZhipingfangValidatorV2:
    """智平方数据集验证器 (高性能版)"""
    
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
            
            # 提取 H5 paths
            self.required_h5_paths = []
            state = observation.get('state', {})
            sub_states = state.get('sub_state', [])
            for sub in sub_states:
                h5_path = sub.get('args', {}).get('h5_path')
                if h5_path:
                    self.required_h5_paths.append(h5_path)
            
            # 提取相机名称 (从 images)
            self.required_cameras = []
            images = observation.get('images', [])
            for img in images:
                # 从名称推断相机名
                name = img.get('name', '')
                if 'head' in name.lower():
                    self.required_cameras.append('head')
            
            if self.verbose:
                print(f"✅ 从config加载: {len(self.required_h5_paths)} 个H5路径, {len(self.required_cameras)} 个相机")
                print(f"   配置文件: {config_path.name}")
        
        except Exception as e:
            print(f"⚠️  加载config失败: {e}")
            self._use_default_config()
    
    def _use_default_config(self):
        """使用默认配置"""
        self.required_h5_paths = [
            "observations/arm/left/joints",
            "observations/camera/rgb/head/images",
            "action"
        ]
        self.required_cameras = ["head"]
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
            "converter_config_zhipingfang.yaml"
        ]
        
        for pattern in patterns:
            config_file = self.config_dir / pattern
            if config_file.exists():
                return config_file
        
        return None
    
    def discover_datasets(self) -> list[tuple[Path, str]]:
        """
        发现所有数据集（通过 device_model_annotation.yaml）
        
        智平方结构: dataset_collection/device_model_annotation.yaml
        
        Returns:
            [(yaml_path, version), ...]
        """
        print("🔍 查找 device_model_annotation.yaml 文件...")
        
        yaml_files = []
        self._find_yaml_recursive(self.data_root, yaml_files, max_depth=3, current_depth=0)
        
        # 读取版本信息
        datasets = []
        for yaml_path in yaml_files:
            try:
                with open(yaml_path, encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    version = data.get('device_model_version', 'default_version')
                    device_model = data.get('device_model', 'zhipingfang')
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
                print("⚠️  未找到匹配的config文件，使用默认配置")
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
                elif item.is_dir() and item.name not in ['error', 'config']:
                    self._find_yaml_recursive(item, results, max_depth, current_depth + 1)
        except PermissionError:
            pass
        except Exception:
            pass
    
    def find_episodes_fast(self, dataset_base: Path, max_episodes: Optional[int] = None) -> list[Path]:
        """
        快速查找episodes（通过 .h5 特征文件）
        
        智平方结构: dataset_base/*.h5 (episode_*.h5 或 converted_*.h5)
        
        Args:
            dataset_base: device_model_annotation.yaml 所在目录
            max_episodes: 最大episode数量
            
        Returns:
            H5文件路径列表
        """
        episodes = []
        
        try:
            for item in dataset_base.iterdir():
                if item.is_file() and item.suffix == '.h5':
                    # 支持 episode_*.h5 和 converted_*.h5 等各种命名
                    episodes.append(item)
                    
                    if max_episodes and len(episodes) >= max_episodes:
                        break
        except Exception as e:
            if self.verbose:
                print(f"  ⚠️  遍历失败: {e}")
        
        return sorted(episodes)
    
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
        
        tasks = [(ep, self.required_h5_paths) for ep in all_episodes]
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(_validate_episode_worker, task): task[0] for task in tasks}
            
            for i, future in enumerate(as_completed(futures), 1):
                try:
                    result = future.result()
                    results.append(result)
                    
                    if self.verbose or not result.is_valid:
                        status = "✅" if result.is_valid else "❌"
                        print(f"  [{i}/{len(all_episodes)}] {status} {result.dataset_name}/{result.episode_name}")
                        if result.errors:
                            for error in result.errors[:3]:
                                print(f"      • {error}")
                    elif i % 100 == 0:
                        print(f"  进度: {i}/{len(all_episodes)} episodes")
                
                except Exception as e:
                    episode = futures[future]
                    print(f"  [{i}/{len(all_episodes)}] ❌ {episode.name} - 验证异常: {e}")
        
        return results
    
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
                f.write("配置问题检测报告 - 智平方数据集\n")
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
                    
                    if "H5缺少路径" in issue['error']:
                        h5_path = issue['error'].split(':')[1].strip() if ':' in issue['error'] else "未知路径"
                        f.write(f"  1. 检查 converter config 中的 h5_path 配置: {h5_path}\n")
                        f.write("  2. 使用 h5dump 或 h5py 查看实际的H5文件结构\n")
                        f.write("  3. 确认 device_model_version 是否正确\n")
                        f.write(f"  4. 可能需要创建新的 converter_config_zhipingfang_xxx.yaml\n")
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
        task: (h5_file_path, required_h5_paths)
    """
    h5_file, required_h5_paths = task
    h5_file = Path(h5_file) if not isinstance(h5_file, Path) else h5_file
    
    errors = []
    warnings = []
    
    episode_name = h5_file.name
    dataset_name = h5_file.parent.name
    
    # 检查H5文件
    if not h5_file.exists():
        errors.append("文件不存在")
    elif h5_file.stat().st_size == 0:
        errors.append("文件大小为0")
    else:
        # 检查H5内部结构（只检查keys，不加载数据）
        try:
            with h5py.File(h5_file, 'r') as f:
                for path in required_h5_paths:
                    if path not in f:
                        errors.append(f"H5缺少路径: {path}")
        except Exception as e:
            errors.append(f"H5读取失败: {e}")
    
    return ValidationResult(
        episode_path=str(h5_file),
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        dataset_name=dataset_name,
        episode_name=episode_name
    )


def main():
    parser = argparse.ArgumentParser(
        description="智平方数据集预转换验证工具 (高性能版)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dataset-path",
        type=Path,
        required=True,
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
    
    args = parser.parse_args()
    
    if not args.dataset_path.exists():
        print(f"❌ 路径不存在: {args.dataset_path}")
        sys.exit(1)
    
    # 设置默认输出文件
    output_file = args.output if args.output else args.dataset_path / "validation_config_issues.txt"
    
    print("🚀 智平方数据集验证器 v2 (高性能版)")
    print(f"📁 数据集: {args.dataset_path}")
    print(f"⚙️  并行度: {args.workers}")
    print()
    
    validator = ZhipingfangValidatorV2(
        str(args.dataset_path),
        config_path=str(args.config) if args.config else None,
        verbose=args.verbose,
        max_workers=args.workers
    )
    
    results = validator.validate_all(max_episodes=args.max_episodes)
    validator.print_summary(results, output_file=str(output_file))
    
    invalid_count = sum(1 for r in results if not r.is_valid)
    sys.exit(0 if invalid_count == 0 else 1)


if __name__ == "__main__":
    main()
