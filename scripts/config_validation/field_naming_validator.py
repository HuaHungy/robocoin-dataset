#!/usr/bin/env python3
"""
字段命名验证器
用于检查配置文件中的字段命名是否符合规范
"""

import yaml
import re
from pathlib import Path
from typing import Dict, List, Tuple


class FieldNamingValidator:
    """字段命名验证器"""
    
    # 关节命名规则：应该从1开始，不是从0
    JOINT_PATTERN = re.compile(r'(\w+)_joint_(\d+)(_\w+)?')
    
    # 单位后缀规则
    REQUIRED_SUFFIXES = {
        'joint': ['_rad', '_deg'],  # 关节角度
        'vel': ['_rad_s', '_deg_s', '_m_s'],  # 速度
        'eff': ['_nm', '_n'],  # 力/力矩
        'pos': ['_m', '_mm'],  # 位置
        'width': ['_m', '_mm'],  # 宽度/距离
        'force': ['_n'],  # 力
        'torque': ['_nm'],  # 力矩
    }
    
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.errors = []
        self.warnings = []
        
    def validate(self) -> Tuple[List[str], List[str]]:
        """验证配置文件
        
        Returns:
            (errors, warnings): 错误和警告列表
        """
        self.errors = []
        self.warnings = []
        
        # 加载配置
        with open(self.config_path) as f:
            config = yaml.safe_load(f)
        
        # 验证observation state
        if 'features' in config and 'observation' in config['features']:
            if 'state' in config['features']['observation']:
                self._validate_state_fields(
                    config['features']['observation']['state'].get('sub_state', []),
                    section='observation.state'
                )
        
        # 验证action
        if 'features' in config and 'action' in config['features']:
            self._validate_state_fields(
                config['features']['action'].get('sub_action', []),
                section='action'
            )
        
        return self.errors, self.warnings
    
    def _validate_state_fields(self, sub_states: List[Dict], section: str):
        """验证state/action字段"""
        for i, sub_state in enumerate(sub_states):
            names = sub_state.get('names', [])
            args = sub_state.get('args', {})
            range_from = args.get('range_from', 0)
            range_to = args.get('range_to', 0)
            
            # 检查字段数量与range是否匹配
            expected_count = range_to - range_from
            actual_count = len(names)
            
            if expected_count != actual_count:
                self.errors.append(
                    f"❌ [{section}] sub_state[{i}]: 字段数量不匹配\n"
                    f"   期望: {expected_count} (range_from={range_from}, range_to={range_to})\n"
                    f"   实际: {actual_count}\n"
                    f"   字段: {names[:3]}..."
                )
            
            # 检查关节命名
            for field_name in names:
                self._validate_field_name(field_name, section, i)
    
    def _validate_field_name(self, field_name: str, section: str, index: int):
        """验证单个字段名"""
        
        # 1. 检查关节编号（应该从1开始）
        joint_match = self.JOINT_PATTERN.match(field_name)
        if joint_match:
            prefix = joint_match.group(1)  # e.g., "left_arm"
            joint_num = int(joint_match.group(2))  # e.g., 0 or 1
            suffix = joint_match.group(3) or ''  # e.g., "_rad"
            
            # 检查是否从0开始（错误）
            if joint_num == 0:
                self.errors.append(
                    f"❌ [{section}] 字段 '{field_name}': 关节编号从0开始（应该从1开始）\n"
                    f"   建议: {prefix}_joint_1{suffix}"
                )
            
            # 检查单位后缀
            if not suffix:
                self.warnings.append(
                    f"⚠️  [{section}] 字段 '{field_name}': 缺少单位后缀\n"
                    f"   建议添加: _rad, _deg, _m 等"
                )
            elif not self._has_valid_suffix(field_name):
                self.warnings.append(
                    f"⚠️  [{section}] 字段 '{field_name}': 单位后缀可能不规范\n"
                    f"   当前: {suffix}\n"
                    f"   常用后缀: {self._get_suggested_suffixes(field_name)}"
                )
        
        # 2. 检查非关节字段的单位后缀
        elif not self._has_valid_suffix(field_name):
            # 如果字段名包含position, velocity, effort等关键词但没有后缀
            keywords = ['position', 'velocity', 'effort', 'width', 'force', 'torque']
            if any(kw in field_name.lower() for kw in keywords):
                self.warnings.append(
                    f"⚠️  [{section}] 字段 '{field_name}': 可能缺少单位后缀\n"
                    f"   建议添加: {self._get_suggested_suffixes(field_name)}"
                )
    
    def _has_valid_suffix(self, field_name: str) -> bool:
        """检查字段是否有有效的单位后缀"""
        for suffixes in self.REQUIRED_SUFFIXES.values():
            if any(field_name.endswith(suffix) for suffix in suffixes):
                return True
        return False
    
    def _get_suggested_suffixes(self, field_name: str) -> str:
        """获取建议的单位后缀"""
        field_lower = field_name.lower()
        
        if 'vel' in field_lower or 'velocity' in field_lower:
            return '_rad_s, _deg_s, _m_s'
        elif 'eff' in field_lower or 'effort' in field_lower:
            return '_nm, _n'
        elif 'force' in field_lower:
            return '_n'
        elif 'torque' in field_lower:
            return '_nm'
        elif 'width' in field_lower or 'pos' in field_lower or 'position' in field_lower:
            return '_m, _mm'
        elif 'joint' in field_lower:
            return '_rad, _deg'
        else:
            return '(根据实际物理单位添加)'
    
    def print_report(self):
        """打印验证报告"""
        errors, warnings = self.validate()
        
        print(f"\n{'='*80}")
        print(f"📋 字段命名验证报告")
        print(f"{'='*80}")
        print(f"配置文件: {self.config_path.name}")
        print()
        
        if errors:
            print(f"❌ 发现 {len(errors)} 个错误:")
            print()
            for error in errors:
                print(error)
                print()
        else:
            print("✅ 未发现关键错误")
            print()
        
        if warnings:
            print(f"⚠️  发现 {len(warnings)} 个警告:")
            print()
            for warning in warnings:
                print(warning)
                print()
        else:
            print("✅ 未发现警告")
            print()
        
        # 总结
        print(f"{'='*80}")
        if not errors and not warnings:
            print("✅ 字段命名检查通过！")
        elif not errors:
            print("⚠️  字段命名基本正确，但有一些建议")
        else:
            print("❌ 字段命名存在错误，需要修正")
        print(f"{'='*80}")
        
        return len(errors) == 0


def main():
    """主函数"""
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python field_naming_validator.py <config_file>")
        print()
        print("示例:")
        print("  python field_naming_validator.py converter_config_yinhe.yaml")
        sys.exit(1)
    
    config_path = Path(sys.argv[1])
    
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        sys.exit(1)
    
    validator = FieldNamingValidator(config_path)
    success = validator.print_report()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

