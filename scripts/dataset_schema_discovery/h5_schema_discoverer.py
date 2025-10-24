"""
H5文件Schema发现器

自动分析H5文件的数据结构，提取字段、形状、数据类型等信息。
"""

import h5py
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import logging


class H5SchemaDiscoverer:
    """H5文件Schema发现器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def discover_file(self, h5_path: Path, max_samples: int = 10) -> Dict[str, Any]:
        """
        发现单个H5文件的schema
        
        Args:
            h5_path: H5文件路径
            max_samples: 最多采样多少个值用于分析
            
        Returns:
            schema字典，包含所有字段的类型、形状、范围等信息
        """
        if not h5_path.exists():
            raise FileNotFoundError(f"H5 file not found: {h5_path}")
        
        schema = {
            'file_path': str(h5_path),
            'file_size_mb': h5_path.stat().st_size / 1024 / 1024,
            'structure': {}
        }
        
        with h5py.File(h5_path, 'r') as f:
            schema['structure'] = self._discover_group(f, max_samples)
        
        return schema
    
    def _discover_group(self, group: h5py.Group, max_samples: int) -> Dict[str, Any]:
        """递归发现H5 Group的结构"""
        structure = {}
        
        for key in group.keys():
            item = group[key]
            
            if isinstance(item, h5py.Group):
                # 递归处理子group
                structure[key] = {
                    'type': 'group',
                    'children': self._discover_group(item, max_samples)
                }
            
            elif isinstance(item, h5py.Dataset):
                # 分析dataset
                structure[key] = self._analyze_dataset(item, max_samples)
        
        return structure
    
    def _analyze_dataset(self, dataset: h5py.Dataset, max_samples: int) -> Dict[str, Any]:
        """分析H5 Dataset"""
        info = {
            'type': 'dataset',
            'dtype': str(dataset.dtype),
            'shape': list(dataset.shape),
            'ndim': dataset.ndim
        }
        
        # 获取数据的一些统计信息
        try:
            # 对于小数据集，直接读取
            if dataset.size < 1000:
                data = dataset[:]
            else:
                # 对于大数据集，采样
                if dataset.ndim == 1:
                    indices = np.linspace(0, len(dataset)-1, min(max_samples, len(dataset)), dtype=int)
                    data = dataset[indices]
                elif dataset.ndim == 2:
                    # 采样第一维
                    indices = np.linspace(0, dataset.shape[0]-1, min(max_samples, dataset.shape[0]), dtype=int)
                    data = dataset[indices]
                else:
                    # 多维数据，只采样第一个元素
                    data = dataset[0:min(max_samples, dataset.shape[0])]
            
            # 统计信息（仅对数值类型）
            if np.issubdtype(dataset.dtype, np.number):
                info['statistics'] = {
                    'min': float(np.min(data)),
                    'max': float(np.max(data)),
                    'mean': float(np.mean(data)),
                    'std': float(np.std(data))
                }
            
            # 样本值
            if dataset.size < 100:
                info['sample_values'] = self._convert_to_python(data[:min(5, len(data))])
            else:
                # 只采样前几个值
                sample_data = data[0] if dataset.ndim > 1 else data[:min(5, len(data))]
                info['sample_values'] = self._convert_to_python(sample_data)
        
        except Exception as e:
            self.logger.warning(f"Failed to read dataset statistics: {e}")
            info['error'] = str(e)
        
        return info
    
    def _convert_to_python(self, data: Union[np.ndarray, Any]) -> Any:
        """将numpy数据转换为Python原生类型，用于JSON序列化"""
        if isinstance(data, np.ndarray):
            if data.size == 1:
                return self._convert_to_python(data.item())
            elif data.size < 10:
                return [self._convert_to_python(x) for x in data]
            else:
                # 太大了，只返回shape信息
                return f"<array shape={data.shape}>"
        elif isinstance(data, (np.integer, np.floating)):
            return data.item()
        elif isinstance(data, (list, tuple)):
            return [self._convert_to_python(x) for x in data]
        else:
            return data
    
    def discover_episode_dataset(
        self, 
        dataset_path: Path, 
        num_episodes: int = 5
    ) -> Dict[str, Any]:
        """
        发现整个数据集的H5 schema（多个episodes）
        
        Args:
            dataset_path: 数据集路径
            num_episodes: 采样多少个episodes分析
            
        Returns:
            汇总的schema信息
        """
        # 查找H5文件
        h5_files = sorted(dataset_path.rglob("*.h5"))
        
        if not h5_files:
            h5_files = sorted(dataset_path.rglob("*.hdf5"))
        
        if not h5_files:
            raise ValueError(f"No H5 files found in {dataset_path}")
        
        self.logger.info(f"找到 {len(h5_files)} 个H5文件")
        
        # 采样分析
        sampled_files = h5_files[:min(num_episodes, len(h5_files))]
        schemas = []
        
        for h5_file in sampled_files:
            try:
                schema = self.discover_file(h5_file)
                schemas.append(schema)
                self.logger.info(f"✓ 分析完成: {h5_file.name}")
            except Exception as e:
                self.logger.error(f"✗ 分析失败 {h5_file.name}: {e}")
        
        # 合并schema（检查一致性）
        merged_schema = self._merge_schemas(schemas)
        merged_schema['total_h5_files'] = len(h5_files)
        merged_schema['sampled_files'] = len(schemas)
        
        return merged_schema
    
    def _merge_schemas(self, schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        合并多个schema，检查一致性
        
        如果所有文件的schema一致，返回统一schema
        如果有不一致，标记差异
        """
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
        
        # 检查键集合
        keys1 = set(struct1.keys())
        keys2 = set(struct2.keys())
        
        if keys1 != keys2:
            missing_in_2 = keys1 - keys2
            missing_in_1 = keys2 - keys1
            
            if missing_in_2:
                differences.append(f"{path}: 缺失字段 {missing_in_2}")
            if missing_in_1:
                differences.append(f"{path}: 多余字段 {missing_in_1}")
        
        # 检查共同的键
        for key in keys1 & keys2:
            item1 = struct1[key]
            item2 = struct2[key]
            current_path = f"{path}/{key}" if path else key
            
            # 检查类型
            if item1.get('type') != item2.get('type'):
                differences.append(
                    f"{current_path}: 类型不一致 "
                    f"({item1.get('type')} vs {item2.get('type')})"
                )
                continue
            
            # 如果是group，递归检查
            if item1.get('type') == 'group':
                sub_diffs = self._compare_structures(
                    item1.get('children', {}),
                    item2.get('children', {}),
                    current_path
                )
                differences.extend(sub_diffs)
            
            # 如果是dataset，检查shape和dtype
            elif item1.get('type') == 'dataset':
                if item1.get('dtype') != item2.get('dtype'):
                    differences.append(
                        f"{current_path}: dtype不一致 "
                        f"({item1.get('dtype')} vs {item2.get('dtype')})"
                    )
                
                # shape的第一维可能不同（episode长度），只检查后续维度
                shape1 = item1.get('shape', [])
                shape2 = item2.get('shape', [])
                if len(shape1) != len(shape2):
                    differences.append(
                        f"{current_path}: shape维度不一致 "
                        f"({shape1} vs {shape2})"
                    )
                elif len(shape1) > 1 and shape1[1:] != shape2[1:]:
                    differences.append(
                        f"{current_path}: shape后续维度不一致 "
                        f"({shape1[1:]} vs {shape2[1:]})"
                    )
        
        return differences


def main():
    """测试H5 Schema Discoverer"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python h5_schema_discoverer.py <h5_file_or_dataset_path>")
        sys.exit(1)
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
    path = Path(sys.argv[1])
    discoverer = H5SchemaDiscoverer()
    
    if path.is_file() and path.suffix in ['.h5', '.hdf5']:
        # 分析单个文件
        schema = discoverer.discover_file(path)
        import json
        print(json.dumps(schema, indent=2, ensure_ascii=False))
    
    elif path.is_dir():
        # 分析整个数据集
        schema = discoverer.discover_episode_dataset(path, num_episodes=5)
        import json
        print(json.dumps(schema, indent=2, ensure_ascii=False))
    
    else:
        print(f"错误: {path} 不是有效的H5文件或目录")
        sys.exit(1)


if __name__ == '__main__':
    main()

