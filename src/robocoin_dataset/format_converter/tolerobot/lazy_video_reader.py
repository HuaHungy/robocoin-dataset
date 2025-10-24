"""
延迟加载视频读取器

解决视频转换器的内存问题：
- 问题：当前实现会将整个episode的所有视频帧加载到内存（100帧 × 3相机 × 1MB = 300MB/episode）
- 方案：延迟加载，按需读取单帧，内存占用降至 ~3MB
- 性能：从300MB → 3MB，100x内存优化

新增：自动视频重编码
- 检测视频编码兼容性问题（如AV1编码）
- 自动调用ffmpeg重编码为H.264
- 使用临时文件，不影响原始数据
"""

import cv2
from pathlib import Path
from typing import Optional, Union
import numpy as np
import logging


class LazyVideoReader:
    """
    延迟加载视频读取器
    
    特性：
    - 按需读取：只在访问时读取指定帧，不预加载整个视频
    - 缓存当前帧：避免重复读取同一帧
    - 智能跳转：顺序访问时不跳转，非顺序访问时才seek
    - 自动释放：使用完毕自动释放资源
    
    使用方式：
        reader = LazyVideoReader(video_path)
        frame = reader[10]  # 读取第10帧
        frame = reader[11]  # 顺序读取，无需seek，快速
        
    兼容性：
        可直接替换list<numpy.ndarray>使用，支持索引访问
    """
    
    def __init__(
        self, 
        video_path: Union[Path, str],
        logger: Optional[logging.Logger] = None,
        convert_to_rgb: bool = True,
        auto_reencode: bool = False
    ):
        """
        初始化延迟视频读取器
        
        Args:
            video_path: 视频文件路径
            logger: 日志记录器（可选）
            convert_to_rgb: 是否自动将BGR转换为RGB（默认True）
            auto_reencode: 是否自动重编码无法解码的视频（默认False）
        
        Raises:
            FileNotFoundError: 视频文件不存在
            RuntimeError: 无法打开视频文件
        """
        self.video_path = Path(video_path)
        self.original_video_path = self.video_path  # 保存原始路径
        self.logger = logger or logging.getLogger(__name__)
        self.convert_to_rgb = convert_to_rgb
        self.auto_reencode = auto_reencode
        self._reencoded = False  # 标记是否已重编码
        self._reencoder = None  # 延迟创建重编码器
        
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video file not found: {self.video_path}")
        
        # 视频捕获对象（延迟创建）
        self._cap: Optional[cv2.VideoCapture] = None
        
        # 当前帧索引和缓存
        self._current_frame_idx = -1
        self._cached_frame: Optional[np.ndarray] = None
        
        # 视频元数据（延迟加载）
        self._total_frames: Optional[int] = None
        self._fps: Optional[float] = None
        self._width: Optional[int] = None
        self._height: Optional[int] = None
        
        # 性能统计
        self._stats = {
            'total_reads': 0,
            'sequential_reads': 0,
            'seek_operations': 0,
            'cache_hits': 0
        }
    
    @property
    def num_frames(self) -> int:
        """返回视频总帧数"""
        self._ensure_opened()
        return self._total_frames
    
    def _try_reencode(self) -> bool:
        """
        尝试重编码视频
        
        Returns:
            是否成功重编码
        """
        try:
            # 延迟导入
            from robocoin_dataset.format_converter.utils.video_reencoder import VideoReencoder
            
            if self._reencoder is None:
                self._reencoder = VideoReencoder(logger=self.logger)
            
            success, reencoded_path, error = self._reencoder.reencode_video(
                self.original_video_path
            )
            
            if success and reencoded_path:
                self.logger.info(f"✅ Successfully re-encoded video, using: {reencoded_path.name}")
                self.video_path = reencoded_path
                self._reencoded = True
                return True
            else:
                self.logger.error(f"❌ Re-encoding failed: {error}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Re-encoding exception: {type(e).__name__}: {e}")
            return False
    
    def _ensure_opened(self):
        """确保视频文件已打开"""
        if self._cap is None:
            self._cap = cv2.VideoCapture(str(self.video_path))
            
            if not self._cap.isOpened():
                # 尝试自动重编码
                if self.auto_reencode and not self._reencoded:
                    self.logger.warning(
                        f"⚠️  Failed to open video: {self.video_path.name}. "
                        f"Attempting automatic re-encoding..."
                    )
                    if self._try_reencode():
                        # 重编码成功，重新尝试打开
                        self._cap = cv2.VideoCapture(str(self.video_path))
                        if not self._cap.isOpened():
                            raise RuntimeError(
                                f"Failed to open re-encoded video: {self.video_path}"
                            )
                    else:
                        raise RuntimeError(f"Failed to open video: {self.original_video_path}")
                else:
                    raise RuntimeError(f"Failed to open video: {self.video_path}")
            
            # 读取元数据
            self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self._fps = self._cap.get(cv2.CAP_PROP_FPS)
            self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            status = "re-encoded" if self._reencoded else "original"
            self.logger.debug(
                f"Opened video ({status}): {self.video_path.name}, "
                f"{self._total_frames} frames, "
                f"{self._width}x{self._height} @ {self._fps}fps"
            )
    
    def __getitem__(self, frame_idx: int) -> np.ndarray:
        """
        读取指定索引的帧
        
        Args:
            frame_idx: 帧索引（从0开始）
            
        Returns:
            numpy数组形式的帧图像 (H, W, C)
            
        Raises:
            IndexError: 帧索引超出范围
            RuntimeError: 读取帧失败
        """
        self._ensure_opened()
        
        # 统计
        self._stats['total_reads'] += 1
        
        # 检查索引范围
        if frame_idx < 0 or frame_idx >= self._total_frames:
            raise IndexError(
                f"Frame index {frame_idx} out of range "
                f"[0, {self._total_frames})"
            )
        
        # 如果请求的是当前缓存的帧，直接返回
        if frame_idx == self._current_frame_idx and self._cached_frame is not None:
            self._stats['cache_hits'] += 1
            return self._cached_frame.copy()  # 返回副本，避免外部修改
        
        # 判断是否需要seek
        if frame_idx != self._current_frame_idx + 1:
            # 非顺序访问，需要跳转
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            self._stats['seek_operations'] += 1
        else:
            # 顺序访问，无需跳转
            self._stats['sequential_reads'] += 1
        
        # 读取帧
        ret, frame = self._cap.read()
        
        if not ret or frame is None:
            # 尝试自动重编码
            if self.auto_reencode and not self._reencoded:
                self.logger.warning(
                    f"⚠️  Failed to read frame {frame_idx}. "
                    f"Attempting automatic re-encoding..."
                )
                # 关闭当前视频
                if self._cap:
                    self._cap.release()
                    self._cap = None
                
                # 尝试重编码
                if self._try_reencode():
                    # 重新打开视频并重试读取
                    self._ensure_opened()
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                    ret, frame = self._cap.read()
                    
                    if not ret or frame is None:
                        raise RuntimeError(
                            f"Failed to read frame {frame_idx} even after re-encoding"
                        )
                    self.logger.info(f"✅ Successfully read frame {frame_idx} from re-encoded video")
                else:
                    raise RuntimeError(
                        f"Failed to read frame {frame_idx} from {self.original_video_path}"
                    )
            else:
                raise RuntimeError(
                    f"Failed to read frame {frame_idx} from {self.video_path}"
                )
        
        # 转换BGR到RGB（如果需要）
        if self.convert_to_rgb:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # 更新缓存
        self._current_frame_idx = frame_idx
        self._cached_frame = frame
        
        return frame.copy()
    
    def __len__(self) -> int:
        """返回视频总帧数"""
        self._ensure_opened()
        return self._total_frames
    
    def __del__(self):
        """析构时释放资源"""
        self.close()
    
    def close(self):
        """关闭视频文件，释放资源"""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._cached_frame = None
            
            # 输出性能统计（如果有读取操作）
            if self._stats['total_reads'] > 0:
                sequential_ratio = (
                    self._stats['sequential_reads'] / self._stats['total_reads'] * 100
                )
                cache_hit_ratio = (
                    self._stats['cache_hits'] / self._stats['total_reads'] * 100
                )
                
                self.logger.debug(
                    f"LazyVideoReader stats for {self.video_path.name}: "
                    f"reads={self._stats['total_reads']}, "
                    f"sequential={sequential_ratio:.1f}%, "
                    f"seeks={self._stats['seek_operations']}, "
                    f"cache_hits={cache_hit_ratio:.1f}%"
                )
    
    @property
    def shape(self) -> tuple:
        """返回视频帧的形状 (num_frames, height, width, channels)"""
        self._ensure_opened()
        return (self._total_frames, self._height, self._width, 3)
    
    @property
    def fps(self) -> float:
        """返回视频帧率"""
        self._ensure_opened()
        return self._fps
    
    @property
    def frame_count(self) -> int:
        """返回视频总帧数"""
        return len(self)
    
    def get_stats(self) -> dict:
        """获取性能统计信息"""
        return self._stats.copy()
    
    def __repr__(self) -> str:
        return (
            f"LazyVideoReader('{self.video_path.name}', "
            f"frames={self._total_frames or 'unknown'})"
        )


