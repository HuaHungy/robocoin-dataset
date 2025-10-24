"""
JSON文件Schema发现器

自动分析JSON文件的数据结构，提取字段、类型等信息。
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import logging
import numpy as np


class JSONSchemaDiscoverer:
    """JSON文件Schema发现器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def discover_file(self, json_path: Path, max_samples: int = 10) -> Dict[str, Any]:
        """
        发现单个JSON文件的schema
        
        Args:
            json_path: JSON文件路径
            max_samples: 最多采样多少个值用于分析
            
        Returns:
            schema字典
        """
        if not json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        schema = {
            'file_path': str(json_path),
            'file_size_mb': json_path.stat().st_size / 1024 / 1024,
            'structure': self._analyze_value(data, max_samples)
        }
        
        return schema
    
    def _analyze_value(self, value: Any, max_samples: int, depth: int = 0) -> Dict[str, Any]:
        """递归分析JSON值的结构"""
        if depth > 10:  # 防止过深递归
            return {'type': 'too_deep', 'value': str(type(value))}
        
        if value is None:
            return {'type': 'null'}
        
        elif isinstance(value, bool):
            return {'type': 'boolean', 'value': value}
        
        elif isinstance(value, int):
            return {'type': 'integer', 'value': value}
        
        elif isinstance(value, float):
            return {'type': 'float', 'value': value}
        
        elif isinstance(value, str):
            return {
                'type': 'string',
                'length': len(value),
                'sample': value[:100] if len(value) > 100 else value
            }
        
        elif isinstance(value, list):
            return self._analyze_list(value, max_samples, depth)
        
        elif isinstance(value, dict):
            return self._analyze_dict(value, max_samples, depth)
        
        else:
            return {'type': f'unknown ({type(value).__name__})'}
    
    def _analyze_list(self, lst: List, max_samples: int, depth: int) -> Dict[str, Any]:
        """分析list结构"""
        info = {
            'type': 'array',
            'length': len(lst),
            'item_types': []
        }
        
        if not lst:
            info['item_type'] = 'empty'
            return info
        
        # 采样分析元素类型
        samples = lst[:min(max_samples, len(lst))]
        element_schemas = [self._analyze_value(item, max_samples, depth+1) for item in samples]
        
        # 检查类型一致性
        types = [schema.get('type') for schema in element_schemas]
        unique_types = list(set(types))
        
        if len(unique_types) == 1:
            # 类型一致
            info['item_type'] = unique_types[0]
            info['item_schema'] = element_schemas[0]
            
            # 如果是数值类型，计算统计信息
            if unique_types[0] in ['integer', 'float'] and len(samples) > 1:
                values = [s.get('value') for s in element_schemas if 'value' in s]
                if values:
                    info['statistics'] = {
                        'min': min(values),
                        'max': max(values),
                        'mean': sum(values) / len(values)
                    }
        else:
            # 类型不一致
            info['item_type'] = 'mixed'
            info['item_types'] = unique_types
        
        return info
    
    def _analyze_dict(self, dct: Dict, max_samples: int, depth: int) -> Dict[str, Any]:
        """分析dict结构"""
        info = {
            'type': 'object',
            'num_keys': len(dct),
            'fields': {}
        }
        
        for key, value in dct.items():
            info['fields'][key] = self._analyze_value(value, max_samples, depth+1)
        
        return info
    
    def discover_episode_dataset(
        self, 
        dataset_path: Path, 
        num_episodes: int = 5,
        json_pattern: str = "*.json"
    ) -> Dict[str, Any]:
        """
        发现整个数据集的JSON schema（多个episodes）
        
        Args:
            dataset_path: 数据集路径
            num_episodes: 采样多少个episodes分析
            json_pattern: JSON文件的匹配模式
            
        Returns:
            汇总的schema信息
        """
        # 查找JSON文件
        json_files = sorted(dataset_path.rglob(json_pattern))
        
        if not json_files:
            raise ValueError(f"No JSON files found in {dataset_path}")
        
        self.logger.info(f"找到 {len(json_files)} 个JSON文件")
        
        # 采样分析
        sampled_files = json_files[:min(num_episodes, len(json_files))]
        schemas = []
        
        for json_file in sampled_files:
            try:
                schema = self.discover_file(json_file)
                schemas.append(schema)
                self.logger.info(f"✓ 分析完成: {json_file.name}")
            except Exception as e:
                self.logger.error(f"✗ 分析失败 {json_file.name}: {e}")
        
        # 合并schema（检查一致性）
        merged_schema = self._merge_schemas(schemas)
        merged_schema['total_json_files'] = len(json_files)
        merged_schema['sampled_files'] = len(schemas)
        
        return merged_schema
    
    def _merge_schemas(self, schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """合并多个schema，检查一致性"""
        if not schemas:
            return {}
        
        if len(schemas) == 1:
            return schemas[0]
        
        # 使用第一个schema作为基准
        base_schema = schemas[0]['structure']
        merged = {
            'structure': base_schema,
            'consistency': 'checking',
            'variations': []
        }
        
        # 检查其他schema是否一致
        all_consistent = True
        for i, schema in enumerate(schemas[1:], 1):
            differences = self._compare_structures(base_schema, schema['structure'])
            if differences:
                all_consistent = False
                merged['variations'].append({
                    'file_index': i,
                    'file_path': schema['file_path'],
                    'differences': differences
                })
        
        merged['consistency'] = 'consistent' if all_consistent else 'inconsistent'
        
        return merged
    
    def _compare_structures(
        self, 
        struct1: Dict[str, Any], 
        struct2: Dict[str, Any],
        path: str = ""
    ) -> List[str]:
        """比较两个structure，返回差异列表"""
        differences = []
        
        # 类型检查
        type1 = struct1.get('type')
        type2 = struct2.get('type')
        
        if type1 != type2:
            differences.append(f"{path or 'root'}: 类型不一致 ({type1} vs {type2})")
            return differences
        
        # 如果是object，检查字段
        if type1 == 'object':
            fields1 = struct1.get('fields', {})
            fields2 = struct2.get('fields', {})
            
            keys1 = set(fields1.keys())
            keys2 = set(fields2.keys())
            
            if keys1 != keys2:
                missing_in_2 = keys1 - keys2
                missing_in_1 = keys2 - keys1
                
                if missing_in_2:
                    differences.append(f"{path or 'root'}: 缺失字段 {missing_in_2}")
                if missing_in_1:
                    differences.append(f"{path or 'root'}: 多余字段 {missing_in_1}")
            
            # 递归检查共同字段
            for key in keys1 & keys2:
                current_path = f"{path}.{key}" if path else key
                sub_diffs = self._compare_structures(fields1[key], fields2[key], current_path)
                differences.extend(sub_diffs)
        
        # 如果是array，检查元素类型
        elif type1 == 'array':
            item_type1 = struct1.get('item_type')
            item_type2 = struct2.get('item_type')
            
            if item_type1 != item_type2:
                differences.append(
                    f"{path or 'root'}[]: 元素类型不一致 ({item_type1} vs {item_type2})"
                )
        
        return differences


def main():
    """测试JSON Schema Discoverer"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python json_schema_discoverer.py <json_file_or_dataset_path>")
        sys.exit(1)
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
    path = Path(sys.argv[1])
    discoverer = JSONSchemaDiscoverer()
    
    if path.is_file() and path.suffix == '.json':
        # 分析单个文件
        schema = discoverer.discover_file(path)
        print(json.dumps(schema, indent=2, ensure_ascii=False))
    
    elif path.is_dir():
        # 分析整个数据集
        schema = discoverer.discover_episode_dataset(path, num_episodes=5)
        print(json.dumps(schema, indent=2, ensure_ascii=False))
    
    else:
        print(f"错误: {path} 不是有效的JSON文件或目录")
        sys.exit(1)


if __name__ == '__main__':
    main()

