"""
MCAP文件Schema发现器

自动分析MCAP文件的数据结构，提取topics、消息类型等信息。
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import logging


class MCAPSchemaDiscoverer:
    """MCAP文件Schema发现器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def discover_file(self, mcap_path: Path, max_messages_per_topic: int = 10) -> Dict[str, Any]:
        """
        发现单个MCAP文件的schema
        
        Args:
            mcap_path: MCAP文件路径
            max_messages_per_topic: 每个topic最多分析多少条消息
            
        Returns:
            schema字典
        """
        if not mcap_path.exists():
            raise FileNotFoundError(f"MCAP file not found: {mcap_path}")
        
        try:
            from mcap.reader import make_reader
        except ImportError:
            raise ImportError(
                "mcap library not installed. Please run: pip install mcap"
            )
        
        schema = {
            'file_path': str(mcap_path),
            'file_size_mb': mcap_path.stat().st_size / 1024 / 1024,
            'topics': {},
            'total_messages': 0
        }
        
        # 统计每个topic的消息
        topic_message_counts = {}
        topic_samples = {}
        
        with open(mcap_path, 'rb') as f:
            reader = make_reader(f)
            
            # 读取schema信息
            for schema_info in reader.iter_schemas():
                self.logger.debug(f"Schema: {schema_info.name} (id={schema_info.id})")
            
            # 读取消息
            for msg_idx, (schema_msg, channel, message) in enumerate(reader.iter_messages()):
                topic = channel.topic
                
                # 统计消息数量
                topic_message_counts[topic] = topic_message_counts.get(topic, 0) + 1
                schema['total_messages'] += 1
                
                # 采样消息内容（每个topic最多采样N条）
                if topic not in topic_samples:
                    topic_samples[topic] = []
                
                if len(topic_samples[topic]) < max_messages_per_topic:
                    topic_samples[topic].append({
                        'timestamp': message.log_time,
                        'sequence': message.sequence,
                        'schema_id': channel.schema_id,
                        'schema_name': schema_msg.name if schema_msg else 'unknown',
                        'message_encoding': schema_msg.encoding if schema_msg else 'unknown',
                        'data_size': len(message.data)
                    })
        
        # 整理topic信息
        for topic, count in topic_message_counts.items():
            schema['topics'][topic] = {
                'message_count': count,
                'samples': topic_samples.get(topic, [])
            }
            
            # 尝试解析第一条消息以获取字段信息
            if topic_samples.get(topic):
                first_sample = topic_samples[topic][0]
                schema['topics'][topic]['schema_name'] = first_sample['schema_name']
                schema['topics'][topic]['message_encoding'] = first_sample['message_encoding']
        
        return schema
    
    def discover_episode_dataset(
        self, 
        dataset_path: Path, 
        num_episodes: int = 5
    ) -> Dict[str, Any]:
        """
        发现整个数据集的MCAP schema（多个episodes）
        
        Args:
            dataset_path: 数据集路径
            num_episodes: 采样多少个episodes分析
            
        Returns:
            汇总的schema信息
        """
        # 查找MCAP文件
        mcap_files = sorted(dataset_path.rglob("*.mcap"))
        
        if not mcap_files:
            raise ValueError(f"No MCAP files found in {dataset_path}")
        
        self.logger.info(f"找到 {len(mcap_files)} 个MCAP文件")
        
        # 采样分析
        sampled_files = mcap_files[:min(num_episodes, len(mcap_files))]
        schemas = []
        
        for mcap_file in sampled_files:
            try:
                schema = self.discover_file(mcap_file)
                schemas.append(schema)
                self.logger.info(f"✓ 分析完成: {mcap_file.name}")
            except Exception as e:
                self.logger.error(f"✗ 分析失败 {mcap_file.name}: {e}")
        
        # 合并schema（检查一致性）
        merged_schema = self._merge_schemas(schemas)
        merged_schema['total_mcap_files'] = len(mcap_files)
        merged_schema['sampled_files'] = len(schemas)
        
        return merged_schema
    
    def _merge_schemas(self, schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """合并多个schema，检查一致性"""
        if not schemas:
            return {}
        
        if len(schemas) == 1:
            return schemas[0]
        
        # 收集所有topic
        all_topics = set()
        for schema in schemas:
            all_topics.update(schema.get('topics', {}).keys())
        
        merged = {
            'topics': {},
            'consistency': 'checking',
            'variations': []
        }
        
        # 检查每个topic在所有文件中是否存在
        all_consistent = True
        for topic in all_topics:
            topic_info = {
                'present_in_all': True,
                'message_counts': [],
                'schema_names': set()
            }
            
            for schema in schemas:
                if topic in schema.get('topics', {}):
                    topic_data = schema['topics'][topic]
                    topic_info['message_counts'].append(topic_data['message_count'])
                    topic_info['schema_names'].add(topic_data.get('schema_name', 'unknown'))
                else:
                    topic_info['present_in_all'] = False
                    all_consistent = False
            
            # 检查schema_name一致性
            if len(topic_info['schema_names']) > 1:
                all_consistent = False
                topic_info['warning'] = f"schema_name不一致: {topic_info['schema_names']}"
            
            topic_info['schema_names'] = list(topic_info['schema_names'])
            merged['topics'][topic] = topic_info
        
        merged['consistency'] = 'consistent' if all_consistent else 'inconsistent'
        
        # 记录详细差异
        if not all_consistent:
            for i, schema in enumerate(schemas):
                schema_topics = set(schema.get('topics', {}).keys())
                if schema_topics != all_topics:
                    merged['variations'].append({
                        'file_index': i,
                        'file_path': schema['file_path'],
                        'missing_topics': list(all_topics - schema_topics),
                        'extra_topics': list(schema_topics - all_topics)
                    })
        
        return merged


def main():
    """测试MCAP Schema Discoverer"""
    import sys
    import json
    
    if len(sys.argv) < 2:
        print("Usage: python mcap_schema_discoverer.py <mcap_file_or_dataset_path>")
        sys.exit(1)
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
    path = Path(sys.argv[1])
    discoverer = MCAPSchemaDiscoverer()
    
    if path.is_file() and path.suffix == '.mcap':
        # 分析单个文件
        schema = discoverer.discover_file(path)
        print(json.dumps(schema, indent=2, ensure_ascii=False))
    
    elif path.is_dir():
        # 分析整个数据集
        schema = discoverer.discover_episode_dataset(path, num_episodes=5)
        print(json.dumps(schema, indent=2, ensure_ascii=False))
    
    else:
        print(f"错误: {path} 不是有效的MCAP文件或目录")
        sys.exit(1)


if __name__ == '__main__':
    main()