class LazyVideoReaderPool:
    """
    延迟视频读取器池
    
    管理多个LazyVideoReader，用于同时处理多个相机的视频。
    支持类似dict的接口，方便替换现有的images_buffer。
    
    使用方式：
        pool = LazyVideoReaderPool()
        pool['cam_high'] = LazyVideoReader('cam_high.mp4')
        pool['cam_left'] = LazyVideoReader('cam_left.mp4')
        
        # 读取所有相机的第10帧
        frame_high = pool['cam_high'][10]
        frame_left = pool['cam_left'][10]
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self._readers: dict[str, LazyVideoReader] = {}
    
    def __setitem__(self, camera_name: str, reader: LazyVideoReader):
        """添加视频读取器"""
        self._readers[camera_name] = reader
    
    def __getitem__(self, camera_name: str) -> LazyVideoReader:
        """获取视频读取器"""
        return self._readers[camera_name]
    
    def __contains__(self, camera_name: str) -> bool:
        """检查相机是否存在"""
        return camera_name in self._readers
    
    def keys(self):
        """返回所有相机名称"""
        return self._readers.keys()
    
    def values(self):
        """返回所有读取器"""
        return self._readers.values()
    
    def items(self):
        """返回所有相机和读取器的键值对"""
        return self._readers.items()
    
    def close_all(self):
        """关闭所有视频读取器"""
        for reader in self._readers.values():
            reader.close()
        self._readers.clear()
    
    def get_total_stats(self) -> dict:
        """获取所有读取器的汇总统计"""
        total_stats = {
            'total_reads': 0,
            'sequential_reads': 0,
            'seek_operations': 0,
            'cache_hits': 0
        }
        
        for reader in self._readers.values():
            stats = reader.get_stats()
            for key in total_stats:
                total_stats[key] += stats.get(key, 0)
        
        return total_stats
    
    def __del__(self):
        """析构时关闭所有读取器"""
        self.close_all()
    
    def __repr__(self) -> str:
        return f"LazyVideoReaderPool({len(self._readers)} cameras)"


def test_lazy_video_reader():
    """测试LazyVideoReader功能"""
    import tempfile
    import shutil
    
    print("=" * 70)
    print("测试 LazyVideoReader")
    print("=" * 70)
    
    # 创建临时测试视频
    print("\n1. 创建测试视频...")
    temp_dir = Path(tempfile.mkdtemp())
    test_video = temp_dir / "test_video.mp4"
    
    # 使用cv2创建一个简单的测试视频
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(test_video), fourcc, 30.0, (640, 480))
    
    # 写入10帧，每帧不同颜色
    for i in range(10):
        frame = np.ones((480, 640, 3), dtype=np.uint8) * (i * 25)
        out.write(frame)
    out.release()
    
    print(f"   ✓ 创建测试视频: {test_video} (10帧)")
    
    # 测试LazyVideoReader
    print("\n2. 测试LazyVideoReader...")
    reader = LazyVideoReader(test_video)
    
    print(f"   视频信息: {reader}")
    print(f"   总帧数: {len(reader)}")
    print(f"   形状: {reader.shape}")
    print(f"   FPS: {reader.fps}")
    
    # 测试顺序读取
    print("\n3. 测试顺序读取...")
    for i in range(5):
        frame = reader[i]
        print(f"   帧 {i}: shape={frame.shape}, mean={frame.mean():.1f}")
    
    # 测试随机访问
    print("\n4. 测试随机访问...")
    frame_7 = reader[7]
    frame_3 = reader[3]
    print(f"   帧 7: mean={frame_7.mean():.1f}")
    print(f"   帧 3: mean={frame_3.mean():.1f}")
    
    # 测试缓存
    print("\n5. 测试缓存...")
    frame_3_again = reader[3]
    print(f"   再次读取帧 3: mean={frame_3_again.mean():.1f}")
    
    # 查看统计
    print("\n6. 性能统计:")
    stats = reader.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    # 关闭
    reader.close()
    
    # 清理
    shutil.rmtree(temp_dir)
    
    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("=" * 70)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    test_lazy_video_reader()

