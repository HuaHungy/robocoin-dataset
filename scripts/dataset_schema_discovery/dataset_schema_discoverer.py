"""
数据集Schema统一发现器

集成所有schema发现器，自动检测数据集格式并提取完整schema。
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import logging
import json

from h5_schema_discoverer import H5SchemaDiscoverer
from json_schema_discoverer import JSONSchemaDiscoverer
from mcap_schema_discoverer import MCAPSchemaDiscoverer
from mmk2_schema_discoverer import MMK2SchemaDiscoverer
from video_metadata_extractor import VideoMetadataExtractor


class DatasetSchemaDiscoverer:
    """统一的数据集Schema发现器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        
        # 初始化各个发现器
        self.h5_discoverer = H5SchemaDiscoverer(logger)
        self.json_discoverer = JSONSchemaDiscoverer(logger)
        self.mcap_discoverer = MCAPSchemaDiscoverer(logger)
        self.mmk2_discoverer = MMK2SchemaDiscoverer(logger)
        self.video_extractor = VideoMetadataExtractor(logger)
    
    def discover_dataset(
        self, 
        dataset_path: Path, 
        device_model: Optional[str] = None,
        num_episodes: int = 5
    ) -> Dict[str, Any]:
        """
        自动发现数据集的完整schema
        
        Args:
            dataset_path: 数据集路径
            device_model: 设备型号（如果已知）
            num_episodes: 采样多少个episodes分析
            
        Returns:
            完整的schema信息
        """
        if not dataset_path.exists():
            raise FileNotFoundError(f"Dataset path not found: {dataset_path}")
        
        self.logger.info("=" * 70)
        self.logger.info(f"开始分析数据集: {dataset_path}")
        if device_model:
            self.logger.info(f"Device Model: {device_model}")
        self.logger.info("=" * 70)
        
        schema = {
            'dataset_path': str(dataset_path),
            'device_model': device_model,
            'data_formats': {},
            'errors': []
        }
        
        # 1. 检测数据格式
        formats = self._detect_formats(dataset_path)
        schema['detected_formats'] = formats
        
        self.logger.info(f"\n检测到的数据格式: {', '.join(formats)}")
        
        # 2. 读取device_model_annotation（如果存在）
        annotation_path = dataset_path / 'device_model_annotation.yaml'
        if annotation_path.exists():
            try:
                import yaml
                with open(annotation_path, 'r', encoding='utf-8') as f:
                    annotation = yaml.safe_load(f)
                schema['device_model_annotation'] = annotation
                
                # 如果没有提供device_model，从annotation中获取
                if not device_model and annotation:
                    device_model = annotation.get('device_model')
                    schema['device_model'] = device_model
                    self.logger.info(f"从device_model_annotation.yaml读取: {device_model}")
            except Exception as e:
                self.logger.warning(f"无法读取device_model_annotation.yaml: {e}")
        
        # 3. 分析各种格式的数据
        self.logger.info("\n" + "=" * 70)
        self.logger.info("开始分析数据...")
        self.logger.info("=" * 70)
        
        # H5文件
        if 'h5' in formats:
            try:
                self.logger.info("\n[1/5] 分析H5文件...")
                h5_schema = self.h5_discoverer.discover_episode_dataset(
                    dataset_path, num_episodes
                )
                schema['data_formats']['h5'] = h5_schema
            except Exception as e:
                self.logger.error(f"H5分析失败: {e}")
                schema['errors'].append({'format': 'h5', 'error': str(e)})
        
        # JSON文件
        if 'json' in formats:
            try:
                self.logger.info("\n[2/5] 分析JSON文件...")
                json_schema = self.json_discoverer.discover_episode_dataset(
                    dataset_path, num_episodes
                )
                schema['data_formats']['json'] = json_schema
            except Exception as e:
                self.logger.error(f"JSON分析失败: {e}")
                schema['errors'].append({'format': 'json', 'error': str(e)})
        
        # MCAP文件
        if 'mcap' in formats:
            try:
                self.logger.info("\n[3/5] 分析MCAP文件...")
                mcap_schema = self.mcap_discoverer.discover_episode_dataset(
                    dataset_path, num_episodes
                )
                schema['data_formats']['mcap'] = mcap_schema
            except Exception as e:
                self.logger.error(f"MCAP分析失败: {e}")
                schema['errors'].append({'format': 'mcap', 'error': str(e)})
        
        # BSON文件（MMK2）
        if 'bson' in formats:
            try:
                self.logger.info("\n[4/5] 分析BSON文件（MMK2）...")
                bson_schema = self.mmk2_discoverer.discover_episode_dataset(
                    dataset_path, num_episodes
                )
                schema['data_formats']['bson'] = bson_schema
            except Exception as e:
                self.logger.error(f"BSON分析失败: {e}")
                schema['errors'].append({'format': 'bson', 'error': str(e)})
        
        # 视频文件
        if 'video' in formats:
            try:
                self.logger.info("\n[5/5] 分析视频文件...")
                video_schema = self.video_extractor.discover_episode_dataset(
                    dataset_path, num_episodes
                )
                schema['data_formats']['video'] = video_schema
            except Exception as e:
                self.logger.error(f"视频分析失败: {e}")
                schema['errors'].append({'format': 'video', 'error': str(e)})
        
        # 4. 生成摘要
        schema['summary'] = self._generate_summary(schema)
        
        self.logger.info("\n" + "=" * 70)
        self.logger.info("分析完成！")
        self.logger.info("=" * 70)
        
        return schema
    
    def _detect_formats(self, dataset_path: Path) -> List[str]:
        """检测数据集包含哪些数据格式"""
        formats = []
        
        # H5/HDF5
        if list(dataset_path.rglob("*.h5")) or list(dataset_path.rglob("*.hdf5")):
            formats.append('h5')
        
        # JSON
        if list(dataset_path.rglob("*.json")):
            formats.append('json')
        
        # MCAP
        if list(dataset_path.rglob("*.mcap")):
            formats.append('mcap')
        
        # BSON (MMK2)
        if list(dataset_path.rglob("*.bson")):
            formats.append('bson')
        
        # 视频（MP4, AVI, MOV等）
        video_extensions = ['*.mp4', '*.avi', '*.mov', '*.mkv']
        for ext in video_extensions:
            if list(dataset_path.rglob(ext)):
                formats.append('video')
                break
        
        # Rosbag
        if list(dataset_path.rglob("*.bag")):
            formats.append('rosbag')
        
        return formats
    
    def _generate_summary(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """生成分析摘要"""
        summary = {
            'dataset_path': schema['dataset_path'],
            'device_model': schema.get('device_model', 'unknown'),
            'detected_formats': schema.get('detected_formats', []),
            'analysis_success': {},
            'total_errors': len(schema.get('errors', []))
        }
        
        # 统计各格式的分析结果
        for fmt, data in schema.get('data_formats', {}).items():
            if data:
                summary['analysis_success'][fmt] = True
            else:
                summary['analysis_success'][fmt] = False
        
        # 提取关键信息
        data_formats = schema.get('data_formats', {})
        
        # H5信息
        if 'h5' in data_formats and data_formats['h5']:
            h5_data = data_formats['h5']
            summary['h5_summary'] = {
                'total_files': h5_data.get('total_h5_files', 0),
                'sampled_files': h5_data.get('sampled_files', 0),
                'consistency': h5_data.get('consistency', 'unknown')
            }
        
        # 视频信息
        if 'video' in data_formats and data_formats['video']:
            video_data = data_formats['video']
            summary['video_summary'] = {
                'total_files': video_data.get('total_video_files', 0),
                'camera_groups': list(video_data.get('camera_groups', {}).keys())
            }
        
        # MCAP信息
        if 'mcap' in data_formats and data_formats['mcap']:
            mcap_data = data_formats['mcap']
            summary['mcap_summary'] = {
                'total_files': mcap_data.get('total_mcap_files', 0),
                'topics': list(mcap_data.get('topics', {}).keys())
            }
        
        return summary
    
    def save_schema(self, schema: Dict[str, Any], output_path: Path):
        """保存schema到文件"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"✓ Schema已保存到: {output_path}")


def main():
    """测试Dataset Schema Discoverer"""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='数据集Schema自动发现工具')
    parser.add_argument('dataset_path', help='数据集路径')
    parser.add_argument('--device-model', help='设备型号（可选）')
    parser.add_argument('--num-episodes', type=int, default=5, help='采样episodes数量（默认5）')
    parser.add_argument('--output', '-o', help='输出文件路径（可选）')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    
    # 设置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # 运行分析
    discoverer = DatasetSchemaDiscoverer()
    schema = discoverer.discover_dataset(
        Path(args.dataset_path),
        device_model=args.device_model,
        num_episodes=args.num_episodes
    )
    
    # 输出结果
    if args.output:
        discoverer.save_schema(schema, Path(args.output))
    else:
        # 打印到stdout
        print("\n" + "=" * 70)
        print("Schema Analysis Result")
        print("=" * 70)
        print(json.dumps(schema['summary'], indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

