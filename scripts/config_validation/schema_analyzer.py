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
        elif "rosbag" in format_type:
            return self._analyze_rosbag(episode_path)
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
    
    def _analyze_rosbag(self, bag_path: Path) -> Dict[str, Any]:
        """分析ROS Bag文件的schema
        
        Args:
            bag_path: ROS bag文件路径
            
        Returns:
            Schema信息字典
        """
        schema = {
            'format': 'rosbag',
            'file_path': str(bag_path),
            'observations': {'state': {}, 'images': {}, 'other': {}},
            'actions': {},
            'topics': {},
            'errors': []
        }
        
        try:
            from rosbags.highlevel import AnyReader
            
            self.logger.info(f"分析ROS Bag文件: {bag_path}")
            
            # 读取bag文件并分析topics
            with AnyReader([bag_path]) as reader:
                # 获取所有topics的连接信息
                connections = reader.connections
                
                # 分析每个topic
                for connection in connections:
                    topic_name = connection.topic
                    msg_type = connection.msgtype
                    
                    # 初始化topic信息
                    topic_info = {
                        'topic': topic_name,
                        'msg_type': msg_type,
                        'msg_count': 0,
                        'fields': {},
                        'sample_values': []
                    }
                    
                    schema['topics'][topic_name] = topic_info
                
                # 读取消息并采样分析
                topic_message_counts = {}
                topic_samples = {}  # 存储每个topic的采样消息
                
                for connection, timestamp, rawdata in reader.messages():
                    topic_name = connection.topic
                    
                    # 计数
                    if topic_name not in topic_message_counts:
                        topic_message_counts[topic_name] = 0
                    topic_message_counts[topic_name] += 1
                    
                    # 采样（每个topic最多采样3条消息）
                    if topic_name not in topic_samples:
                        topic_samples[topic_name] = []
                    
                    if len(topic_samples[topic_name]) < 3:
                        # 反序列化消息
                        msg = reader.deserialize(rawdata, connection.msgtype)
                        topic_samples[topic_name].append(msg)
                
                # 更新消息计数
                for topic_name, count in topic_message_counts.items():
                    if topic_name in schema['topics']:
                        schema['topics'][topic_name]['msg_count'] = count
                
                # 分析采样的消息
                for topic_name, messages in topic_samples.items():
                    if topic_name not in schema['topics']:
                        continue
                    
                    topic_info = schema['topics'][topic_name]
                    
                    # 分析消息结构
                    if messages:
                        first_msg = messages[0]
                        fields_info = self._analyze_ros_message_structure(first_msg)
                        topic_info['fields'] = fields_info
                        
                        # 分类到observations/actions
                        self._categorize_ros_topic(topic_name, topic_info, schema)
            
            self.logger.info(f"ROS Bag分析完成: 共{len(schema['topics'])}个topics")
            
        except ImportError as e:
            error_msg = "rosbags库未安装。请运行: uv pip install rosbags"
            self.logger.error(error_msg)
            schema['errors'].append(error_msg)
        except Exception as e:
            self.logger.error(f"分析ROS Bag文件失败: {e}")
            schema['errors'].append(str(e))
        
        return schema
    
    def _analyze_ros_message_structure(self, msg: Any, depth: int = 0, max_depth: int = 3) -> Dict[str, Any]:
        """递归分析ROS消息结构
        
        Args:
            msg: ROS消息对象
            depth: 当前递归深度
            max_depth: 最大递归深度
            
        Returns:
            消息字段信息
        """
        if depth >= max_depth:
            return {'_truncated': True}
        
        fields = {}
        
        # 检查消息是否有__slots__属性（ROS消息的特征）
        if hasattr(msg, '__slots__'):
            for field_name in msg.__slots__:
                try:
                    value = getattr(msg, field_name, None)
                    
                    if value is None:
                        fields[field_name] = {'type': 'None', 'value': None}
                    elif isinstance(value, (int, float)):
                        fields[field_name] = {
                            'type': type(value).__name__,
                            'value': value
                        }
                    elif isinstance(value, str):
                        fields[field_name] = {
                            'type': 'str',
                            'length': len(value)
                        }
                    elif isinstance(value, (list, tuple)):
                        if value and len(value) > 0:
                            # 分析数组/列表
                            item_type = type(value[0]).__name__
                            fields[field_name] = {
                                'type': 'array',
                                'length': len(value),
                                'item_type': item_type,
                                'shape': (len(value),)
                            }
                            
                            # 如果是数值数组，计算统计信息
                            if isinstance(value[0], (int, float)):
                                import numpy as np
                                arr = np.array(value)
                                fields[field_name].update({
                                    'min': float(arr.min()),
                                    'max': float(arr.max()),
                                    'mean': float(arr.mean()),
                                    'std': float(arr.std()),
                                    'is_all_zero': bool(np.all(arr == 0)),
                                    'non_zero_count': int(np.count_nonzero(arr))
                                })
                        else:
                            fields[field_name] = {
                                'type': 'array',
                                'length': 0
                            }
                    elif hasattr(value, '__slots__'):
                        # 嵌套的ROS消息
                        fields[field_name] = {
                            'type': 'nested_message',
                            'fields': self._analyze_ros_message_structure(value, depth + 1, max_depth)
                        }
                    else:
                        fields[field_name] = {
                            'type': type(value).__name__
                        }
                
                except Exception as e:
                    fields[field_name] = {'error': str(e)}
        
        return fields
    
    def _categorize_ros_topic(self, topic_name: str, topic_info: Dict[str, Any], schema: Dict[str, Any]):
        """将ROS topic分类到observations/actions
        
        Args:
            topic_name: Topic名称
            topic_info: Topic信息
            schema: Schema字典
        """
        # 根据topic名称判断类别
        topic_lower = topic_name.lower()
        
        # 图像topic
        if any(keyword in topic_lower for keyword in ['image', 'camera', 'rgb', 'depth']):
            camera_name = topic_name.split('/')[-1] if '/' in topic_name else topic_name
            schema['observations']['images'][camera_name] = {
                'topic': topic_name,
                'msg_type': topic_info.get('msg_type'),
                'msg_count': topic_info.get('msg_count', 0)
            }
        
        # 状态/观测topic
        elif any(keyword in topic_lower for keyword in ['state', 'joint', 'feedback', 'pose', 'position']):
            # 提取字段信息
            fields = topic_info.get('fields', {})
            
            # 检查是否有位置/速度/力矩等字段
            for field_name, field_info in fields.items():
                if isinstance(field_info, dict):
                    full_path = f"{topic_name}/{field_name}"
                    
                    # 保存到state
                    schema['observations']['state'][full_path] = {
                        'topic': topic_name,
                        'field': field_name,
                        **field_info
                    }
        
        # 动作topic
        elif 'action' in topic_lower or 'command' in topic_lower or 'cmd' in topic_lower:
            fields = topic_info.get('fields', {})
            
            for field_name, field_info in fields.items():
                if isinstance(field_info, dict):
                    full_path = f"{topic_name}/{field_name}"
                    
                    schema['actions'][full_path] = {
                        'topic': topic_name,
                        'field': field_name,
                        **field_info
                    }
        
        # 其他topic
        else:
            schema['observations']['other'][topic_name] = topic_info
    
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
    
    def analyze_with_converter(
        self,
        converter: Any,
        num_episodes: int = 1
    ) -> Dict[str, Any]:
        """
        使用converter实例分析数据schema
        
        这是新的统一接口，直接调用converter的方法来定位和加载数据，
        避免重复实现episode定位和数据加载逻辑。
        
        Args:
            converter: Converter实例（已初始化）
            num_episodes: 分析的episode数量
        
        Returns:
            Schema字典，包含observations/actions结构
        """
        self.logger.info(f"使用converter分析数据schema: {converter.__class__.__name__}")
        
        schema = {
            'format': converter.__class__.__name__,
            'observations': {'images': {}, 'state': {}},
            'actions': {},
            'episodes_analyzed': 0,
            'errors': []
        }
        
        try:
            # 1. 定位episodes（调用converter的方法）
            episodes = self._get_converter_episodes(converter)
            
            if not episodes:
                raise ValueError("未找到任何episodes")
            
            self.logger.info(f"找到 {len(episodes)} 个episodes，将分析前 {num_episodes} 个")
            
            # 2. 分析指定数量的episodes
            episodes_to_analyze = episodes[:num_episodes]
            
            for ep_idx, episode_info in enumerate(episodes_to_analyze):
                try:
                    self.logger.debug(f"分析episode {ep_idx}: {episode_info}")
                    
                    # 调用converter的数据加载方法
                    # 注意：不同converter有不同的内部API，这里需要适配
                    episode_schema = self._extract_episode_schema_from_converter(
                        converter, episode_info, ep_idx
                    )
                    
                    # 合并schema（第一个episode的结构作为基准）
                    if schema['episodes_analyzed'] == 0:
                        schema['observations'] = episode_schema.get('observations', {})
                        schema['actions'] = episode_schema.get('actions', {})
                    
                    schema['episodes_analyzed'] += 1
                    
                except Exception as e:
                    self.logger.error(f"分析episode {ep_idx} 失败: {e}")
                    schema['errors'].append(f"Episode {ep_idx}: {str(e)}")
            
        except Exception as e:
            self.logger.error(f"使用converter分析schema失败: {e}")
            schema['errors'].append(str(e))
        
        return schema
    
    def _get_converter_episodes(self, converter: Any) -> List[Any]:
        """
        从converter获取episode列表
        
        不同converter有不同的方式获取episodes：
        - H5 converter: task_episode_h5file_paths
        - H5+JPG, JPG+JSON converter: _get_all_episode_dirs()
        - H5+MP4 converter: _get_all_episode_h5_files()
        - MCAP converter: _get_all_mcap_files()
        - 其他: _get_task_episodes_num()
        """
        episodes = []
        
        # 尝试不同的converter API（按优先级顺序）
        
        # 1. H5单文件格式: task_episode_h5file_paths
        if hasattr(converter, 'task_episode_h5file_paths'):
            # H5 converter
            for task_path, h5_files in converter.task_episode_h5file_paths.items():
                for ep_idx, h5_file in enumerate(h5_files):
                    episodes.append({
                        'task_path': task_path,
                        'episode_path': h5_file,
                        'episode_idx': ep_idx,
                        'type': 'h5_file'
                    })
        
        # 2. JPG+JSON, H5+JPG格式: _get_all_episode_dirs()
        elif hasattr(converter, '_get_all_episode_dirs'):
            for task_path in converter.path_task_dict.keys():
                ep_dirs = converter._get_all_episode_dirs(task_path)
                for ep_idx, ep_dir in enumerate(ep_dirs):
                    episodes.append({
                        'task_path': task_path,
                        'episode_path': ep_dir,
                        'episode_idx': ep_idx,
                        'type': 'episode_dir'
                    })
        
        # 3. H5+MP4格式: _get_all_episode_h5_files()
        elif hasattr(converter, '_get_all_episode_h5_files'):
            for task_path in converter.path_task_dict.keys():
                h5_files = converter._get_all_episode_h5_files(task_path)
                for ep_idx, h5_file in enumerate(h5_files):
                    episodes.append({
                        'task_path': task_path,
                        'episode_path': h5_file,
                        'episode_idx': ep_idx,
                        'type': 'h5_mp4'
                    })
        
        # 4. MCAP格式: _get_all_mcap_files()
        elif hasattr(converter, '_get_all_mcap_files'):
            for task_path in converter.path_task_dict.keys():
                mcap_files = converter._get_all_mcap_files(task_path)
                for ep_idx, mcap_file in enumerate(mcap_files):
                    episodes.append({
                        'task_path': task_path,
                        'episode_path': mcap_file,
                        'episode_idx': ep_idx,
                        'type': 'mcap'
                    })
        
        # 5. 通用方法：使用_get_task_episodes_num
        elif hasattr(converter, 'path_task_dict') and hasattr(converter, '_get_task_episodes_num'):
            for task_path in converter.path_task_dict.keys():
                num_episodes = converter._get_task_episodes_num(task_path)
                for ep_idx in range(num_episodes):
                    episodes.append({
                        'task_path': task_path,
                        'episode_idx': ep_idx,
                        'type': 'indexed'
                    })
        
        else:
            self.logger.warning(
                f"⚠️ Converter {type(converter).__name__} 没有已知的episode定位方法。"
                f"可用属性: {[attr for attr in dir(converter) if not attr.startswith('_')][:10]}"
            )
        
        self.logger.info(f"从converter获取到 {len(episodes)} 个episodes")
        return episodes
    
    def _extract_episode_schema_from_converter(
        self,
        converter: Any,
        episode_info: Dict[str, Any],
        ep_idx: int
    ) -> Dict[str, Any]:
        """
        从converter提取单个episode的schema
        
        这里只提取结构信息（字段名、shape），不加载完整数据
        """
        schema = {
            'observations': {'images': {}, 'state': {}},
            'actions': {}
        }
        
        # 根据converter类型，调用不同的方法
        # 注意：这里我们只读取第一帧来获取schema信息
        
        task_path = episode_info.get('task_path')
        episode_idx = episode_info.get('episode_idx', ep_idx)
        
        try:
            # 尝试获取帧数
            if hasattr(converter, '_get_episode_frames_num'):
                self.logger.debug(f"         → 获取episode帧数...")
                frames_num = converter._get_episode_frames_num(task_path, episode_idx)
                self.logger.debug(f"         → 帧数: {frames_num}")
                if frames_num <= 0:
                    raise ValueError(f"Episode {episode_idx} 无有效帧")
                
                # 获取配置中的第一个sub_state的args作为示例
                sample_state_args = {}
                if hasattr(converter, 'config') and 'features' in converter.config:
                    state_config = converter.config.get('features', {}).get('observation', {}).get('state', {})
                    sub_states = state_config.get('sub_state', [])
                    if sub_states and len(sub_states) > 0:
                        sample_state_args = sub_states[0].get('args', {})
                
                # 只读取第一帧
                if hasattr(converter, '_get_frame_sub_states') and sample_state_args:
                    # 获取state数据（使用第一个sub_state的args）
                    state_data = converter._get_frame_sub_states(task_path, episode_idx, 0, sample_state_args)
                    if state_data is not None:
                        schema['observations']['state'] = {
                            'shape': np.array(state_data).shape if isinstance(state_data, (list, np.ndarray)) else None,
                            'dtype': str(np.array(state_data).dtype) if isinstance(state_data, (list, np.ndarray)) else None
                        }
                
                # 获取action数据
                sample_action_args = {}
                if hasattr(converter, 'config') and 'features' in converter.config:
                    action_config = converter.config.get('features', {}).get('action', {})
                    sub_actions = action_config.get('sub_action', [])
                    if sub_actions and len(sub_actions) > 0:
                        sample_action_args = sub_actions[0].get('args', {})
                
                if hasattr(converter, '_get_frame_sub_actions') and sample_action_args:
                    action_data = converter._get_frame_sub_actions(task_path, episode_idx, 0, sample_action_args)
                    if action_data is not None:
                        schema['actions'] = {
                            'shape': np.array(action_data).shape if isinstance(action_data, (list, np.ndarray)) else None,
                            'dtype': str(np.array(action_data).dtype) if isinstance(action_data, (list, np.ndarray)) else None
                        }
                
                # 获取images（暂时简化，只记录有图片）
                if hasattr(converter, 'config') and 'features' in converter.config:
                    images_config = converter.config.get('features', {}).get('observation', {}).get('images', [])
                    for img_cfg in images_config:
                        cam_name = img_cfg.get('cam_name', 'unknown')
                        schema['observations']['images'][cam_name] = {
                            'exists': True
                        }
            
        except Exception as e:
            self.logger.warning(f"提取episode schema失败: {e}")
            raise
        
        return schema


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    analyzer = SchemaAnalyzer()
    
    # 测试H5文件
    test_h5 = Path("/mnt/nas/synnas/docker/8agilex_cobot_decoupled_magic/pour_rice/episode_0.hdf5")
    if test_h5.exists():
        schema = analyzer.analyze_episode(test_h5, 'h5')
        print(json.dumps(schema, indent=2, default=str))

