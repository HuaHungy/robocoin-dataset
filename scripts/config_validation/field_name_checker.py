"""
字段命名检查器 - 检查字段命名是否符合标准

命名标准（基于converter_config_realman_rmc_aidal.yaml）：
- 关节角度: xxx_joint_N_rad (N为关节编号，1-7)
- 夹爪: xxx_gripper_open_rad 或 xxx_gripper_open
- 末端位置: xxx_eef_pos_x_m, xxx_eef_pos_y_m, xxx_eef_pos_z_m
- 末端姿态: xxx_eef_rot_euler_x_rad, xxx_eef_rot_euler_y_rad, xxx_eef_rot_euler_z_rad
- 前缀: left_, right_, base_, mobile_
- 单位后缀: _rad (弧度), _m (米), _deg (度, 不推荐)
"""

import logging
import re
from typing import List, Dict, Any, Optional


class FieldNameChecker:
    """字段命名检查器"""
    
    # 命名规范模式
    PATTERNS = {
        'joint': r'^(left_|right_|base_|mobile_)?(\w+_)?joint_\d+_rad$',
        'gripper': r'^(left_|right_)?gripper_(open|close)(_rad)?$',
        'eef_pos': r'^(left_|right_)?eef_pos_[xyz]_m$',
        'eef_rot': r'^(left_|right_)?eef_rot_(euler|quat)_[xyzw]_rad$',
        'arm': r'^(left_|right_)arm_joint_\d+_rad$',
        'camera': r'^(cam|camera)_(left|right|high|front|head|wrist)(_rgb)?$'
    }
    
    # 单位后缀
    UNIT_SUFFIXES = {
        '_rad': '弧度',
        '_m': '米',
        '_deg': '度（不推荐，应使用_rad）',
        '_mm': '毫米（不推荐，应使用_m）',
        '_cm': '厘米（不推荐，应使用_m）'
    }
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def check_field_names(self, names: List[str]) -> Dict[str, Any]:
        """
        检查一组字段名
        
        Args:
            names: 字段名列表
            
        Returns:
            检查报告
        """
        report = {
            'total_fields': len(names),
            'compliant': [],
            'non_compliant': [],
            'warnings': [],
            'suggestions': []
        }
        
        for name in names:
            check_result = self._check_single_field(name)
            
            if check_result['status'] == 'compliant':
                report['compliant'].append(name)
            elif check_result['status'] == 'non_compliant':
                report['non_compliant'].append({
                    'name': name,
                    'issues': check_result['issues'],
                    'suggestion': check_result.get('suggestion')
                })
            elif check_result['status'] == 'warning':
                report['warnings'].append({
                    'name': name,
                    'issues': check_result['issues'],
                    'suggestion': check_result.get('suggestion')
                })
        
        # 生成总体建议
        report['suggestions'] = self._generate_suggestions(report)
        
        return report
    
    def _check_single_field(self, name: str) -> Dict[str, Any]:
        """检查单个字段名"""
        result = {
            'name': name,
            'status': 'unknown',
            'issues': []
        }
        
        # 检查是否匹配任何已知模式
        matched_pattern = None
        for pattern_name, pattern_regex in self.PATTERNS.items():
            if re.match(pattern_regex, name):
                matched_pattern = pattern_name
                result['status'] = 'compliant'
                result['pattern'] = pattern_name
                break
        
        if matched_pattern:
            return result
        
        # 未匹配已知模式，进行详细检查
        result['status'] = 'non_compliant'
        
        # 检查单位后缀
        has_unit = False
        used_unit = None
        for unit, unit_name in self.UNIT_SUFFIXES.items():
            if name.endswith(unit):
                has_unit = True
                used_unit = unit
                if unit in ['_deg', '_mm', '_cm']:
                    result['status'] = 'warning'
                    result['issues'].append(f"使用了不推荐的单位: {unit_name}")
                break
        
        if not has_unit:
            # 判断是否应该有单位
            if any(keyword in name.lower() for keyword in ['joint', 'angle', 'rot', 'euler', 'quat']):
                result['issues'].append("缺少角度单位后缀（应为_rad）")
                result['suggestion'] = name + '_rad'
            elif any(keyword in name.lower() for keyword in ['pos', 'position', 'x', 'y', 'z', 'distance']):
                # 但排除一些不需要单位的情况
                if not any(keyword in name.lower() for keyword in ['image', 'cam', 'pixel']):
                    result['issues'].append("缺少长度单位后缀（应为_m）")
                    result['suggestion'] = name + '_m'
        
        # 检查前缀
        if any(keyword in name.lower() for keyword in ['left', 'right']):
            if not name.startswith('left_') and not name.startswith('right_'):
                result['issues'].append("left/right应作为前缀，用下划线分隔")
                # 尝试生成建议
                if 'left' in name.lower():
                    suggested = 'left_' + name.replace('left', '').replace('Left', '').strip('_')
                    result['suggestion'] = suggested
                elif 'right' in name.lower():
                    suggested = 'right_' + name.replace('right', '').replace('Right', '').strip('_')
                    result['suggestion'] = suggested
        
        # 检查关节命名
        if 'joint' in name.lower():
            # 应该符合 xxx_joint_N_rad格式
            if not re.search(r'joint_\d+', name):
                result['issues'].append("关节应使用joint_N格式，N为关节编号")
            if not name.endswith('_rad'):
                result['issues'].append("关节角度应使用_rad后缀")
        
        # 检查夹爪命名
        if 'gripper' in name.lower():
            if not any(keyword in name for keyword in ['open', 'close', 'width']):
                result['issues'].append("夹爪字段应包含open/close/width等描述")
        
        # 检查末端执行器命名
        if 'eef' in name.lower() or 'end_effector' in name.lower():
            if 'pos' in name.lower():
                if not re.search(r'_[xyz]_m$', name):
                    result['issues'].append("末端位置应使用xxx_eef_pos_[xyz]_m格式")
            elif 'rot' in name.lower() or 'euler' in name.lower():
                if not re.search(r'_[xyz]_rad$', name):
                    result['issues'].append("末端姿态应使用xxx_eef_rot_euler_[xyz]_rad格式")
        
        # 如果没有发现任何问题，可能只是命名风格不同
        if not result['issues']:
            result['status'] = 'compliant'
            result['note'] = '未匹配标准模式，但未发现明显问题'
        
        return result
    
    def _generate_suggestions(self, report: Dict[str, Any]) -> List[str]:
        """生成总体建议"""
        suggestions = []
        
        if report['non_compliant']:
            suggestions.append(f"有 {len(report['non_compliant'])} 个字段名不符合命名规范")
        
        if report['warnings']:
            suggestions.append(f"有 {len(report['warnings'])} 个字段名使用了不推荐的命名方式")
        
        # 统计缺少单位的字段
        missing_rad = sum(1 for item in report['non_compliant'] 
                         if any('_rad' in issue for issue in item['issues']))
        if missing_rad > 0:
            suggestions.append(f"有 {missing_rad} 个字段缺少_rad单位后缀")
        
        missing_m = sum(1 for item in report['non_compliant'] 
                       if any('_m' in issue for issue in item['issues']))
        if missing_m > 0:
            suggestions.append(f"有 {missing_m} 个字段缺少_m单位后缀")
        
        return suggestions
    
    def generate_readable_report(self, report: Dict[str, Any]) -> str:
        """生成可读的检查报告"""
        lines = []
        lines.append("=" * 70)
        lines.append("字段命名检查报告")
        lines.append("=" * 70)
        
        lines.append(f"\n总字段数: {report['total_fields']}")
        lines.append(f"符合规范: {len(report['compliant'])} ({len(report['compliant'])/report['total_fields']*100:.1f}%)")
        lines.append(f"不符合规范: {len(report['non_compliant'])}")
        lines.append(f"警告: {len(report['warnings'])}")
        
        # 不符合规范的字段
        if report['non_compliant']:
            lines.append("\n" + "=" * 70)
            lines.append("不符合规范的字段")
            lines.append("=" * 70)
            
            for item in report['non_compliant']:
                lines.append(f"\n✗ {item['name']}")
                for issue in item['issues']:
                    lines.append(f"    - {issue}")
                if item.get('suggestion'):
                    lines.append(f"    💡 建议: {item['suggestion']}")
        
        # 警告
        if report['warnings']:
            lines.append("\n" + "=" * 70)
            lines.append("警告")
            lines.append("=" * 70)
            
            for item in report['warnings']:
                lines.append(f"\n⚠ {item['name']}")
                for issue in item['issues']:
                    lines.append(f"    - {issue}")
                if item.get('suggestion'):
                    lines.append(f"    💡 建议: {item['suggestion']}")
        
        # 总体建议
        if report['suggestions']:
            lines.append("\n" + "=" * 70)
            lines.append("总体建议")
            lines.append("=" * 70)
            for suggestion in report['suggestions']:
                lines.append(f"  • {suggestion}")
        
        lines.append("\n" + "=" * 70)
        lines.append("命名规范参考（基于realman_rmc_aidal）")
        lines.append("=" * 70)
        lines.append("  • 关节: {left/right}_arm_joint_N_rad")
        lines.append("  • 夹爪: {left/right}_gripper_open_rad")
        lines.append("  • 末端位置: {left/right}_eef_pos_{x/y/z}_m")
        lines.append("  • 末端姿态: {left/right}_eef_rot_euler_{x/y/z}_rad")
        lines.append("  • 摄像头: cam_{high/left/right/wrist}_rgb")
        lines.append("=" * 70)
        
        return "\n".join(lines)
    
    def check_config_field_names(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        检查配置文件中的所有字段名
        
        Args:
            config: converter配置
            
        Returns:
            检查报告
        """
        all_names = []
        
        # 提取observations中的names
        if 'features' in config and 'observation' in config['features']:
            obs_config = config['features']['observation']
            
            # state names
            if 'state' in obs_config and 'sub_state' in obs_config['state']:
                for sub_state in obs_config['state']['sub_state']:
                    all_names.extend(sub_state.get('names', []))
        
        # 提取actions中的names
        if 'features' in config and 'action' in config['features']:
            action_config = config['features']['action']
            if 'sub_action' in action_config:
                for sub_action in action_config['sub_action']:
                    all_names.extend(sub_action.get('names', []))
        
        if not all_names:
            return {
                'total_fields': 0,
                'compliant': [],
                'non_compliant': [],
                'warnings': [],
                'suggestions': ['未找到任何字段名']
            }
        
        return self.check_field_names(all_names)


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    checker = FieldNameChecker()
    
    # 测试一些字段名
    test_names = [
        'right_arm_joint_1_rad',  # ✓ 符合规范
        'left_gripper_open',       # ✓ 符合规范
        'right_eef_pos_x_m',       # ✓ 符合规范
        'left_eef_rot_euler_z_rad', # ✓ 符合规范
        'joint_1',                 # ✗ 缺少_rad
        'gripper',                 # ✗ 缺少open/close
        'eef_pos_x',               # ✗ 缺少_m
        'rightArmJoint1',          # ✗ 命名风格不对
    ]
    
    report = checker.check_field_names(test_names)
    print(checker.generate_readable_report(report))

