"""
配置对比器 - 对比实际schema与YAML配置文件

功能：
- 加载converter config YAML
- 对比配置的h5_path是否存在于实际数据中
- 对比维度是否匹配（range_from/range_to）
- 检查缺失的字段
- 检查多余的配置
- 生成差异报告
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


class ConfigComparator:
    """配置对比器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def load_config(self, config_path: Path) -> Dict[str, Any]:
        """加载converter配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            self.logger.error(f"加载配置文件失败 {config_path}: {e}")
            return {}
    
    def compare(
        self,
        schema: Dict[str, Any],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        对比schema与配置
        
        Args:
            schema: 实际数据的schema
            config: converter配置
            
        Returns:
            差异报告
        """
        report = {
            'observations': {
                'images': [],
                'state': [],
                'missing_configs': [],
                'missing_fields': [],
                'dimension_mismatches': []
            },
            'actions': {
                'missing_configs': [],
                'missing_fields': [],
                'dimension_mismatches': []
            },
            'summary': {
                'total_errors': 0,
                'total_warnings': 0
            }
        }
        
        # 对比observations
        if 'features' in config and 'observation' in config['features']:
            obs_config = config['features']['observation']
            
            # 对比images
            if 'images' in obs_config:
                report['observations']['images'] = self._compare_images(
                    schema.get('observations', {}).get('images', {}),
                    obs_config['images']
                )
            
            # 对比state
            if 'state' in obs_config:
                state_comparison = self._compare_state(
                    schema.get('observations', {}),
                    obs_config['state']
                )
                report['observations']['state'] = state_comparison.get('details', [])
                report['observations']['missing_configs'] = state_comparison.get('missing_configs', [])
                report['observations']['missing_fields'] = state_comparison.get('missing_fields', [])
                report['observations']['dimension_mismatches'] = state_comparison.get('dimension_mismatches', [])
        
        # 对比actions
        if 'features' in config and 'action' in config['features']:
            action_config = config['features']['action']
            action_comparison = self._compare_actions(
                schema.get('actions', {}),
                action_config
            )
            report['actions'] = action_comparison
        
        # 计算错误和警告总数
        report['summary']['total_errors'] = sum([
            len(report['observations']['missing_fields']),
            len(report['observations']['dimension_mismatches']),
            len(report['actions']['missing_fields']),
            len(report['actions']['dimension_mismatches'])
        ])
        
        report['summary']['total_warnings'] = sum([
            len(report['observations']['missing_configs']),
            len(report['actions']['missing_configs'])
        ])
        
        return report
    
    def _compare_images(
        self,
        schema_images: Dict[str, Any],
        config_images: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """对比images配置"""
        results = []
        
        for img_config in config_images:
            cam_name = img_config.get('cam_name', 'unknown')
            h5_path = img_config.get('args', {}).get('h5_path', '')
            
            result = {
                'cam_name': cam_name,
                'configured_h5_path': h5_path,
                'status': 'ok',
                'issues': []
            }
            
            # 检查h5_path是否存在于schema中
            if cam_name not in schema_images:
                # 尝试通过h5_path查找
                found = False
                for schema_cam_name, schema_cam_info in schema_images.items():
                    if h5_path in schema_cam_info.get('h5_path', ''):
                        result['found_as'] = schema_cam_name
                        result['schema_info'] = schema_cam_info
                        found = True
                        break
                
                if not found:
                    result['status'] = 'error'
                    result['issues'].append(f"配置的摄像头 '{cam_name}' 或h5_path '{h5_path}' 未在数据中找到")
            else:
                result['schema_info'] = schema_images[cam_name]
                # 检查shape是否匹配（如果配置中有shape）
                if 'shape' in result['schema_info']:
                    result['actual_shape'] = result['schema_info']['shape']
            
            results.append(result)
        
        # 检查schema中有但配置中没有的images
        configured_cams = {img.get('cam_name') for img in config_images}
        for schema_cam in schema_images.keys():
            if schema_cam not in configured_cams:
                results.append({
                    'cam_name': schema_cam,
                    'status': 'warning',
                    'issues': [f"数据中存在摄像头 '{schema_cam}'，但配置中未定义"]
                })
        
        return results
    
    def _compare_state(
        self,
        schema_obs: Dict[str, Any],
        config_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """对比state配置"""
        result = {
            'details': [],
            'missing_configs': [],
            'missing_fields': [],
            'dimension_mismatches': []
        }
        
        # 获取配置的sub_states
        sub_states = config_state.get('sub_state', [])
        
        for sub_state in sub_states:
            names = sub_state.get('names', [])
            args = sub_state.get('args', {})
            h5_path = args.get('h5_path', '')
            range_from = args.get('range_from')
            range_to = args.get('range_to')
            
            detail = {
                'names': names,
                'h5_path': h5_path,
                'configured_range': f'[{range_from}:{range_to}]' if range_from is not None else None,
                'status': 'ok',
                'issues': []
            }
            
            # 检查h5_path是否存在
            h5_path_parts = h5_path.split('/')
            found = False
            actual_shape = None
            
            # 在schema中查找对应的字段
            for category in ['qpos', 'qvel', 'state', 'other']:
                if category in schema_obs:
                    for field_name, field_info in schema_obs[category].items():
                        if h5_path in field_info.get('h5_path', ''):
                            found = True
                            actual_shape = field_info.get('shape')
                            detail['actual_shape'] = actual_shape
                            break
                if found:
                    break
            
            if not found:
                detail['status'] = 'error'
                detail['issues'].append(f"h5_path '{h5_path}' 未在数据中找到")
                result['missing_fields'].append({
                    'h5_path': h5_path,
                    'names': names
                })
            else:
                # 🆕 检查数据质量警告
                for category in ['qpos', 'qvel', 'state', 'other']:
                    if category in schema_obs:
                        for field_name, field_info in schema_obs[category].items():
                            if h5_path in field_info.get('h5_path', ''):
                                if field_info.get('warning'):
                                    warning_type = field_info['warning']
                                    if warning_type == 'ALL_ZERO':
                                        detail['status'] = 'warning'
                                        detail['issues'].append(
                                            f"⚠️ 数据质量问题: 所有值都为0（可能是传感器未连接或数据采集失败）"
                                        )
                                    elif warning_type == 'CONSTANT':
                                        detail['status'] = 'warning'
                                        constant_val = field_info.get('constant_value', 0)
                                        detail['issues'].append(
                                            f"⚠️ 数据质量问题: 所有值都是常量 {constant_val}（可能是传感器故障）"
                                        )
                                    elif warning_type == 'VERY_SMALL_RANGE':
                                        detail['status'] = 'warning'
                                        detail['issues'].append(
                                            f"⚠️ 数据质量问题: 数据变化范围极小（可能只是噪声）"
                                        )
                                break
                

                # 检查维度是否匹配
                if range_from is not None and range_to is not None and actual_shape:
                    expected_dim = range_to - range_from
                    num_names = len(names)
                    
                    if expected_dim != num_names:
                        detail['status'] = 'warning'
                        detail['issues'].append(
                            f"维度可能不匹配: 配置range [{range_from}:{range_to}]={expected_dim}个元素, "
                            f"但names有{num_names}个"
                        )
                    
                    # 检查实际数据的shape
                    if len(actual_shape) > 0:
                        actual_dim = actual_shape[-1]  # 最后一个维度
                        if range_to > actual_dim:
                            detail['status'] = 'error'
                            detail['issues'].append(
                                f"维度越界: 配置要求到索引{range_to}, 但实际数据只有{actual_dim}个元素"
                            )
                            result['dimension_mismatches'].append({
                                'h5_path': h5_path,
                                'configured_range': [range_from, range_to],
                                'actual_dim': actual_dim
                            })
            
            result['details'].append(detail)
        
        return result
    
    def _compare_actions(
        self,
        schema_actions: Dict[str, Any],
        config_actions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """对比actions配置"""
        result = {
            'missing_configs': [],
            'missing_fields': [],
            'dimension_mismatches': [],
            'details': []
        }
        
        # 获取配置的sub_actions
        sub_actions = config_actions.get('sub_action', [])
        
        for sub_action in sub_actions:
            names = sub_action.get('names', [])
            args = sub_action.get('args', {})
            h5_path = args.get('h5_path', '')
            range_from = args.get('range_from')
            range_to = args.get('range_to')
            
            detail = {
                'names': names,
                'h5_path': h5_path,
                'configured_range': f'[{range_from}:{range_to}]' if range_from is not None else None,
                'status': 'ok',
                'issues': []
            }
            
            # 检查h5_path是否存在于actions schema中
            found = False
            actual_shape = None
            
            if isinstance(schema_actions, dict):
                # actions是一个字典，包含多个字段
                for action_name, action_info in schema_actions.items():
                    if h5_path in action_info.get('h5_path', ''):
                        found = True
                        actual_shape = action_info.get('shape')
                        detail['actual_shape'] = actual_shape
                        break
            else:
                # actions是单个dataset
                if 'h5_path' in schema_actions and h5_path in schema_actions['h5_path']:
                    found = True
                    actual_shape = schema_actions.get('shape')
                    detail['actual_shape'] = actual_shape
            
            if not found:
                detail['status'] = 'error'
                detail['issues'].append(f"h5_path '{h5_path}' 未在actions中找到")
                result['missing_fields'].append({
                    'h5_path': h5_path,
                    'names': names
                })
            else:
                # 🆕 检查数据质量警告（actions）
                if isinstance(schema_actions, dict):
                    for action_name, action_info in schema_actions.items():
                        if h5_path in action_info.get('h5_path', '') and action_info.get('warning'):
                            warning_type = action_info['warning']
                            if warning_type == 'ALL_ZERO':
                                detail['status'] = 'warning'
                                detail['issues'].append(
                                    f"⚠️ 数据质量问题: 所有action值都为0（可能数据有问题）"
                                )
                            elif warning_type == 'CONSTANT':
                                detail['status'] = 'warning'
                                detail['issues'].append(
                                    f"⚠️ 数据质量问题: Action值为常量（可能数据有问题）"
                                )
                else:
                    if schema_actions.get('warning'):
                        warning_type = schema_actions['warning']
                        if warning_type == 'ALL_ZERO':
                            detail['status'] = 'warning'
                            detail['issues'].append(
                                f"⚠️ 数据质量问题: 所有action值都为0"
                            )
                
                # 检查维度
                if range_from is not None and range_to is not None and actual_shape:
                    expected_dim = range_to - range_from
                    num_names = len(names)
                    
                    if expected_dim != num_names:
                        detail['status'] = 'warning'
                        detail['issues'].append(
                            f"维度可能不匹配: 配置range [{range_from}:{range_to}]={expected_dim}个元素, "
                            f"但names有{num_names}个"
                        )
                    
                    if len(actual_shape) > 0:
                        actual_dim = actual_shape[-1]
                        if range_to > actual_dim:
                            detail['status'] = 'error'
                            detail['issues'].append(
                                f"维度越界: 配置要求到索引{range_to}, 但实际数据只有{actual_dim}个元素"
                            )
                            result['dimension_mismatches'].append({
                                'h5_path': h5_path,
                                'configured_range': [range_from, range_to],
                                'actual_dim': actual_dim
                            })
            
            result['details'].append(detail)
        
        return result
    
    def generate_readable_report(self, comparison_report: Dict[str, Any]) -> str:
        """生成可读的对比报告"""
        lines = []
        lines.append("=" * 70)
        lines.append("配置对比报告")
        lines.append("=" * 70)
        
        summary = comparison_report.get('summary', {})
        lines.append(f"\n总错误数: {summary.get('total_errors', 0)}")
        lines.append(f"总警告数: {summary.get('total_warnings', 0)}")
        
        # Observations
        lines.append("\n" + "=" * 70)
        lines.append("Observations")
        lines.append("=" * 70)
        
        # Images
        images = comparison_report.get('observations', {}).get('images', [])
        if images:
            lines.append("\n[Images]")
            for img in images:
                status_symbol = "✓" if img['status'] == 'ok' else ("✗" if img['status'] == 'error' else "⚠")
                lines.append(f"  {status_symbol} {img['cam_name']}")
                if img.get('issues'):
                    for issue in img['issues']:
                        lines.append(f"      - {issue}")
                if img.get('actual_shape'):
                    lines.append(f"      Shape: {img['actual_shape']}")
        
        # State
        state_details = comparison_report.get('observations', {}).get('state', [])
        if state_details:
            lines.append("\n[State]")
            for detail in state_details:
                status_symbol = "✓" if detail['status'] == 'ok' else ("✗" if detail['status'] == 'error' else "⚠")
                lines.append(f"  {status_symbol} {detail['h5_path']} {detail.get('configured_range', '')}")
                lines.append(f"      Names: {', '.join(detail['names'][:3])}{'...' if len(detail['names']) > 3 else ''}")
                if detail.get('issues'):
                    for issue in detail['issues']:
                        lines.append(f"      - {issue}")
        
        # Actions
        lines.append("\n" + "=" * 70)
        lines.append("Actions")
        lines.append("=" * 70)
        
        action_details = comparison_report.get('actions', {}).get('details', [])
        if action_details:
            for detail in action_details:
                status_symbol = "✓" if detail['status'] == 'ok' else ("✗" if detail['status'] == 'error' else "⚠")
                lines.append(f"  {status_symbol} {detail['h5_path']} {detail.get('configured_range', '')}")
                lines.append(f"      Names: {', '.join(detail['names'][:3])}{'...' if len(detail['names']) > 3 else ''}")
                if detail.get('issues'):
                    for issue in detail['issues']:
                        lines.append(f"      - {issue}")
        
        lines.append("\n" + "=" * 70)
        
        return "\n".join(lines)


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    comparator = ConfigComparator()
    
    config_path = Path("/home/liu/program/robocoin-dataset/scripts/format_converters/tolerobot/configs/converter_config_agilex_cobot_decoupled_magic.yaml")
    if config_path.exists():
        config = comparator.load_config(config_path)
        print(f"Loaded config: {config.get('features', {}).keys()}")

