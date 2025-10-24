#!/usr/bin/env python3
"""Schema对比器 - 详细对比配置vs实际数据结构

功能：
- 对比配置文件中定义的schema与实际数据的schema
- 识别不匹配的字段、维度、数据类型
- 高亮显示差异
- 提供自动修复建议
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np


class SchemaComparator:
    """Schema对比器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def compare_schemas(
        self,
        config_schema: Dict[str, Any],
        actual_schema: Dict[str, Any],
        strict_mode: bool = False
    ) -> Dict[str, Any]:
        """
        详细对比配置schema和实际schema
        
        Args:
            config_schema: 从配置文件提取的schema
            actual_schema: 从实际数据提取的schema
            strict_mode: 严格模式，要求完全匹配
        
        Returns:
            对比结果字典，包含差异、建议等
        """
        comparison = {
            'status': 'unknown',  # 'match', 'mismatch', 'partial_match'
            'observation': {
                'state': self._compare_state(
                    config_schema.get('observation', {}).get('state', {}),
                    actual_schema.get('observations', {}).get('state', {})
                ),
                'images': self._compare_images(
                    config_schema.get('observation', {}).get('images', {}),
                    actual_schema.get('observations', {}).get('images', {})
                )
            },
            'action': self._compare_action(
                config_schema.get('action', {}),
                actual_schema.get('actions', {})
            ),
            'summary': {
                'total_issues': 0,
                'critical_issues': 0,
                'warnings': 0,
                'suggestions': []
            }
        }
        
        # 统计问题数量
        comparison = self._calculate_summary(comparison, strict_mode)
        
        # 确定总体状态
        if comparison['summary']['critical_issues'] == 0:
            if comparison['summary']['warnings'] == 0:
                comparison['status'] = 'match'
            else:
                comparison['status'] = 'partial_match'
        else:
            comparison['status'] = 'mismatch'
        
        return comparison
    
    def _compare_state(
        self,
        config_state: Dict[str, Any],
        actual_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """对比state schema"""
        result = {
            'status': 'unknown',
            'differences': [],
            'suggestions': []
        }
        
        if not config_state and not actual_state:
            result['status'] = 'match'
            return result
        
        if not config_state:
            result['differences'].append({
                'type': 'missing_config',
                'severity': 'warning',
                'message': 'Configuration has no state definition, but actual data has state',
                'actual': actual_state
            })
            result['suggestions'].append({
                'action': 'add_state_config',
                'details': 'Add state configuration to match actual data',
                'example': self._generate_state_config_example(actual_state)
            })
            result['status'] = 'mismatch'
            return result
        
        if not actual_state:
            result['differences'].append({
                'type': 'missing_actual',
                'severity': 'critical',
                'message': 'Configuration expects state, but actual data has no state',
                'config': config_state
            })
            result['suggestions'].append({
                'action': 'remove_state_config',
                'details': 'Remove state configuration or check data source'
            })
            result['status'] = 'mismatch'
            return result
        
        # 对比维度
        config_shape = config_state.get('shape') or config_state.get('expected_shape')
        actual_shape = actual_state.get('shape')
        
        if config_shape and actual_shape:
            if not self._shapes_match(config_shape, actual_shape):
                result['differences'].append({
                    'type': 'shape_mismatch',
                    'severity': 'critical',
                    'field': 'state',
                    'message': f'State shape mismatch',
                    'config_value': config_shape,
                    'actual_value': actual_shape
                })
                result['suggestions'].append({
                    'action': 'update_shape',
                    'field': 'state',
                    'from': config_shape,
                    'to': actual_shape,
                    'config_path': 'features.observation.state'
                })
        
        # 对比数据类型
        config_dtype = config_state.get('dtype') or config_state.get('expected_dtype')
        actual_dtype = actual_state.get('dtype')
        
        if config_dtype and actual_dtype:
            if not self._dtypes_match(config_dtype, actual_dtype):
                severity = 'warning' if self._dtypes_compatible(config_dtype, actual_dtype) else 'critical'
                result['differences'].append({
                    'type': 'dtype_mismatch',
                    'severity': severity,
                    'field': 'state',
                    'message': f'State dtype mismatch',
                    'config_value': config_dtype,
                    'actual_value': actual_dtype
                })
                if severity == 'critical':
                    result['suggestions'].append({
                        'action': 'update_dtype',
                        'field': 'state',
                        'from': config_dtype,
                        'to': actual_dtype
                    })
        
        # 对比sub_state字段（如果有）
        if 'sub_states' in config_state and 'sub_states' in actual_state:
            sub_state_diff = self._compare_sub_states(
                config_state['sub_states'],
                actual_state['sub_states']
            )
            if sub_state_diff:
                result['differences'].extend(sub_state_diff)
        
        # 确定状态
        critical_count = sum(1 for d in result['differences'] if d['severity'] == 'critical')
        if critical_count > 0:
            result['status'] = 'mismatch'
        elif len(result['differences']) > 0:
            result['status'] = 'partial_match'
        else:
            result['status'] = 'match'
        
        return result
    
    def _compare_images(
        self,
        config_images: Dict[str, Any],
        actual_images: Dict[str, Any]
    ) -> Dict[str, Any]:
        """对比images schema"""
        result = {
            'status': 'unknown',
            'differences': [],
            'suggestions': [],
            'camera_comparison': {}
        }
        
        if not config_images and not actual_images:
            result['status'] = 'match'
            return result
        
        # 获取相机列表
        config_cameras = set(config_images.keys()) if config_images else set()
        actual_cameras = set(actual_images.keys()) if actual_images else set()
        
        # 检查缺失的相机
        missing_in_actual = config_cameras - actual_cameras
        missing_in_config = actual_cameras - config_cameras
        
        for cam in missing_in_actual:
            result['differences'].append({
                'type': 'missing_camera',
                'severity': 'critical',
                'camera': cam,
                'message': f'Camera {cam} is in config but missing in actual data'
            })
            result['suggestions'].append({
                'action': 'remove_camera',
                'camera': cam,
                'details': f'Remove camera {cam} from configuration'
            })
        
        for cam in missing_in_config:
            result['differences'].append({
                'type': 'extra_camera',
                'severity': 'warning',
                'camera': cam,
                'message': f'Camera {cam} exists in actual data but not in config'
            })
            result['suggestions'].append({
                'action': 'add_camera',
                'camera': cam,
                'details': f'Add camera {cam} to configuration',
                'example': self._generate_camera_config_example(cam, actual_images[cam])
            })
        
        # 对比共同存在的相机
        common_cameras = config_cameras & actual_cameras
        for cam in common_cameras:
            cam_comparison = self._compare_camera(
                cam,
                config_images[cam],
                actual_images[cam]
            )
            result['camera_comparison'][cam] = cam_comparison
            if cam_comparison['differences']:
                result['differences'].extend(cam_comparison['differences'])
            if cam_comparison['suggestions']:
                result['suggestions'].extend(cam_comparison['suggestions'])
        
        # 确定状态
        critical_count = sum(1 for d in result['differences'] if d['severity'] == 'critical')
        if critical_count > 0:
            result['status'] = 'mismatch'
        elif len(result['differences']) > 0:
            result['status'] = 'partial_match'
        else:
            result['status'] = 'match'
        
        return result
    
    def _compare_camera(
        self,
        camera_name: str,
        config_cam: Dict[str, Any],
        actual_cam: Dict[str, Any]
    ) -> Dict[str, Any]:
        """对比单个相机的schema"""
        result = {
            'status': 'match',
            'differences': [],
            'suggestions': []
        }
        
        # 对比图像尺寸
        config_shape = config_cam.get('shape') or config_cam.get('expected_shape')
        actual_shape = actual_cam.get('shape')
        
        if config_shape and actual_shape:
            if not self._shapes_match(config_shape, actual_shape):
                result['differences'].append({
                    'type': 'image_shape_mismatch',
                    'severity': 'warning',  # 图像尺寸不匹配通常是warning
                    'camera': camera_name,
                    'message': f'Image shape mismatch for camera {camera_name}',
                    'config_value': config_shape,
                    'actual_value': actual_shape
                })
                result['suggestions'].append({
                    'action': 'update_camera_shape',
                    'camera': camera_name,
                    'from': config_shape,
                    'to': actual_shape
                })
        
        # 对比数据类型
        config_dtype = config_cam.get('dtype') or config_cam.get('expected_dtype')
        actual_dtype = actual_cam.get('dtype')
        
        if config_dtype and actual_dtype:
            if not self._dtypes_match(config_dtype, actual_dtype):
                result['differences'].append({
                    'type': 'image_dtype_mismatch',
                    'severity': 'warning',
                    'camera': camera_name,
                    'message': f'Image dtype mismatch for camera {camera_name}',
                    'config_value': config_dtype,
                    'actual_value': actual_dtype
                })
        
        if result['differences']:
            result['status'] = 'mismatch'
        
        return result
    
    def _compare_action(
        self,
        config_action: Dict[str, Any],
        actual_action: Dict[str, Any]
    ) -> Dict[str, Any]:
        """对比action schema"""
        result = {
            'status': 'unknown',
            'differences': [],
            'suggestions': []
        }
        
        if not config_action and not actual_action:
            result['status'] = 'match'
            return result
        
        if not config_action:
            result['differences'].append({
                'type': 'missing_config',
                'severity': 'critical',
                'message': 'Configuration has no action definition, but actual data has action'
            })
            result['status'] = 'mismatch'
            return result
        
        if not actual_action:
            result['differences'].append({
                'type': 'missing_actual',
                'severity': 'critical',
                'message': 'Configuration expects action, but actual data has no action'
            })
            result['status'] = 'mismatch'
            return result
        
        # 对比维度
        config_shape = config_action.get('shape') or config_action.get('expected_shape')
        actual_shape = actual_action.get('shape')
        
        if config_shape and actual_shape:
            if not self._shapes_match(config_shape, actual_shape):
                result['differences'].append({
                    'type': 'shape_mismatch',
                    'severity': 'critical',
                    'field': 'action',
                    'message': f'Action shape mismatch',
                    'config_value': config_shape,
                    'actual_value': actual_shape
                })
                result['suggestions'].append({
                    'action': 'update_shape',
                    'field': 'action',
                    'from': config_shape,
                    'to': actual_shape,
                    'config_path': 'features.action'
                })
        
        # 对比数据类型
        config_dtype = config_action.get('dtype') or config_action.get('expected_dtype')
        actual_dtype = actual_action.get('dtype')
        
        if config_dtype and actual_dtype:
            if not self._dtypes_match(config_dtype, actual_dtype):
                severity = 'warning' if self._dtypes_compatible(config_dtype, actual_dtype) else 'critical'
                result['differences'].append({
                    'type': 'dtype_mismatch',
                    'severity': severity,
                    'field': 'action',
                    'message': f'Action dtype mismatch',
                    'config_value': config_dtype,
                    'actual_value': actual_dtype
                })
        
        # 确定状态
        critical_count = sum(1 for d in result['differences'] if d['severity'] == 'critical')
        if critical_count > 0:
            result['status'] = 'mismatch'
        elif len(result['differences']) > 0:
            result['status'] = 'partial_match'
        else:
            result['status'] = 'match'
        
        return result
    
    def _compare_sub_states(
        self,
        config_sub_states: List[Dict[str, Any]],
        actual_sub_states: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """对比sub_state列表"""
        differences = []
        
        # 简化实现：对比数量和名称
        config_names = set(s.get('name', '') for s in config_sub_states)
        actual_names = set(s.get('name', '') for s in actual_sub_states)
        
        missing_in_actual = config_names - actual_names
        missing_in_config = actual_names - config_names
        
        for name in missing_in_actual:
            differences.append({
                'type': 'missing_sub_state',
                'severity': 'critical',
                'field': name,
                'message': f'Sub-state {name} is in config but missing in actual data'
            })
        
        for name in missing_in_config:
            differences.append({
                'type': 'extra_sub_state',
                'severity': 'warning',
                'field': name,
                'message': f'Sub-state {name} exists in actual data but not in config'
            })
        
        return differences
    
    def _shapes_match(self, shape1: Any, shape2: Any) -> bool:
        """判断两个shape是否匹配"""
        if shape1 == shape2:
            return True
        
        # 尝试转换为tuple比较
        try:
            s1 = tuple(shape1) if isinstance(shape1, (list, tuple)) else (shape1,)
            s2 = tuple(shape2) if isinstance(shape2, (list, tuple)) else (shape2,)
            return s1 == s2
        except Exception:
            return False
    
    def _dtypes_match(self, dtype1: str, dtype2: str) -> bool:
        """判断两个dtype是否匹配"""
        # 完全匹配
        if dtype1 == dtype2:
            return True
        
        # 标准化dtype字符串
        dtype1_norm = self._normalize_dtype(dtype1)
        dtype2_norm = self._normalize_dtype(dtype2)
        
        return dtype1_norm == dtype2_norm
    
    def _dtypes_compatible(self, dtype1: str, dtype2: str) -> bool:
        """判断两个dtype是否兼容（可以转换）"""
        # 例如：float64可以转换为float32，int64可以转换为int32
        compatible_groups = [
            {'float16', 'float32', 'float64'},
            {'int8', 'int16', 'int32', 'int64'},
            {'uint8', 'uint16', 'uint32', 'uint64'}
        ]
        
        dtype1_norm = self._normalize_dtype(dtype1)
        dtype2_norm = self._normalize_dtype(dtype2)
        
        for group in compatible_groups:
            if dtype1_norm in group and dtype2_norm in group:
                return True
        
        return False
    
    def _normalize_dtype(self, dtype: str) -> str:
        """标准化dtype字符串"""
        dtype_str = str(dtype).lower()
        
        # 移除numpy前缀
        dtype_str = dtype_str.replace('numpy.', '').replace('np.', '')
        
        # 标准化一些常见的别名
        dtype_map = {
            'float': 'float32',
            'int': 'int32',
            'uint': 'uint32',
            'double': 'float64',
            'long': 'int64'
        }
        
        return dtype_map.get(dtype_str, dtype_str)
    
    def _calculate_summary(
        self,
        comparison: Dict[str, Any],
        strict_mode: bool
    ) -> Dict[str, Any]:
        """计算对比摘要"""
        total_issues = 0
        critical_issues = 0
        warnings = 0
        all_suggestions = []
        
        # 收集所有differences和suggestions
        for component in ['observation', 'action']:
            if component == 'observation':
                for sub_component in ['state', 'images']:
                    sub_data = comparison[component][sub_component]
                    diffs = sub_data.get('differences', [])
                    total_issues += len(diffs)
                    critical_issues += sum(1 for d in diffs if d.get('severity') == 'critical')
                    warnings += sum(1 for d in diffs if d.get('severity') == 'warning')
                    all_suggestions.extend(sub_data.get('suggestions', []))
            else:
                sub_data = comparison[component]
                diffs = sub_data.get('differences', [])
                total_issues += len(diffs)
                critical_issues += sum(1 for d in diffs if d.get('severity') == 'critical')
                warnings += sum(1 for d in diffs if d.get('severity') == 'warning')
                all_suggestions.extend(sub_data.get('suggestions', []))
        
        # 在strict模式下，warnings也算作critical
        if strict_mode:
            critical_issues += warnings
            warnings = 0
        
        comparison['summary'] = {
            'total_issues': total_issues,
            'critical_issues': critical_issues,
            'warnings': warnings,
            'suggestions': all_suggestions
        }
        
        return comparison
    
    def _generate_state_config_example(self, actual_state: Dict[str, Any]) -> Dict[str, Any]:
        """生成state配置示例"""
        return {
            'sub_state': [
                {
                    'names': ['state_dim_' + str(i) for i in range(actual_state.get('shape', [0])[0])],
                    'args': {
                        'h5_path': '/observation/state',  # 需要根据实际格式调整
                        'range_from': 0,
                        'range_to': actual_state.get('shape', [0])[0]
                    }
                }
            ]
        }
    
    def _generate_camera_config_example(self, camera_name: str, actual_cam: Dict[str, Any]) -> Dict[str, Any]:
        """生成相机配置示例"""
        return {
            'cam_name': camera_name,
            'args': {
                'video_path': f'{{ep_idx}}_{camera_name}.mp4',  # 需要根据实际格式调整
                # 或者
                # 'image_dir': f'camera/{camera_name}',
                # 'image_pattern': 'frame_{:04d}.jpg'
            }
        }
    
    def generate_fix_script(
        self,
        comparison: Dict[str, Any],
        config_file: Path
    ) -> str:
        """
        根据对比结果生成修复脚本
        
        Args:
            comparison: 对比结果
            config_file: 配置文件路径
        
        Returns:
            Python脚本代码
        """
        script_lines = [
            "#!/usr/bin/env python3",
            "\"\"\"自动生成的配置修复脚本\"\"\"",
            "",
            "import yaml",
            "from pathlib import Path",
            "",
            f"config_file = Path('{config_file}')",
            "",
            "# 读取配置文件",
            "with open(config_file) as f:",
            "    config = yaml.safe_load(f)",
            "",
            "# 应用修复",
            ""
        ]
        
        # 根据suggestions生成修复代码
        suggestions = comparison['summary'].get('suggestions', [])
        
        for i, suggestion in enumerate(suggestions):
            action = suggestion.get('action')
            
            if action == 'update_shape':
                field = suggestion.get('field')
                to_shape = suggestion.get('to')
                config_path = suggestion.get('config_path', '')
                script_lines.extend([
                    f"# Fix {i+1}: Update {field} shape",
                    f"# Expected shape: {to_shape}",
                    f"# Uncomment and adjust the following line:",
                    f"# config['{config_path}']['shape'] = {to_shape}",
                    ""
                ])
            
            elif action == 'remove_camera':
                camera = suggestion.get('camera')
                script_lines.extend([
                    f"# Fix {i+1}: Remove camera {camera}",
                    f"# Uncomment the following lines:",
                    f"# cameras = config['features']['observation']['image']",
                    f"# config['features']['observation']['image'] = [c for c in cameras if c['cam_name'] != '{camera}']",
                    ""
                ])
            
            elif action == 'add_camera':
                camera = suggestion.get('camera')
                example = suggestion.get('example', {})
                script_lines.extend([
                    f"# Fix {i+1}: Add camera {camera}",
                    f"# Uncomment and adjust the following lines:",
                    f"# new_camera = {example}",
                    f"# config['features']['observation']['image'].append(new_camera)",
                    ""
                ])
        
        script_lines.extend([
            "# 保存修改后的配置",
            "# with open(config_file, 'w') as f:",
            "#     yaml.dump(config, f, default_flow_style=False, sort_keys=False)",
            "",
            "print('Please review and uncomment the fixes above, then run this script again.')"
        ])
        
        return '\n'.join(script_lines)
    
    def print_comparison_report(self, comparison: Dict[str, Any], verbose: bool = True):
        """
        打印格式化的对比报告
        
        Args:
            comparison: 对比结果
            verbose: 是否打印详细信息
        """
        print("\n" + "="*70)
        print("Schema Comparison Report")
        print("="*70)
        
        summary = comparison['summary']
        status = comparison['status']
        
        # 状态图标
        status_icon = {
            'match': '✅',
            'partial_match': '⚠️ ',
            'mismatch': '❌'
        }
        
        print(f"\n{status_icon.get(status, '❓')} Overall Status: {status.upper()}")
        print(f"\n📊 Summary:")
        print(f"   Total Issues: {summary['total_issues']}")
        print(f"   Critical Issues: {summary['critical_issues']}")
        print(f"   Warnings: {summary['warnings']}")
        
        if not verbose:
            return
        
        # 打印详细差异
        print(f"\n🔍 Detailed Differences:")
        
        for component in ['observation', 'action']:
            if component == 'observation':
                print(f"\n  📦 Observation:")
                for sub_component in ['state', 'images']:
                    self._print_component_differences(
                        sub_component,
                        comparison[component][sub_component],
                        indent=4
                    )
            else:
                print(f"\n  🎯 Action:")
                self._print_component_differences(
                    'action',
                    comparison[component],
                    indent=4
                )
        
        # 打印修复建议
        if summary['suggestions']:
            print(f"\n💡 Suggestions for Fixing:")
            for i, suggestion in enumerate(summary['suggestions'], 1):
                print(f"\n  {i}. {suggestion.get('action', 'unknown')}:")
                for key, value in suggestion.items():
                    if key != 'action' and key != 'example':
                        print(f"     {key}: {value}")
                if 'example' in suggestion:
                    print(f"     Example configuration:")
                    import json
                    print(f"     {json.dumps(suggestion['example'], indent=6)}")
        
        print("\n" + "="*70 + "\n")
    
    def _print_component_differences(
        self,
        component_name: str,
        component_data: Dict[str, Any],
        indent: int = 0
    ):
        """打印组件的差异信息"""
        spaces = " " * indent
        status = component_data.get('status', 'unknown')
        status_icon = {'match': '✅', 'partial_match': '⚠️ ', 'mismatch': '❌', 'unknown': '❓'}
        
        print(f"{spaces}{status_icon.get(status, '❓')} {component_name.title()}: {status}")
        
        differences = component_data.get('differences', [])
        if differences:
            for diff in differences:
                severity_icon = {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}
                severity = diff.get('severity', 'info')
                print(f"{spaces}  {severity_icon.get(severity, '⚪')} [{severity.upper()}] {diff.get('message', 'No message')}")
                if 'config_value' in diff:
                    print(f"{spaces}    Config: {diff['config_value']}")
                if 'actual_value' in diff:
                    print(f"{spaces}    Actual: {diff['actual_value']}")

