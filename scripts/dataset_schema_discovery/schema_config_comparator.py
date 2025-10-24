"""
Schema vs Config 对比工具

对比发现的实际数据schema与converter config，诊断配置问题。
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, Set
import logging
import yaml


class SchemaConfigComparator:
    """Schema vs Config 对比工具"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def compare(
        self, 
        discovered_schema: Dict[str, Any],
        converter_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        对比discovered schema和converter config
        
        Args:
            discovered_schema: 从数据集发现的schema
            converter_config: converter配置文件
            
        Returns:
            诊断结果
        """
        diagnosis = {
            'dataset_path': discovered_schema.get('dataset_path'),
            'device_model': discovered_schema.get('device_model'),
            'detected_formats': discovered_schema.get('detected_formats', []),
            'issues': [],
            'warnings': [],
            'suggestions': [],
            'severity': 'ok'  # ok, warning, error
        }
        
        # 1. 检查device_model匹配
        self._check_device_model(discovered_schema, converter_config, diagnosis)
        
        # 2. 检查数据格式匹配
        self._check_data_formats(discovered_schema, converter_config, diagnosis)
        
        # 3. 检查observation字段
        self._check_observations(discovered_schema, converter_config, diagnosis)
        
        # 4. 检查action字段
        self._check_actions(discovered_schema, converter_config, diagnosis)
        
        # 5. 检查图像/相机字段
        self._check_images(discovered_schema, converter_config, diagnosis)
        
        # 6. 确定总体严重程度
        if diagnosis['issues']:
            diagnosis['severity'] = 'error'
        elif diagnosis['warnings']:
            diagnosis['severity'] = 'warning'
        
        return diagnosis
    
    def _check_device_model(
        self, 
        schema: Dict[str, Any], 
        config: Dict[str, Any],
        diagnosis: Dict[str, Any]
    ):
        """检查device_model是否匹配"""
        schema_dm = schema.get('device_model')
        
        # converter_config本身没有device_model字段
        # 这个需要通过converter_factory_config.yaml来确认
        # 这里我们主要检查schema中是否有device_model_annotation
        
        if 'device_model_annotation' in schema:
            annotation = schema['device_model_annotation']
            if not annotation:
                diagnosis['warnings'].append({
                    'category': 'device_model',
                    'message': 'device_model_annotation.yaml存在但为空',
                    'severity': 'warning'
                })
        else:
            diagnosis['issues'].append({
                'category': 'device_model',
                'message': 'dataset目录缺少device_model_annotation.yaml文件',
                'severity': 'error',
                'suggestion': '请创建device_model_annotation.yaml并指定正确的device_model'
            })
    
    def _check_data_formats(
        self, 
        schema: Dict[str, Any], 
        config: Dict[str, Any],
        diagnosis: Dict[str, Any]
    ):
        """检查数据格式是否与converter类型匹配"""
        detected_formats = set(schema.get('detected_formats', []))
        
        # 根据detected formats推断期望的converter类型
        # 这个检查是辅助性的，主要提醒
        
        if 'h5' in detected_formats and 'video' in detected_formats:
            diagnosis['warnings'].append({
                'category': 'data_format',
                'message': '检测到H5+视频格式，请确认使用H5+MP4 converter',
                'severity': 'info'
            })
        
        elif 'mcap' in detected_formats:
            diagnosis['warnings'].append({
                'category': 'data_format',
                'message': '检测到MCAP格式，请确认使用MCAP converter',
                'severity': 'info'
            })
        
        elif 'bson' in detected_formats:
            diagnosis['warnings'].append({
                'category': 'data_format',
                'message': '检测到BSON格式，请确认使用MMK2 converter',
                'severity': 'info'
            })
    
    def _check_observations(
        self, 
        schema: Dict[str, Any], 
        config: Dict[str, Any],
        diagnosis: Dict[str, Any]
    ):
        """检查observation字段配置"""
        config_obs = config.get('features', {}).get('observation', {})
        
        # 检查state字段（qpos, qvel等）
        if 'state' in config_obs:
            self._check_state_fields(schema, config_obs['state'], diagnosis)
        
        # 检查effort字段
        if 'effort' in config_obs:
            self._check_effort_fields(schema, config_obs['effort'], diagnosis)
    
    def _check_state_fields(
        self, 
        schema: Dict[str, Any], 
        state_config: Dict[str, Any],
        diagnosis: Dict[str, Any]
    ):
        """检查state字段（从H5或MCAP中）"""
        # 从schema中提取实际的state相关字段
        actual_fields = self._extract_h5_observation_fields(schema)
        
        # 检查config中配置的字段是否存在
        for field_name, field_config in state_config.items():
            h5_path = field_config.get('h5_path')
            mcap_topic = field_config.get('mcap_topic')
            json_key = field_config.get('json_key')
            
            if h5_path:
                # 检查H5路径是否存在
                if h5_path not in actual_fields.get('h5', set()):
                    diagnosis['issues'].append({
                        'category': 'observation_state',
                        'field': field_name,
                        'message': f'配置的H5路径不存在: {h5_path}',
                        'severity': 'error',
                        'suggestion': f'实际存在的H5字段: {actual_fields.get("h5", set())}'
                    })
            
            if mcap_topic:
                # 检查MCAP topic是否存在
                if mcap_topic not in actual_fields.get('mcap_topics', set()):
                    diagnosis['issues'].append({
                        'category': 'observation_state',
                        'field': field_name,
                        'message': f'配置的MCAP topic不存在: {mcap_topic}',
                        'severity': 'error',
                        'suggestion': f'实际存在的topics: {actual_fields.get("mcap_topics", set())}'
                    })
    
    def _check_effort_fields(
        self, 
        schema: Dict[str, Any], 
        effort_config: Dict[str, Any],
        diagnosis: Dict[str, Any]
    ):
        """检查effort字段"""
        actual_fields = self._extract_h5_observation_fields(schema)
        
        for field_name, field_config in effort_config.items():
            h5_path = field_config.get('h5_path')
            
            if h5_path:
                if h5_path not in actual_fields.get('h5', set()):
                    diagnosis['issues'].append({
                        'category': 'observation_effort',
                        'field': field_name,
                        'message': f'配置的H5路径不存在: {h5_path}',
                        'severity': 'error'
                    })
    
    def _check_actions(
        self, 
        schema: Dict[str, Any], 
        config: Dict[str, Any],
        diagnosis: Dict[str, Any]
    ):
        """检查action字段配置"""
        config_actions = config.get('features', {}).get('action', {})
        
        actual_fields = self._extract_h5_action_fields(schema)
        
        for field_name, field_config in config_actions.items():
            h5_path = field_config.get('h5_path')
            
            if h5_path:
                if h5_path not in actual_fields.get('h5', set()):
                    diagnosis['issues'].append({
                        'category': 'action',
                        'field': field_name,
                        'message': f'配置的H5路径不存在: {h5_path}',
                        'severity': 'error',
                        'suggestion': f'实际存在的action字段: {actual_fields.get("h5", set())}'
                    })
    
    def _check_images(
        self, 
        schema: Dict[str, Any], 
        config: Dict[str, Any],
        diagnosis: Dict[str, Any]
    ):
        """检查图像/相机字段配置"""
        config_images = config.get('features', {}).get('observation', {}).get('images', {})
        
        # 从schema中提取实际的相机
        actual_cameras = self._extract_camera_names(schema)
        
        # 检查config中配置的相机是否存在
        config_cameras = set(config_images.keys())
        
        missing_cameras = config_cameras - actual_cameras
        extra_cameras = actual_cameras - config_cameras
        
        if missing_cameras:
            diagnosis['issues'].append({
                'category': 'images',
                'message': f'配置中的相机在实际数据中不存在: {missing_cameras}',
                'severity': 'error',
                'suggestion': f'请从config中删除这些相机配置: {missing_cameras}'
            })
        
        if extra_cameras:
            diagnosis['warnings'].append({
                'category': 'images',
                'message': f'实际数据中存在但config未配置的相机: {extra_cameras}',
                'severity': 'warning',
                'suggestion': f'考虑添加这些相机到config: {extra_cameras}'
            })
    
    def _extract_h5_observation_fields(self, schema: Dict[str, Any]) -> Dict[str, Set[str]]:
        """从schema中提取H5 observation相关字段"""
        fields = {'h5': set(), 'mcap_topics': set()}
        
        # 从H5 schema中提取
        h5_data = schema.get('data_formats', {}).get('h5', {})
        if h5_data and 'structure' in h5_data:
            structure = h5_data['structure']
            
            # 递归提取所有字段路径
            def extract_paths(obj, prefix=''):
                if isinstance(obj, dict):
                    if obj.get('type') == 'dataset':
                        fields['h5'].add(prefix)
                    elif obj.get('type') == 'group':
                        children = obj.get('children', {})
                        for key, value in children.items():
                            new_prefix = f"{prefix}/{key}" if prefix else key
                            extract_paths(value, new_prefix)
                    elif 'fields' in obj:
                        for key, value in obj['fields'].items():
                            new_prefix = f"{prefix}/{key}" if prefix else key
                            extract_paths(value, new_prefix)
            
            extract_paths(structure)
        
        # 从MCAP schema中提取topics
        mcap_data = schema.get('data_formats', {}).get('mcap', {})
        if mcap_data and 'topics' in mcap_data:
            fields['mcap_topics'] = set(mcap_data['topics'].keys())
        
        return fields
    
    def _extract_h5_action_fields(self, schema: Dict[str, Any]) -> Dict[str, Set[str]]:
        """从schema中提取H5 action相关字段"""
        # 通常action字段在H5的顶层或action group下
        return self._extract_h5_observation_fields(schema)
    
    def _extract_camera_names(self, schema: Dict[str, Any]) -> Set[str]:
        """从schema中提取相机名称"""
        cameras = set()
        
        # 从视频元数据中提取
        video_data = schema.get('data_formats', {}).get('video', {})
        if video_data and 'camera_groups' in video_data:
            cameras.update(video_data['camera_groups'].keys())
        
        # 从H5中的images字段提取（如果有）
        h5_data = schema.get('data_formats', {}).get('h5', {})
        if h5_data and 'structure' in h5_data:
            structure = h5_data['structure']
            
            # 查找images group
            if isinstance(structure, dict) and 'fields' in structure:
                fields = structure['fields']
                if 'images' in fields or 'observations/images' in str(fields):
                    # 这里需要更精细的解析
                    pass
        
        return cameras
    
    def load_converter_config(self, config_path: Path) -> Dict[str, Any]:
        """加载converter配置文件"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def generate_fix_suggestions(self, diagnosis: Dict[str, Any]) -> List[str]:
        """基于诊断结果生成修复建议"""
        suggestions = []
        
        # 汇总所有建议
        for issue in diagnosis.get('issues', []):
            if 'suggestion' in issue:
                suggestions.append(f"❌ [{issue['category']}] {issue['suggestion']}")
        
        for warning in diagnosis.get('warnings', []):
            if 'suggestion' in warning:
                suggestions.append(f"⚠️  [{warning['category']}] {warning['suggestion']}")
        
        return suggestions


