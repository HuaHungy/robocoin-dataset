"""
MMK2 BSON文件Schema发现器

自动分析MMK2格式的BSON文件数据结构。
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import logging


class MMK2SchemaDiscoverer:
    """MMK2 BSON文件Schema发现器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def discover_file(self, bson_path: Path, max_samples: int = 10) -> Dict[str, Any]:
        """
        发现单个BSON文件的schema
        
        Args:
            bson_path: BSON文件路径
            max_samples: 最多采样多少个记录
            
        Returns:
            schema字典
        """
        if not bson_path.exists():
            raise FileNotFoundError(f"BSON file not found: {bson_path}")
        
        try:
            import bson
        except ImportError:
            raise ImportError(
                "bson library not installed. Please run: pip install pymongo"
            )
        
        schema = {
            'file_path': str(bson_path),
            'file_size_mb': bson_path.stat().st_size / 1024 / 1024,
            'records': []
        }
        
        # 读取BSON文件
        with open(bson_path, 'rb') as f:
            data = f.read()
        
        # 解析BSON记录
        offset = 0
        record_count = 0
        
        while offset < len(data) and record_count < max_samples:
            try:
                # BSON格式: 4字节长度 + 数据
                if offset + 4 > len(data):
                    break
                
                doc_len = int.from_bytes(data[offset:offset+4], 'little')
                if offset + doc_len > len(data):
                    break
                
                # 解析BSON文档
                doc_bytes = data[offset:offset+doc_len]
                doc = bson.decode(doc_bytes)
                
                # 分析文档结构
                record_schema = self._analyze_document(doc)
                schema['records'].append(record_schema)
                
                offset += doc_len
                record_count += 1
                
            except Exception as e:
                self.logger.warning(f"Failed to parse BSON record at offset {offset}: {e}")
                break
        
        schema['total_records_sampled'] = record_count
        
        # 如果有多条记录，检查一致性
        if len(schema['records']) > 1:
            schema['consistency'] = self._check_consistency(schema['records'])
        
        return schema
    
    def _analyze_document(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """分析BSON文档的结构"""
        schema = {
            'fields': {},
            'num_fields': len(doc)
        }
        
        for key, value in doc.items():
            schema['fields'][key] = self._analyze_value(value)
        
        return schema
    
    def _analyze_value(self, value: Any, depth: int = 0) -> Dict[str, Any]:
        """递归分析值的类型和结构"""
        if depth > 10:
            return {'type': 'too_deep'}
        
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
        
        elif isinstance(value, bytes):
            return {
                'type': 'bytes',
                'length': len(value)
            }
        
        elif isinstance(value, list):
            info = {
                'type': 'array',
                'length': len(value)
            }
            if value:
                # 分析第一个元素
                info['item_schema'] = self._analyze_value(value[0], depth+1)
            return info
        
        elif isinstance(value, dict):
            info = {
                'type': 'object',
                'num_fields': len(value),
                'fields': {}
            }
            for k, v in value.items():
                info['fields'][k] = self._analyze_value(v, depth+1)
            return info
        
        else:
            return {'type': f'unknown ({type(value).__name__})'}
    
    def _check_consistency(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """检查多条记录的schema一致性"""
        if not records:
            return {'status': 'empty'}
        
        base_fields = set(records[0]['fields'].keys())
        all_consistent = True
        variations = []
        
        for i, record in enumerate(records[1:], 1):
            current_fields = set(record['fields'].keys())
            if current_fields != base_fields:
                all_consistent = False
                variations.append({
                    'record_index': i,
                    'missing_fields': list(base_fields - current_fields),
                    'extra_fields': list(current_fields - base_fields)
                })
        
        return {
            'status': 'consistent' if all_consistent else 'inconsistent',
            'base_fields': list(base_fields),
            'variations': variations
        }
    
    def discover_episode_dataset(
        self, 
        dataset_path: Path, 
        num_episodes: int = 5
    ) -> Dict[str, Any]:
        """
        发现整个数据集的MMK2 BSON schema（多个episodes）
        
        Args:
            dataset_path: 数据集路径
            num_episodes: 采样多少个episodes分析
            
        Returns:
            汇总的schema信息
        """
        # 查找BSON文件
        bson_files = sorted(dataset_path.rglob("*.bson"))
        
        if not bson_files:
            raise ValueError(f"No BSON files found in {dataset_path}")
        
        self.logger.info(f"找到 {len(bson_files)} 个BSON文件")
        
        # 采样分析
        sampled_files = bson_files[:min(num_episodes, len(bson_files))]
        schemas = []
        
        for bson_file in sampled_files:
            try:
                schema = self.discover_file(bson_file)
                schemas.append(schema)
                self.logger.info(f"✓ 分析完成: {bson_file.name}")
            except Exception as e:
                self.logger.error(f"✗ 分析失败 {bson_file.name}: {e}")
        
        # 合并schema
        merged_schema = {
            'total_bson_files': len(bson_files),
            'sampled_files': len(schemas),
            'schemas': schemas
        }
        
        # 检查跨文件一致性
        if len(schemas) > 1:
            merged_schema['cross_file_consistency'] = self._check_cross_file_consistency(schemas)
        
        return merged_schema
    
    def _check_cross_file_consistency(self, schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """检查跨文件的schema一致性"""
        if not schemas or not schemas[0].get('records'):
            return {'status': 'no_data'}
        
        # 使用第一个文件的第一条记录作为基准
        base_fields = set(schemas[0]['records'][0]['fields'].keys())
        all_consistent = True
        variations = []
        
        for i, schema in enumerate(schemas):
            if not schema.get('records'):
                continue
            
            current_fields = set(schema['records'][0]['fields'].keys())
            if current_fields != base_fields:
                all_consistent = False
                variations.append({
                    'file_index': i,
                    'file_path': schema['file_path'],
                    'missing_fields': list(base_fields - current_fields),
                    'extra_fields': list(current_fields - base_fields)
                })
        
        return {
            'status': 'consistent' if all_consistent else 'inconsistent',
            'base_fields': list(base_fields),
            'variations': variations
        }


def main():
    """测试MMK2 Schema Discoverer"""
    import sys
    import json
    
    if len(sys.argv) < 2:
        print("Usage: python mmk2_schema_discoverer.py <bson_file_or_dataset_path>")
        sys.exit(1)
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
    path = Path(sys.argv[1])
    discoverer = MMK2SchemaDiscoverer()
    
    if path.is_file() and path.suffix == '.bson':
        # 分析单个文件
        schema = discoverer.discover_file(path)
        print(json.dumps(schema, indent=2, ensure_ascii=False))
    
    elif path.is_dir():
        # 分析整个数据集
        schema = discoverer.discover_episode_dataset(path, num_episodes=5)
        print(json.dumps(schema, indent=2, ensure_ascii=False))
    
    else:
        print(f"错误: {path} 不是有效的BSON文件或目录")
        sys.exit(1)


if __name__ == '__main__':
    main()

