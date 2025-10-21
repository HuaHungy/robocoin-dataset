"""
视频元数据提取器

提取视频文件的元数据信息（分辨率、帧率、编码格式、帧数等）
"""

import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
import json


class VideoMetadataExtractor:
    """视频元数据提取器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def extract_metadata(self, video_path: Path) -> Dict[str, Any]:
        """
        提取单个视频文件的元数据
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            元数据字典
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        metadata = {
            'file_path': str(video_path),
            'file_size_mb': video_path.stat().st_size / 1024 / 1024,
        }
        
        # 优先使用ffprobe（更准确）
        try:
            metadata.update(self._extract_with_ffprobe(video_path))
            metadata['extraction_method'] = 'ffprobe'
        except Exception as e:
            self.logger.warning(f"ffprobe failed, fallback to cv2: {e}")
            try:
                metadata.update(self._extract_with_cv2(video_path))
                metadata['extraction_method'] = 'cv2'
            except Exception as e2:
                self.logger.error(f"cv2 also failed: {e2}")
                metadata['error'] = str(e2)
                metadata['extraction_method'] = 'failed'
        
        return metadata
    
    def _extract_with_ffprobe(self, video_path: Path) -> Dict[str, Any]:
        """使用ffprobe提取元数据"""
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 
            'stream=width,height,r_frame_rate,nb_frames,codec_name,pix_fmt,bit_rate,duration',
            '-of', 'json',
            str(video_path)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )
        
        data = json.loads(result.stdout)
        stream = data.get('streams', [{}])[0]
        
        metadata = {
            'width': stream.get('width'),
            'height': stream.get('height'),
            'codec': stream.get('codec_name'),
            'pixel_format': stream.get('pix_fmt'),
            'bit_rate': stream.get('bit_rate'),
            'duration': stream.get('duration')
        }
        
        # 解析帧率
        fps_str = stream.get('r_frame_rate', '0/1')
        if '/' in fps_str:
            num, den = fps_str.split('/')
            metadata['fps'] = float(num) / float(den) if float(den) != 0 else 0
        else:
            metadata['fps'] = float(fps_str)
        
        # 获取帧数
        # 优先使用nb_frames，如果没有则用duration * fps估算
        if 'nb_frames' in stream:
            try:
                metadata['frame_count'] = int(stream['nb_frames'])
                metadata['frame_count_source'] = 'nb_frames'
            except ValueError:
                metadata['frame_count'] = None
        
        if metadata.get('frame_count') is None and metadata.get('duration') and metadata.get('fps'):
            try:
                metadata['frame_count'] = int(float(metadata['duration']) * metadata['fps'])
                metadata['frame_count_source'] = 'duration_x_fps_estimate'
            except:
                pass
        
        # 如果还是没有，用count_packets获取
        if metadata.get('frame_count') is None:
            try:
                count_cmd = [
                    'ffprobe',
                    '-v', 'error',
                    '-select_streams', 'v:0',
                    '-count_packets',
                    '-show_entries', 'stream=nb_read_packets',
                    '-of', 'csv=p=0',
                    str(video_path)
                ]
                count_result = subprocess.run(
                    count_cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30
                )
                metadata['frame_count'] = int(count_result.stdout.strip())
                metadata['frame_count_source'] = 'nb_read_packets'
            except:
                pass
        
        return metadata
    
    def _extract_with_cv2(self, video_path: Path) -> Dict[str, Any]:
        """使用OpenCV提取元数据"""
        try:
            import cv2
        except ImportError:
            raise ImportError("opencv-python not installed")
        
        cap = cv2.VideoCapture(str(video_path))
        
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video: {video_path}")
        
        metadata = {
            'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            'fps': cap.get(cv2.CAP_PROP_FPS),
            'frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            'codec': int(cap.get(cv2.CAP_PROP_FOURCC)),
            'frame_count_source': 'cv2.CAP_PROP_FRAME_COUNT'
        }
        
        cap.release()
        
        return metadata
    
    def discover_episode_dataset(
        self, 
        dataset_path: Path, 
        num_episodes: int = 5,
        video_pattern: str = "*.mp4"
    ) -> Dict[str, Any]:
        """
        发现整个数据集的视频元数据（多个episodes）
        
        Args:
            dataset_path: 数据集路径
            num_episodes: 采样多少个episodes分析
            video_pattern: 视频文件匹配模式
            
        Returns:
            汇总的元数据信息
        """
        # 查找视频文件
        video_files = sorted(dataset_path.rglob(video_pattern))
        
        if not video_files:
            # 尝试其他视频格式
            for pattern in ['*.avi', '*.mov', '*.mkv']:
                video_files = sorted(dataset_path.rglob(pattern))
                if video_files:
                    break
        
        if not video_files:
            raise ValueError(f"No video files found in {dataset_path}")
        
        self.logger.info(f"找到 {len(video_files)} 个视频文件")
        
        # 按摄像头分组（如果文件名包含摄像头名称）
        camera_groups = self._group_by_camera(video_files)
        
        result = {
            'total_video_files': len(video_files),
            'camera_groups': {}
        }
        
        # 对每个摄像头组采样分析
        for camera_name, files in camera_groups.items():
            self.logger.info(f"分析摄像头: {camera_name} ({len(files)} 个文件)")
            
            sampled_files = files[:min(num_episodes, len(files))]
            metadata_list = []
            
            for video_file in sampled_files:
                try:
                    metadata = self.extract_metadata(video_file)
                    metadata_list.append(metadata)
                    self.logger.info(f"  ✓ {video_file.name}")
                except Exception as e:
                    self.logger.error(f"  ✗ {video_file.name}: {e}")
            
            # 检查一致性
            result['camera_groups'][camera_name] = {
                'total_files': len(files),
                'sampled_files': len(metadata_list),
                'metadata_samples': metadata_list,
                'consistency': self._check_video_consistency(metadata_list)
            }
        
        return result
    
    def _group_by_camera(self, video_files: List[Path]) -> Dict[str, List[Path]]:
        """根据文件名或路径将视频文件按摄像头分组"""
        groups = {}
        
        for video_file in video_files:
            # 尝试从文件名或父目录提取摄像头名称
            camera_name = self._infer_camera_name(video_file)
            
            if camera_name not in groups:
                groups[camera_name] = []
            groups[camera_name].append(video_file)
        
        return groups
    
    def _infer_camera_name(self, video_path: Path) -> str:
        """从文件路径推断摄像头名称"""
        # 常见的摄像头名称关键词
        camera_keywords = [
            'cam_high', 'cam_low', 'cam_left', 'cam_right',
            'wrist', 'head', 'chest', 'top', 'side',
            'camera', 'rgb', 'depth',
            'left_wrist', 'right_wrist', 'high_up', 'high_down'
        ]
        
        # 检查文件名
        filename_lower = video_path.stem.lower()
        for keyword in camera_keywords:
            if keyword in filename_lower:
                return keyword
        
        # 检查父目录名
        parent_lower = video_path.parent.name.lower()
        for keyword in camera_keywords:
            if keyword in parent_lower:
                return keyword
        
        # 如果都没有，使用父目录名或'unknown'
        return video_path.parent.name if video_path.parent.name else 'unknown'
    
    def _check_video_consistency(self, metadata_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """检查多个视频的元数据一致性"""
        if not metadata_list:
            return {'status': 'no_data'}
        
        if len(metadata_list) == 1:
            return {'status': 'single_file'}
        
        # 检查关键属性的一致性
        properties_to_check = ['width', 'height', 'fps', 'codec']
        
        consistency = {
            'status': 'consistent',
            'variations': {}
        }
        
        base = metadata_list[0]
        for prop in properties_to_check:
            base_value = base.get(prop)
            values = [m.get(prop) for m in metadata_list]
            unique_values = list(set(values))
            
            if len(unique_values) > 1:
                consistency['status'] = 'inconsistent'
                consistency['variations'][prop] = {
                    'base_value': base_value,
                    'all_values': unique_values,
                    'count': {v: values.count(v) for v in unique_values}
                }
        
        return consistency


def main():
    """测试Video Metadata Extractor"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python video_metadata_extractor.py <video_file_or_dataset_path>")
        sys.exit(1)
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
    path = Path(sys.argv[1])
    extractor = VideoMetadataExtractor()
    
    if path.is_file() and path.suffix in ['.mp4', '.avi', '.mov', '.mkv']:
        # 分析单个文件
        metadata = extractor.extract_metadata(path)
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
    
    elif path.is_dir():
        # 分析整个数据集
        metadata = extractor.discover_episode_dataset(path, num_episodes=5)
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
    
    else:
        print(f"错误: {path} 不是有效的视频文件或目录")
        sys.exit(1)


if __name__ == '__main__':
    main()