def main():
    """测试Schema Config Comparator"""
    import sys
    import json
    import argparse
    
    parser = argparse.ArgumentParser(description='Schema vs Config 对比工具')
    parser.add_argument('schema_file', help='Discovered schema JSON文件')
    parser.add_argument('config_file', help='Converter config YAML文件')
    parser.add_argument('--output', '-o', help='输出诊断结果到文件')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
    comparator = SchemaConfigComparator()
    
    # 加载schema
    with open(args.schema_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    
    # 加载config
    config = comparator.load_converter_config(Path(args.config_file))
    
    # 执行对比
    diagnosis = comparator.compare(schema, config)
    
    # 输出结果
    print("\n" + "=" * 70)
    print("诊断结果")
    print("=" * 70)
    print(f"数据集: {diagnosis['dataset_path']}")
    print(f"Device Model: {diagnosis['device_model']}")
    print(f"严重程度: {diagnosis['severity']}")
    print()
    
    if diagnosis['issues']:
        print(f"发现 {len(diagnosis['issues'])} 个错误:")
        for i, issue in enumerate(diagnosis['issues'], 1):
            print(f"  {i}. [{issue['category']}] {issue['message']}")
            if 'suggestion' in issue:
                print(f"     建议: {issue['suggestion']}")
        print()
    
    if diagnosis['warnings']:
        print(f"发现 {len(diagnosis['warnings'])} 个警告:")
        for i, warning in enumerate(diagnosis['warnings'], 1):
            print(f"  {i}. [{warning['category']}] {warning['message']}")
        print()
    
    # 生成修复建议
    suggestions = comparator.generate_fix_suggestions(diagnosis)
    if suggestions:
        print("修复建议:")
        for suggestion in suggestions:
            print(f"  {suggestion}")
    
    # 保存结果
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(diagnosis, f, indent=2, ensure_ascii=False)
        print(f"\n✓ 诊断结果已保存到: {args.output}")


if __name__ == '__main__':
    main()

