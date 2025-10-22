"""
Schema深度分析器 - 分析采样episodes的实际数据结构

功能：
- 读取H5、JSON、MCAP、BSON等格式的数据
- 提取字段名、shape、dtype、range
- 识别images、state、action等组件
- 生成结构化的schema报告
"""

import logging
import json
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import h5py


class SchemaAnalyzer:
    """Schema分析器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def analyze_episode(
        self,
        episode_path: Path,
        format_type: str
    ) -> Dict[str, Any]:
        """
        深度分析单个episode的schema
        
        Args:
            episode_path: Episode路径
            format_type: 格式类型
            
        Returns:
            Schema信息字典
        """
        self.logger.info(f"分析Episode: {episode_path}")
        
        if "h5" in format_type:
            return self._analyze_h5(episode_path)
        elif "json" in format_type:
            return self._analyze_json(episode_path)
        elif "mcap" in format_type:
            return self._analyze_mcap(episode_path)
        elif "bson" in format_type:
            return self._analyze_bson(episode_path)
        else:
            raise ValueError(f"不支持的格式: {format_type}")
    
    def _analyze_h5(self, h5_path: Path) -> Dict[str, Any]:
        """分析H5文件的schema"""
        schema = {
            'format': 'h5',
            'file_path': str(h5_path),
            'observations': {},
            'actions': {},
            'other_fields': {},
            'errors': []
        }
        
        try:
            with h5py.File(h5_path, 'r') as f:
                # 递归遍历H5文件结构
                schema['structure'] = self._traverse_h5_group(f, max_depth=5)
                
                # 提取observations
                if 'observations' in f:
                    obs_group = f['observations']
                    schema['observations'] = self._extract_h5_observations(obs_group)
                
                # 提取actions
                if 'actions' in f or 'action' in f:
                    action_key = 'actions' if 'actions' in f else 'action'
                    schema['actions'] = self._extract_h5_actions(f[action_key])
                
                # 提取其他关键字段
                for key in f.keys():
                    if key not in ['observations', 'actions', 'action']:
                        schema['other_fields'][key] = self._describe_h5_dataset(f[key])
        
        except Exception as e:
            self.logger.error(f"分析H5文件失败: {e}")
            schema['errors'].append(str(e))
        
        return schema
    
    def _traverse_h5_group(
        self,
        group: h5py.Group,
        max_depth: int = 5,
        current_depth: int = 0,
        path_prefix: str = ""
    ) -> Dict[str, Any]:
        """递归遍历H5 Group"""
        if current_depth >= max_depth:
            return {'_truncated': True}
        
        structure = {}
        
        for key in group.keys():
            item = group[key]
            current_path = f"{path_prefix}/{key}" if path_prefix else key
            
            if isinstance(item, h5py.Dataset):
                structure[key] = {
                    'type': 'dataset',
                    'shape': item.shape,
                    'dtype': str(item.dtype),
                    'path': current_path
                }
                
                # 如果数据量不大，计算统计信息
                if item.size > 0 and item.size < 100000:
                    try:
                        data = item[()]
                        if np.issubdtype(item.dtype, np.number):
                            structure[key]['min'] = float(np.min(data))
                            structure[key]['max'] = float(np.max(data))
                            structure[key]['mean'] = float(np.mean(data))
                    except:
                        pass
            
            elif isinstance(item, h5py.Group):
                structure[key] = {
                    'type': 'group',
                    'path': current_path,
                    'children': self._traverse_h5_group(
                        item,
                        max_depth=max_depth,
                        current_depth=current_depth + 1,
                        path_prefix=current_path
                    )
                }
        
        return structure
    
    def _extract_h5_observations(self, obs_group: h5py.Group) -> Dict[str, Any]:
        """提取observations schema"""
        observations = {
            'images': {},
            'state': {},
            'qpos': {},
            'qvel': {},
            'other': {}
        }
        
        # 遍历observations组
        for key in obs_group.keys():
            item = obs_group[key]
            
            if isinstance(item, h5py.Group):
                # 可能是images组
                if key == 'images' or 'image' in key.lower() or 'cam' in key.lower():
                    for cam_name in item.keys():
                        cam_data = item[cam_name]
                        if isinstance(cam_data, h5py.Dataset):
                            observations['images'][cam_name] = {
                                'shape': cam_data.shape,
                                'dtype': str(cam_data.dtype),
                                'h5_path': f'observations/{key}/{cam_name}'
                            }
                else:
                    # 递归处理其他组
                    for sub_key in item.keys():
                        observations['other'][f'{key}/{sub_key}'] = self._describe_h5_dataset(item[sub_key])
            
            elif isinstance(item, h5py.Dataset):
                # 直接的dataset
                desc = self._describe_h5_dataset(item)
                desc['h5_path'] = f'observations/{key}'
                
                if 'qpos' in key.lower():
                    observations['qpos'][key] = desc
                elif 'qvel' in key.lower():
                    observations['qvel'][key] = desc
                elif 'state' in key.lower():
                    observations['state'][key] = desc
                else:
                    observations['other'][key] = desc
        
        return observations
    
    def _extract_h5_actions(self, action_data: Union[h5py.Group, h5py.Dataset]) -> Dict[str, Any]:
        """提取actions schema"""
        if isinstance(action_data, h5py.Dataset):
            desc = self._describe_h5_dataset(action_data)
            desc['h5_path'] = 'actions' if 'actions' in str(action_data.name) else 'action'
            return desc
        elif isinstance(action_data, h5py.Group):
            actions = {}
            for key in action_data.keys():
                desc = self._describe_h5_dataset(action_data[key])
                desc['h5_path'] = f'{action_data.name}/{key}'
                actions[key] = desc
            return actions
        else:
            return {}
    
    def _describe_h5_dataset(self, dataset: h5py.Dataset) -> Dict[str, Any]:
        """描述H5 Dataset"""
        desc = {
            'shape': dataset.shape,
            'dtype': str(dataset.dtype),
        }
        
        # 计算统计信息（如果数据量不大）
        if dataset.size > 0 and dataset.size < 100000:
            try:
                data = dataset[()]
                if np.issubdtype(dataset.dtype, np.number):
                    desc['min'] = float(np.min(data))
                    desc['max'] = float(np.max(data))
                    desc['mean'] = float(np.mean(data))
                    desc['std'] = float(np.std(data))
                    
                    # 🆕 检测全0数据
                    is_all_zero = np.all(data == 0)
                    if is_all_zero:
                        desc['warning'] = 'ALL_ZERO'
                        desc['data_quality'] = 'suspicious'
                    
                    # 🆕 检测常量数据（标准差接近0）
                    elif desc['std'] < 1e-10:
                        desc['warning'] = 'CONSTANT'
                        desc['data_quality'] = 'suspicious'
                        desc['constant_value'] = float(np.mean(data))
                    
                    # 🆕 检测数据变化范围很小（可能是噪声）
                    elif desc['max'] - desc['min'] < 1e-6:
                        desc['warning'] = 'VERY_SMALL_RANGE'
                        desc['data_quality'] = 'suspicious'
            except:
                pass
        
        return desc
    
    def _analyze_json(self, json_path: Path) -> Dict[str, Any]:
        """分析JSON文件的schema"""
        schema = {
            'format': 'json',
            'file_path': str(json_path),
            'fields': {},
            'errors': []
        }
        
        try:
            # 如果是目录，查找JSON文件
            if json_path.is_dir():
                json_files = list(json_path.glob("*.json"))
                if json_files:
                    json_path = json_files[0]  # 取第一个
            
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            # 递归分析JSON结构
            schema['fields'] = self._analyze_json_structure(data)
        
        except Exception as e:
            self.logger.error(f"分析JSON文件失败: {e}")
            schema['errors'].append(str(e))
        
        return schema
    
    def _analyze_json_structure(
        self,
        data: Any,
        max_depth: int = 5,
        current_depth: int = 0
    ) -> Dict[str, Any]:
        """递归分析JSON结构"""
        if current_depth >= max_depth:
            return {'_truncated': True}
        
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                result[key] = {
                    'type': type(value).__name__,
                    'value_sample': str(value)[:100] if not isinstance(value, (dict, list)) else None,
                }
                
                if isinstance(value, (dict, list)):
                    result[key]['structure'] = self._analyze_json_structure(
                        value,
                        max_depth=max_depth,
                        current_depth=current_depth + 1
                    )
                
                # 如果是数组，分析元素
                if isinstance(value, list) and len(value) > 0:
                    result[key]['length'] = len(value)
                    result[key]['element_type'] = type(value[0]).__name__
                    if isinstance(value[0], (int, float)):
                        result[key]['min'] = min(value)
                        result[key]['max'] = max(value)
            
            return result
        
        elif isinstance(data, list):
            if len(data) == 0:
                return {'type': 'empty_list'}
            else:
                return {
                    'type': 'list',
                    'length': len(data),
                    'element_type': type(data[0]).__name__,
                    'sample_element': self._analyze_json_structure(
                        data[0],
                        max_depth=max_depth,
                        current_depth=current_depth + 1
                    )
                }
        else:
            return {'type': type(data).__name__, 'value': str(data)[:100]}
    
    def _analyze_mcap(self, mcap_path: Path) -> Dict[str, Any]:
        """分析MCAP文件的schema"""
        schema = {
            'format': 'mcap',
            'file_path': str(mcap_path),
            'topics': {},
            'schemas': {},
            'errors': []
        }
        
        try:
            from mcap.reader import make_reader
            
            with open(mcap_path, 'rb') as f:
                reader = make_reader(f)
                
                # 读取schemas
                summary = reader.get_summary()
                if summary and summary.schemas:
                    for schema_id, schema_obj in summary.schemas.items():
                        schema['schemas'][schema_id] = {
                            'name': schema_obj.name,
                            'encoding': schema_obj.encoding
                        }
                
                # 读取topics
                if summary and summary.channels:
                    for channel_id, channel in summary.channels.items():
                        schema['topics'][channel.topic] = {
                            'schema_id': channel.schema_id,
                            'message_count': channel.message_count if hasattr(channel, 'message_count') else 'unknown'
                        }
        
        except Exception as e:
            self.logger.error(f"分析MCAP文件失败: {e}")
            schema['errors'].append(str(e))
        
        return schema
    
    def _analyze_bson(self, bson_path: Path) -> Dict[str, Any]:
        """分析BSON文件的schema"""
        schema = {
            'format': 'bson',
            'file_path': str(bson_path),
            'documents': [],
            'errors': []
        }
        
        try:
            import bson
            
            # 如果是目录，查找BSON文件
            if bson_path.is_dir():
                bson_files = list(bson_path.glob("*.bson"))
                if not bson_files:
                    raise ValueError("未找到BSON文件")
                bson_path = bson_files[0]
            
            with open(bson_path, 'rb') as f:
                # 读取前几个文档进行分析
                for i in range(min(3, 10)):  # 最多读3个文档
                    try:
                        doc_bytes = f.read(4)
                        if len(doc_bytes) < 4:
                            break
                        
                        doc_size = int.from_bytes(doc_bytes, 'little')
                        remaining_bytes = f.read(doc_size - 4)
                        
                        doc = bson.decode(doc_bytes + remaining_bytes)
                        schema['documents'].append(self._analyze_json_structure(doc, max_depth=3))
                    
                    except Exception as e:
                        self.logger.warning(f"读取BSON文档失败: {e}")
                        break
        
        except ImportError:
            schema['errors'].append("未安装pymongo库，无法分析BSON文件")
        except Exception as e:
            self.logger.error(f"分析BSON文件失败: {e}")
            schema['errors'].append(str(e))
        
        return schema
    
    def generate_schema_report(self, schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成schema报告，合并多个episodes的分析结果
        
        Args:
            schemas: 多个episodes的schema列表
            
        Returns:
            合并后的schema报告
        """
        if not schemas:
            return {}
        
        report = {
            'num_episodes_analyzed': len(schemas),
            'format': schemas[0].get('format', 'unknown'),
            'common_fields': {},
            'inconsistencies': [],
            'summary': {}
        }
        
        # 提取公共字段
        if schemas[0].get('format') == 'h5':
            report['summary'] = self._summarize_h5_schemas(schemas)
        elif schemas[0].get('format') == 'json':
            report['summary'] = self._summarize_json_schemas(schemas)
        
        return report
    
    def _summarize_h5_schemas(self, schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """总结H5 schemas"""
        summary = {
            'observations': {},
            'actions': {},
            'images': {}
        }
        
        # 收集所有observations字段
        all_obs_fields = set()
        for schema in schemas:
            obs = schema.get('observations', {})
            for category in ['images', 'state', 'qpos', 'qvel', 'other']:
                if category in obs:
                    all_obs_fields.update(obs[category].keys())
        
        summary['observations']['all_fields'] = list(all_obs_fields)
        
        # 收集images信息
        for schema in schemas:
            obs = schema.get('observations', {})
            if 'images' in obs:
                summary['images'].update(obs['images'])
        
        # 收集actions信息
        for schema in schemas:
            actions = schema.get('actions', {})
            if actions:
                summary['actions'] = actions
                break  # 假设所有episodes的actions结构相同
        
        return summary
    
    def _summarize_json_schemas(self, schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """总结JSON schemas"""
        summary = {
            'common_fields': [],
            'all_fields': set()
        }
        
        for schema in schemas:
            fields = schema.get('fields', {})
            summary['all_fields'].update(fields.keys())
        
        summary['all_fields'] = list(summary['all_fields'])
        
        return summary


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    analyzer = SchemaAnalyzer()
    
    # 测试H5文件
    test_h5 = Path("/mnt/nas/synnas/docker/8agilex_cobot_decoupled_magic/pour_rice/episode_0.hdf5")
    if test_h5.exists():
        schema = analyzer.analyze_episode(test_h5, 'h5')
        print(json.dumps(schema, indent=2, default=str))

