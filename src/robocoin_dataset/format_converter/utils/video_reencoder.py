"""
视频自动重编码工具

在转换过程中动态检测和修复视频编码问题
"""

import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple
import logging


class VideoReencoder:
    """视频自动重编码器
    
    特性:
    - 检测视频编码兼容性问题
    - 自动调用 ffmpeg 重编码
    - 使用临时文件，不影响原始数据
    - 支持缓存重编码结果
    """
    
    def __init__(
        self,
        temp_dir: Optional[Path] = None,
        codec: str = "libx264",
        crf: int = 23,
        logger: Optional[logging.Logger] = None
    ):
        """
        初始化重编码器
        
        Args:
            temp_dir: 临时文件目录（默认使用系统临时目录）
            codec: 视频编码器（默认 libx264）
            crf: 压缩质量 (0-51, 越小质量越好，默认23)
            logger: 日志记录器
        """
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir()) / "robocoin_reencoded"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        self.codec = codec
        self.crf = crf
        self.logger = logger or logging.getLogger(__name__)
        
        # 缓存已重编码的文件
        self._reencoded_cache: dict[str, Path] = {}
    
    def check_ffmpeg_available(self) -> bool:
        """检查 ffmpeg 是否可用"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def reencode_video(
        self,
        video_path: Path,
        force: bool = False
    ) -> Tuple[bool, Optional[Path], Optional[str]]:
        """
        重编码视频文件
        
        Args:
            video_path: 原始视频路径
            force: 强制重编码（即使已有缓存）
            
        Returns:
            (成功标志, 重编码后的路径, 错误信息)
        """
        video_path = Path(video_path)
        
        if not video_path.exists():
            return False, None, f"Video file not found: {video_path}"
        
        # 检查缓存
        cache_key = str(video_path.absolute())
        if not force and cache_key in self._reencoded_cache:
            cached_path = self._reencoded_cache[cache_key]
            if cached_path.exists():
                self.logger.info(f"✅ Using cached reencoded video: {cached_path.name}")
                return True, cached_path, None
        
        # 检查 ffmpeg 是否可用
        if not self.check_ffmpeg_available():
            return False, None, "ffmpeg is not available. Please install ffmpeg."
        
        # 生成临时文件路径
        temp_filename = f"{video_path.stem}_reencoded_{video_path.suffix}"
        temp_path = self.temp_dir / temp_filename
        
        self.logger.info(f"🔄 Re-encoding video: {video_path.name}")
        self.logger.info(f"   Codec: {self.codec}, CRF: {self.crf}")
        
        try:
            # 构建 ffmpeg 命令
            cmd = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-i", str(video_path),
                "-c:v", self.codec,
                "-crf", str(self.crf),
                "-preset", "medium",
                "-pix_fmt", "yuv420p",
                str(temp_path)
            ]
            
            # 执行重编码
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode != 0:
                error_msg = f"ffmpeg failed: {result.stderr}"
                self.logger.error(error_msg)
                return False, None, error_msg
            
            # 验证输出文件
            if not temp_path.exists() or temp_path.stat().st_size == 0:
                return False, None, "Re-encoded file is empty or missing"
            
            # 缓存结果
            self._reencoded_cache[cache_key] = temp_path
            
            self.logger.info(f"✅ Re-encoding successful: {temp_path.name}")
            self.logger.info(f"   Original: {video_path.stat().st_size / 1024 / 1024:.2f} MB")
            self.logger.info(f"   Re-encoded: {temp_path.stat().st_size / 1024 / 1024:.2f} MB")
            
            return True, temp_path, None
            
        except subprocess.TimeoutExpired:
            return False, None, "Re-encoding timeout (>5 minutes)"
        except Exception as e:
            return False, None, f"Re-encoding error: {type(e).__name__}: {e}"
    
    def cleanup(self):
        """清理所有临时文件"""
        if self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
                self.logger.info(f"🧹 Cleaned up temporary re-encoded videos")
            except Exception as e:
                self.logger.warning(f"Failed to cleanup temp directory: {e}")
    
    def get_cache_info(self) -> dict:
        """获取缓存信息"""
        total_size = sum(
            path.stat().st_size 
            for path in self._reencoded_cache.values() 
            if path.exists()
        )
        
        return {
            "cached_videos": len(self._reencoded_cache),
            "total_size_mb": total_size / 1024 / 1024,
            "temp_dir": str(self.temp_dir)
        }

