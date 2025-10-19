#!/usr/bin/env python3
"""
软通天擎数据集预转换验证工具

数据格式:
- Episode 目录包含: aligned_joints.h5 + camera/ + meta_info.json
- camera/ 按帧组织: camera/0/, camera/1/, ...
- 每帧包含多个图片: head_color.jpg, hand_left_color.jpg, 鱼眼相机等
- aligned_joints.h5 包含: state/*, action/* (嵌套group结构)

使用方法:
    # 验证所有GT数据版本
    python ruantong_preconversion_validator.py \\
        --data-root /mnt/nas/synnas/docker2/外部数据/软通天擎 \\
        --config-dir scripts/format_converters/tolerobot/configs
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import h5py
import yaml


class EpisodeValidator:
    """单个 episode 验证器"""
    
    def __init__(self, episode_dir: Path, config: dict):
        self.episode_dir = episode_dir
        self.config = config
        self.errors = []
        self.warnings = []
        
    def validate(self) -> bool:
        """执行验证"""
        try:
            if not self._check_structure():
                return False
            if not self._check_h5_file():
                return False
            if not self._check_images():
                return False
            if not self._check_meta_info():
                return False
            return len(self.errors) == 0
        except Exception as e:
            self.errors.append(f"验证异常: {e}")
            return False
    
    def _check_structure(self) -> bool:
        """检查基本目录结构"""
        h5_file = self.episode_dir / "aligned_joints.h5"
        camera_dir = self.episode_dir / "camera"
        meta_file = self.episode_dir / "meta_info.json"
        
        missing = []
        if not h5_file.exists():
            missing.append("aligned_joints.h5")
        if not camera_dir.exists():
            missing.append("camera/")
        if not meta_file.exists():
            self.warnings.append("meta_info.json 不存在")
        
        if missing:
            self.errors.append(f"缺少必要文件/目录: {', '.join(missing)}")
            return False
        
        return True
    
    def _check_h5_file(self) -> bool:
        """检查 H5 文件结构"""
        h5_path = self.episode_dir / "aligned_joints.h5"
        
        try:
            with h5py.File(h5_path, 'r') as f:
                # 检查是否有 state 和 action
                if 'state' not in f:
                    self.errors.append("H5文件缺少 'state' group")
                    return False
                if 'action' not in f:
                    self.errors.append("H5文件缺少 'action' group")
                    return False
                
                # 检查配置中的路径
                missing_paths = self._check_h5_paths(f)
                if missing_paths:
                    self.errors.append(
                        f"KeyError - H5路径不存在:\\n"
                        f"  缺少: {missing_paths[:5]}\\n"
                        f"  可用(示例): {self._get_available_paths(f)[:5]}"
                    )
                    return False
                
                # 检查数据维度
                if not self._check_h5_dimensions(f):
                    return False
        
        except Exception as e:
            self.errors.append(f"H5文件读取失败: {e}")
            return False
        
        return True
    
    def _check_h5_paths(self, h5_file) -> list:
        """检查配置路径是否存在"""
        missing = []
        
        # 检查 state paths
        if 'state' in self.config['features']['observation']:
            for sub in self.config['features']['observation']['state'].get('sub_state', []):
                if 'args' in sub and 'h5_path' in sub['args']:
                    path = sub['args']['h5_path']
                    # 去掉开头的 /
                    path = path.lstrip('/')
                    if path not in h5_file:
                        missing.append(path)
        
        # 检查 action paths
        if 'action' in self.config['features']:
            for sub in self.config['features']['action'].get('sub_action', []):
                if 'args' in sub and 'h5_path' in sub['args']:
                    path = sub['args']['h5_path']
                    path = path.lstrip('/')
                    if path not in h5_file:
                        missing.append(path)
        
        return missing
    
    def _get_available_paths(self, h5_file, max_depth=3) -> list:
        """获取可用的路径（示例）"""
        paths = []
        
        def visit(name, obj):
            if isinstance(obj, h5py.Dataset):
                paths.append(name)
        
        h5_file.visititems(visit)
        return paths
    
    def _check_h5_dimensions(self, h5_file) -> bool:
        """检查数据维度和切片"""
        # 检查 sub_states
        if 'state' in self.config['features']['observation']:
            for sub in self.config['features']['observation']['state'].get('sub_state', []):
                if not self._check_dataset_slice(h5_file, sub):
                    return False
        
        # 检查 sub_actions
        if 'action' in self.config['features']:
            for sub in self.config['features']['action'].get('sub_action', []):
                if not self._check_dataset_slice(h5_file, sub):
                    return False
        
        return True
    
    def _check_dataset_slice(self, h5_file, config: dict) -> bool:
        """检查数据集切片配置"""
        if 'args' not in config:
            return True
        
        args = config['args']
        h5_path = args.get('h5_path', '').lstrip('/')
        range_from = args.get('range_from')
        range_to = args.get('range_to')
        
        if not h5_path or h5_path not in h5_file:
            return True
        
        dataset = h5_file[h5_path]
        
        # 检查是否能读取第一帧
        if dataset.shape[0] == 0:
            self.warnings.append(f"数据集为空: {h5_path}")
            return True
        
        try:
            frame_data = dataset[0]
        except Exception as e:
            self.errors.append(f"IndexError - 无法读取: {h5_path}, {e}")
            return False
        
        # 检查切片范围
        if range_from is not None and range_to is not None:
            import numpy as np
            if not isinstance(frame_data, np.ndarray):
                frame_data = np.array(frame_data)
            
            if frame_data.ndim == 0:
                # 标量数据
                if not (range_from == 0 and range_to == 1):
                    self.errors.append(
                        f"ValueError - 标量数据无法切片: {h5_path}, "
                        f"range=[{range_from}:{range_to}]"
                    )
                    return False
            else:
                # 向量数据
                data_len = len(frame_data)
                if range_from < 0 or range_to > data_len or range_from >= range_to:
                    self.errors.append(
                        f"ValueError - 切片范围无效: {h5_path}, "
                        f"range=[{range_from}:{range_to}], len={data_len}"
                    )
                    return False
        
        return True
    
    def _check_images(self) -> bool:
        """检查图像文件"""
        camera_dir = self.episode_dir / "camera"
        
        # 找到所有帧目录
        frame_dirs = sorted([d for d in camera_dir.iterdir() if d.is_dir() and d.name.isdigit()])
        
        if not frame_dirs:
            self.errors.append("camera/ 目录中没有找到任何帧")
            return False
        
        # 检查第一帧的图像（作为样本）
        first_frame = frame_dirs[0]
        
        # 检查配置中的图像路径
        if 'images' not in self.config['features']['observation']:
            return True
        
        for img_config in self.config['features']['observation']['images']:
            if 'args' not in img_config:
                continue
            
            h5_path = img_config['args'].get('h5_path', '')
            # 替换 {frame_idx} 为实际帧号
            img_path = h5_path.replace('{frame_idx}', first_frame.name)
            
            # 转换为绝对路径
            full_path = self.episode_dir / img_path
            
            if not full_path.exists():
                cam_name = img_config.get('cam_name', '未知相机')
                self.errors.append(
                    f"KeyError - 图像文件不存在: {cam_name}\\n"
                    f"  预期: {img_path}\\n"
                    f"  完整路径: {full_path}"
                )
                return False
        
        return True
    
    def _check_meta_info(self) -> bool:
        """检查 meta_info.json"""
        meta_file = self.episode_dir / "meta_info.json"
        
        if not meta_file.exists():
            return True  # 已经在 _check_structure 中警告
        
        try:
            with open(meta_file, encoding='utf-8') as f:
                meta = json.load(f)
            
            # 检查基本字段
            required_fields = ['camera_list', 'camera_type', 'fps']
            missing = [f for f in required_fields if f not in meta]
            
            if missing:
                self.warnings.append(f"meta_info.json 缺少字段: {', '.join(missing)}")
        
        except Exception as e:
            self.warnings.append(f"meta_info.json 解析失败: {e}")
        
        return True


class RuantongDatasetVersion:
    """软通天擎数据版本"""
    def __init__(self, name: str, base_dir: Path):
        self.name = name  # 如 gt01, gt02, jx01
        self.base_dir = base_dir
        self.config_path: Path = None
        self.episodes: list[Path] = []
        self.failed_episodes: list[dict] = []
        self.warning_episodes: list[dict] = []


class RuantongValidator:
    """软通天擎验证器"""
    
    def __init__(self, data_root: str, config_dir: str, error_dir: str = None):
        self.data_root = Path(data_root)
        self.config_dir = Path(config_dir)
        self.error_dir = Path(error_dir) if error_dir else self.data_root / "error"
        
        self.versions: list[RuantongDatasetVersion] = []
        self.total_episodes = 0
        self.total_failed = 0
        self.total_warning = 0
        
        self.logs = []
    
    def log(self, msg: str, level: str = "INFO") -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}"
        print(line)
        self.logs.append(line)
    
    def discover_versions(self) -> None:
        """发现所有数据版本"""
        self.log("=" * 80)
        self.log("步骤 1: 发现数据版本")
        self.log("=" * 80)
        
        # 软通天擎的版本目录: gt01, gt02, jx01, jx02, ...
        version_dirs = [d for d in self.data_root.iterdir() 
                       if d.is_dir() and d.name not in ['config', 'error']]
        
        if not version_dirs:
            raise FileNotFoundError(f"未找到任何版本目录: {self.data_root}")
        
        self.log(f"找到 {len(version_dirs)} 个版本")
        
        for ver_dir in sorted(version_dirs):
            version = RuantongDatasetVersion(ver_dir.name, ver_dir)
            version.config_path = self._find_config(version.name)
            self.versions.append(version)
            
            self.log(f"  {ver_dir.name}")
            self.log(f"    配置: {version.config_path.name if version.config_path else '未找到'}")
    
    def _find_config(self, version_name: str) -> Path:
        """查找配置文件"""
        # 尝试匹配: converter_config_ruantong_{version_name}*.yaml
        pattern = f"converter_config_ruantong_{version_name}*.yaml"
        configs = list(self.config_dir.glob(pattern))
        
        if configs:
            # 优先选择 _no_depth 版本（更常见）
            no_depth = [c for c in configs if 'no_depth' in c.name]
            return no_depth[0] if no_depth else configs[0]
        
        # 尝试通用配置
        generic = self.config_dir / "converter_config_ruantong.yaml"
        if generic.exists():
            return generic
        
        return None
    
    def find_episodes(self) -> None:
        """查找所有 episode"""
        self.log("\\n" + "=" * 80)
        self.log("步骤 2: 索引 Episode")
        self.log("=" * 80)
        
        for version in self.versions:
            self.log(f"  正在扫描 {version.name}...")
            
            # 手动遍历目录树（更快）
            episodes = []
            self._find_episodes_recursive(version.base_dir, episodes, max_depth=6)
            
            version.episodes = episodes
            self.total_episodes += len(version.episodes)
            
            self.log(f"  {version.name}: {len(version.episodes)} 个 episode")
        
        self.log(f"\\n总计: {self.total_episodes} 个 episode")
    
    def _find_episodes_recursive(self, directory: Path, episodes: list, max_depth: int, current_depth: int = 0) -> None:
        """递归查找 episode（带深度限制）"""
        if current_depth > max_depth:
            return
        
        # 检查当前目录是否包含 aligned_joints.h5
        h5_file = directory / "aligned_joints.h5"
        if h5_file.exists():
            episodes.append(directory)
            return  # 找到了就不继续往下找了
        
        # 遍历子目录
        try:
            for child in directory.iterdir():
                if child.is_dir() and not child.name.startswith('.'):
                    self._find_episodes_recursive(child, episodes, max_depth, current_depth + 1)
        except PermissionError:
            pass
    
    def validate_all(self) -> None:
        """验证所有 episode"""
        self.log("\\n" + "=" * 80)
        self.log("步骤 3: 验证所有版本")
        self.log("=" * 80)
        
        for idx, version in enumerate(self.versions, 1):
            self.log(f"\\n[{idx}/{len(self.versions)}] {version.name}")
            
            if not version.config_path or not version.config_path.exists():
                self.log("  跳过: 无配置", "WARNING")
                continue
            
            try:
                with open(version.config_path, encoding='utf-8') as f:
                    config = yaml.safe_load(f)
            except Exception as e:
                self.log(f"  配置加载失败: {e}", "ERROR")
                continue
            
            failed = 0
            warning = 0
            
            for i, ep_dir in enumerate(version.episodes, 1):
                if i % 50 == 0:
                    self.log(f"  进度: {i}/{len(version.episodes)}")
                
                validator = EpisodeValidator(ep_dir, config)
                is_valid = validator.validate()
                
                if not is_valid:
                    version.failed_episodes.append({
                        'path': ep_dir,
                        'errors': validator.errors,
                        'warnings': validator.warnings
                    })
                    failed += 1
                elif validator.warnings:
                    version.warning_episodes.append({
                        'path': ep_dir,
                        'warnings': validator.warnings
                    })
                    warning += 1
            
            self.log(f"  失败: {failed}, 警告: {warning}")
            self.total_failed += failed
            self.total_warning += warning
        
        self.log(f"\\n总计: 失败={self.total_failed}, 警告={self.total_warning}")
    
    def move_failed(self) -> None:
        """移动失败的 episode"""
        if self.total_failed == 0:
            return
        
        self.log("\\n" + "=" * 80)
        self.log("步骤 4: 移动失败 Episode")
        self.log("=" * 80)
        
        self.error_dir.mkdir(parents=True, exist_ok=True)
        moved = 0
        
        for version in self.versions:
            for item in version.failed_episodes:
                ep_dir = item['path']
                rel = ep_dir.relative_to(self.data_root)
                dest = self.error_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                
                try:
                    shutil.move(str(ep_dir), str(dest))
                    moved += 1
                except Exception as e:
                    self.log(f"移动失败 {ep_dir.name}: {e}", "ERROR")
        
        self.log(f"移动 {moved} 个 episode 到 {self.error_dir}")
    
    def generate_report(self) -> Path:
        """生成报告"""
        self.log("\\n" + "=" * 80)
        self.log("步骤 5: 生成报告")
        self.log("=" * 80)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.data_root / f"validation_report_{timestamp}.txt"
        
        lines = []
        lines.append("=" * 80)
        lines.append("软通天擎预转换验证报告")
        lines.append("=" * 80)
        lines.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"版本数: {len(self.versions)}")
        lines.append(f"总 Episode: {self.total_episodes}")
        lines.append(f"失败: {self.total_failed}")
        lines.append(f"警告: {self.total_warning}")
        lines.append("")
        
        # 各版本统计
        lines.append("=" * 80)
        lines.append("各版本统计")
        lines.append("=" * 80)
        for version in self.versions:
            lines.append(f"\\n{version.name}")
            lines.append(f"  路径: {version.base_dir}")
            lines.append(f"  配置: {version.config_path.name if version.config_path else '无'}")
            lines.append(f"  Episode: {len(version.episodes)}")
            lines.append(f"  失败: {len(version.failed_episodes)}")
            lines.append(f"  警告: {len(version.warning_episodes)}")
        
        # 失败详情
        if self.total_failed > 0:
            lines.append("\\n" + "=" * 80)
            lines.append("失败 Episode 详情")
            lines.append("=" * 80)
            
            for version in self.versions:
                if not version.failed_episodes:
                    continue
                
                lines.append(f"\\n### {version.name}")
                
                for item in version.failed_episodes[:20]:  # 最多显示20个
                    ep_dir = item['path']
                    rel = ep_dir.relative_to(version.base_dir)
                    lines.append(f"\\n  {rel}")
                    for error in item['errors']:
                        for line in error.split('\\n'):
                            lines.append(f"    {line}")
                
                if len(version.failed_episodes) > 20:
                    lines.append(f"\\n  ... 还有 {len(version.failed_episodes) - 20} 个失败 episode")
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\\n'.join(lines))
        
        self.log(f"报告: {report_path}")
        return report_path
    
    def run(self, move_files: bool = True) -> bool:
        """执行验证"""
        try:
            self.discover_versions()
            self.find_episodes()
            self.validate_all()
            
            if move_files:
                self.move_failed()
            
            self.generate_report()
            
            self.log("\\n" + "=" * 80)
            self.log("验证完成!")
            self.log(f"失败: {self.total_failed}")
            self.log("=" * 80)
            
            return self.total_failed == 0
        except Exception as e:
            self.log(f"错误: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="软通天擎预转换验证工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 验证所有版本
  python ruantong_preconversion_validator.py \\
      --data-root /mnt/nas/synnas/docker2/外部数据/软通天擎 \\
      --config-dir scripts/format_converters/tolerobot/configs
  
  # Dry-run（不移动文件）
  python ruantong_preconversion_validator.py \\
      --data-root data/ruantong \\
      --config-dir examples/configs \\
      --dry-run
        """
    )
    
    parser.add_argument(
        '--data-root',
        type=str,
        default='/mnt/nas/synnas/docker2/外部数据/软通天擎',
        help='软通天擎数据根目录'
    )
    parser.add_argument(
        '--config-dir',
        type=str,
        required=True,
        help='转换配置文件目录'
    )
    parser.add_argument(
        '--error-dir',
        type=str,
        default=None,
        help='错误 episode 移动目标目录（默认: <data-root>/error）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只验证，不移动文件'
    )
    
    args = parser.parse_args()
    
    validator = RuantongValidator(
        data_root=args.data_root,
        config_dir=args.config_dir,
        error_dir=args.error_dir
    )
    
    success = validator.run(move_files=not args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
