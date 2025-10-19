#!/usr/bin/env python3
"""
智平方数据集预转换验证工具 - 多版本自动发现

目的: 
1. 自动发现所有 device_model_annotation.yaml（识别不同数据版本）
2. 为每个版本自动匹配转换配置
3. 检测每个版本下会导致转换失败的 H5 文件
4. 生成综合报告并隔离问题文件

使用方法:
    # 自动发现所有版本（推荐）
    python zhipingfang_preconversion_validator.py \\
        --data-root /mnt/nas/synnas/docker2/外部数据/智平方 \\
        --config-base /home/diy01/dev/robocoin-dataset/examples/configs
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import h5py
import yaml


class H5FileValidator:
    """H5 文件验证器 - 检测会导致转换失败的问题"""
    
    def __init__(self, h5_path: Path, config: dict):
        self.h5_path = h5_path
        self.config = config
        self.errors = []
        self.warnings = []
        self.h5_data = None
        
    def validate(self) -> bool:
        """执行验证"""
        try:
            if not self._open_h5_file():
                return False
            if not self._check_config_paths_exist():
                return False
            if not self._check_compressed_video_format():
                return False
            if not self._check_data_dimensions():
                return False
            return len(self.errors) == 0
        finally:
            if self.h5_data:
                self.h5_data.close()
    
    def _open_h5_file(self) -> bool:
        try:
            self.h5_data = h5py.File(self.h5_path, 'r')
            return True
        except Exception as e:
            self.errors.append(f"无法打开H5文件: {e}")
            return False
    
    def _check_config_paths_exist(self) -> bool:
        """检查配置路径是否存在"""
        all_h5_paths = self._extract_h5_paths_from_config()
        missing_paths = [p for p in all_h5_paths if p not in self.h5_data]
        
        if missing_paths:
            available = list(self.h5_data.keys())[:10]
            self.errors.append(
                f"KeyError - 配置路径不存在:\\n"
                f"  缺少: {missing_paths}\\n"
                f"  可用(前10): {available}"
            )
            return False
        return True
    
    def _extract_h5_paths_from_config(self) -> set:
        """从配置提取所有 h5_path"""
        paths = set()
        
        # observation.images
        if 'features' in self.config and 'observation' in self.config['features']:
            obs = self.config['features']['observation']
            if 'images' in obs:
                for img in obs['images']:
                    if 'args' in img and 'h5_path' in img['args']:
                        paths.add(img['args']['h5_path'])
                        if img['args'].get('use_compressed_video'):
                            if 'video_index_key' in img['args']:
                                paths.add(img['args']['video_index_key'])
            
            # observation.state
            if 'state' in obs and 'sub_state' in obs['state']:
                for sub in obs['state']['sub_state']:
                    if 'args' in sub and 'h5_path' in sub['args']:
                        paths.add(sub['args']['h5_path'])
        
        # action
        if 'features' in self.config and 'action' in self.config['features']:
            action = self.config['features']['action']
            if 'sub_action' in action:
                for sub in action['sub_action']:
                    if 'args' in sub and 'h5_path' in sub['args']:
                        paths.add(sub['args']['h5_path'])
        
        return paths
    
    def _check_compressed_video_format(self) -> bool:
        """检查压缩视频格式"""
        if 'features' not in self.config or 'observation' not in self.config['features']:
            return True
        
        obs = self.config['features']['observation']
        if 'images' not in obs:
            return True
        
        for img in obs['images']:
            if 'args' not in img or not img['args'].get('use_compressed_video'):
                continue
            
            h5_path = img['args'].get('h5_path')
            video_index_key = img['args'].get('video_index_key')
            
            if not h5_path or not video_index_key:
                self.errors.append(f"压缩视频配置不完整: {img.get('cam_name')}")
                return False
            
            video_path = h5_path.replace('/images', '/video')
            
            if video_path not in self.h5_data:
                self.errors.append(f"KeyError - 视频数据不存在: {video_path}")
                return False
            
            if video_index_key not in self.h5_data:
                self.errors.append(f"KeyError - 视频索引不存在: {video_index_key}")
                return False
        
        return True
    
    def _check_data_dimensions(self) -> bool:
        """检查数据维度"""
        # 检查 sub_states
        if 'features' in self.config and 'observation' in self.config['features']:
            obs = self.config['features']['observation']
            if 'state' in obs and 'sub_state' in obs['state']:
                for sub in obs['state']['sub_state']:
                    if not self._check_sub_state(sub):
                        return False
        
        # 检查 sub_actions
        if 'features' in self.config and 'action' in self.config['features']:
            action = self.config['features']['action']
            if 'sub_action' in action:
                for sub in action['sub_action']:
                    if not self._check_sub_action(sub):
                        return False
        
        return True
    
    def _check_sub_state(self, config: dict) -> bool:
        """检查 sub_state 维度"""
        if 'args' not in config:
            return True
        
        args = config['args']
        h5_path = args.get('h5_path')
        range_from = args.get('range_from')
        range_to = args.get('range_to')
        
        if not h5_path or h5_path not in self.h5_data:
            return True
        
        dataset = self.h5_data[h5_path]
        if dataset.shape[0] == 0:
            self.warnings.append(f"数据集为空: {h5_path}")
            return True
        
        try:
            frame_data = dataset[0]
        except Exception as e:
            self.errors.append(f"IndexError - 无法读取: {h5_path}, {e}")
            return False
        
        import numpy as np
        if not isinstance(frame_data, np.ndarray):
            frame_data = np.array(frame_data)
        
        if range_from is not None and range_to is not None:
            if frame_data.ndim == 0:
                if not (range_from == 0 and range_to == 1):
                    self.errors.append(
                        f"ValueError - 标量数据无法切片: {h5_path}, "
                        f"range=[{range_from}:{range_to}]"
                    )
                    return False
            else:
                data_len = len(frame_data)
                if range_from < 0 or range_to > data_len or range_from >= range_to:
                    self.errors.append(
                        f"ValueError - 切片范围无效: {h5_path}, "
                        f"range=[{range_from}:{range_to}], len={data_len}"
                    )
                    return False
        
        return True
    
    def _check_sub_action(self, config: dict) -> bool:
        """检查 sub_action 维度（逻辑同 sub_state）"""
        return self._check_sub_state(config)


class DatasetVersion:
    """数据集版本"""
    def __init__(self, yaml_path: Path) -> None:
        self.yaml_path = yaml_path
        self.base_dir = yaml_path.parent
        self.config_path: Path = None
        self.h5_files: list[Path] = []
        self.failed_files: list[dict] = []
        self.warning_files: list[dict] = []
        
        try:
            with open(yaml_path, encoding='utf-8') as f:
                data = yaml.safe_load(f)
                self.version = data.get('device_model_version', 'unknown')
        except Exception:
            self.version = 'unknown'


class ZhipingfangValidator:
    """智平方验证器 - 多版本"""
    
    def __init__(self, data_root: str, config_path: str = None, config_base: str = None, error_dir: str = None) -> None:
        self.data_root = Path(data_root)
        self.config_path = Path(config_path) if config_path else None
        self.config_base = Path(config_base) if config_base else None
        self.error_dir = Path(error_dir) if error_dir else self.data_root / "error"
        
        self.versions: list[DatasetVersion] = []
        self.total_h5 = 0
        self.total_failed = 0
        self.total_warning = 0
        
        self.logs = []
    
    def log(self, msg: str, level: str = "INFO"):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}"
        print(line)
        self.logs.append(line)
    
    def discover_versions(self):
        """发现所有版本"""
        self.log("=" * 80)
        self.log("步骤 1: 发现数据集版本")
        self.log("=" * 80)
        
        yaml_files = list(self.data_root.glob("**/device_model_annotation.yaml"))
        if not yaml_files:
            raise FileNotFoundError(f"未找到 device_model_annotation.yaml: {self.data_root}")
        
        self.log(f"找到 {len(yaml_files)} 个版本")
        
        for yaml_file in yaml_files:
            version = DatasetVersion(yaml_file)
            
            if self.config_path:
                version.config_path = self.config_path
            elif self.config_base:
                version.config_path = self._find_config(version)
            
            self.versions.append(version)
            
            rel_path = yaml_file.relative_to(self.data_root)
            self.log(f"  {rel_path.parent}")
            self.log(f"    版本: {version.version}")
            self.log(f"    配置: {version.config_path.name if version.config_path else '未找到'}")
    
    def _find_config(self, version: DatasetVersion) -> Path:
        """查找配置"""
        if not self.config_base or not self.config_base.exists():
            return None
        
        configs = list(self.config_base.glob("converter_config_zhipingfang*.yaml"))
        if not configs:
            return None
        
        # 优先选择 compressed_video 配置
        compressed = [c for c in configs if 'compressed_video' in c.name]
        return compressed[0] if compressed else configs[0]
    
    def find_h5_files(self):
        """查找 H5 文件"""
        self.log("\\n" + "=" * 80)
        self.log("步骤 2: 索引 H5 文件")
        self.log("=" * 80)
        
        for version in self.versions:
            same = list(version.base_dir.glob("*.h5")) + list(version.base_dir.glob("*.hdf5"))
            next_level = list(version.base_dir.glob("*/*.h5")) + list(version.base_dir.glob("*/*.hdf5"))
            
            version.h5_files = same + next_level
            self.total_h5 += len(version.h5_files)
            
            rel = version.base_dir.relative_to(self.data_root)
            self.log(f"  {rel}: {len(version.h5_files)} 个文件")
        
        self.log(f"\\n总计: {self.total_h5} 个 H5 文件")
    
    def validate_all(self):
        """验证所有文件"""
        self.log("\\n" + "=" * 80)
        self.log("步骤 3: 验证所有版本")
        self.log("=" * 80)
        
        for idx, version in enumerate(self.versions, 1):
            rel = version.base_dir.relative_to(self.data_root)
            self.log(f"\\n[{idx}/{len(self.versions)}] {rel}")
            
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
            
            for i, h5 in enumerate(version.h5_files, 1):
                if i % 100 == 0:
                    self.log(f"  进度: {i}/{len(version.h5_files)}")
                
                validator = H5FileValidator(h5, config)
                is_valid = validator.validate()
                
                if not is_valid:
                    version.failed_files.append({
                        'path': h5,
                        'errors': validator.errors,
                        'warnings': validator.warnings
                    })
                    failed += 1
                elif validator.warnings:
                    version.warning_files.append({
                        'path': h5,
                        'warnings': validator.warnings
                    })
                    warning += 1
            
            self.log(f"  失败: {failed}, 警告: {warning}")
            self.total_failed += failed
            self.total_warning += warning
        
        self.log(f"\\n总计: 失败={self.total_failed}, 警告={self.total_warning}")
    
    def move_failed(self):
        """移动失败文件"""
        if self.total_failed == 0:
            return
        
        self.log("\\n" + "=" * 80)
        self.log("步骤 4: 移动失败文件")
        self.log("=" * 80)
        
        self.error_dir.mkdir(parents=True, exist_ok=True)
        moved = 0
        
        for version in self.versions:
            for item in version.failed_files:
                h5 = item['path']
                rel = h5.relative_to(self.data_root)
                dest = self.error_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                
                try:
                    shutil.move(str(h5), str(dest))
                    moved += 1
                except Exception as e:
                    self.log(f"移动失败 {h5.name}: {e}", "ERROR")
        
        self.log(f"移动 {moved} 个文件到 {self.error_dir}")
    
    def generate_report(self):
        """生成报告"""
        self.log("\\n" + "=" * 80)
        self.log("步骤 5: 生成报告")
        self.log("=" * 80)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.data_root / f"validation_report_{timestamp}.txt"
        
        lines = []
        lines.append("=" * 80)
        lines.append("智平方预转换验证报告")
        lines.append("=" * 80)
        lines.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"版本数: {len(self.versions)}")
        lines.append(f"总文件: {self.total_h5}")
        lines.append(f"失败: {self.total_failed}")
        lines.append(f"警告: {self.total_warning}")
        lines.append("")
        
        # 各版本统计
        lines.append("=" * 80)
        lines.append("各版本统计")
        lines.append("=" * 80)
        for version in self.versions:
            rel = version.base_dir.relative_to(self.data_root)
            lines.append(f"\\n{rel}")
            lines.append(f"  版本: {version.version}")
            lines.append(f"  配置: {version.config_path.name if version.config_path else '无'}")
            lines.append(f"  文件: {len(version.h5_files)}")
            lines.append(f"  失败: {len(version.failed_files)}")
            lines.append(f"  警告: {len(version.warning_files)}")
        
        # 失败文件详情
        if self.total_failed > 0:
            lines.append("\\n" + "=" * 80)
            lines.append("失败文件详情")
            lines.append("=" * 80)
            
            for version in self.versions:
                if not version.failed_files:
                    continue
                
                rel = version.base_dir.relative_to(self.data_root)
                lines.append(f"\\n### {rel}")
                
                for item in version.failed_files:
                    h5 = item['path']
                    rel_h5 = h5.relative_to(version.base_dir)
                    lines.append(f"\\n  {rel_h5}")
                    for error in item['errors']:
                        for line in error.split('\\n'):
                            lines.append(f"    {line}")
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\\n'.join(lines))
        
        self.log(f"报告: {report_path}")
        return report_path
    
    def run(self, move_files: bool = True):
        """执行验证"""
        try:
            self.discover_versions()
            self.find_h5_files()
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


def main():
    parser = argparse.ArgumentParser(
        description="智平方预转换验证 - 多版本自动发现",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 自动发现所有版本
  python zhipingfang_preconversion_validator.py \\
      --data-root /mnt/nas/synnas/docker2/外部数据/智平方 \\
      --config-base examples/configs
  
  # 所有版本用同一配置
  python zhipingfang_preconversion_validator.py \\
      --config examples/configs/converter_config_zhipingfang_dual_arm_no_pose_compressed_video.yaml \\
      --data-root /mnt/nas/synnas/docker2/外部数据/智平方
        """
    )
    
    parser.add_argument('--data-root', type=str, default='/mnt/nas/synnas/docker2/外部数据/智平方')
    parser.add_argument('--config', type=str, default=None)
    parser.add_argument('--config-base', type=str, default=None)
    parser.add_argument('--error-dir', type=str, default=None)
    parser.add_argument('--dry-run', action='store_true')
    
    args = parser.parse_args()
    
    if not args.config and not args.config_base:
        print("错误: 必须指定 --config 或 --config-base")
        sys.exit(1)
    
    validator = ZhipingfangValidator(
        data_root=args.data_root,
        config_path=args.config,
        config_base=args.config_base,
        error_dir=args.error_dir
    )
    
    success = validator.run(move_files=not args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
