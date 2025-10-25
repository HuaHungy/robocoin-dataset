"""
测试 Galaxea 数据集的自动视频重编码功能

测试场景：
1. 尝试打开 AV1 编码的视频（预期失败）
2. 启用 auto_reencode 后自动重编码
3. 验证重编码后的视频可以正常读取
"""

import sys
from pathlib import Path
import logging

# 添加 src 到路径
_project_root = Path(__file__).parent.parent
_src_dir = _project_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from robocoin_dataset.format_converter.tolerobot.lazy_video_reader import LazyVideoReader
from robocoin_dataset.format_converter.utils.video_reencoder import VideoReencoder

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def test_galaxea_videos():
    """测试 Galaxea 视频的自动重编码"""
    
    # Galaxea 数据集路径
    galaxea_path = Path("/home/liu/program/robocoin-dataset/data/galaxea_r1_lite:h5_mp4_version/865")
    
    # 测试视频列表
    video_files = [
        galaxea_path / "865_cam_high.mp4",
        galaxea_path / "865_cam_left_wrist.mp4",
        galaxea_path / "865_cam_right_wrist.mp4",
    ]
    
    logger.info("=" * 80)
    logger.info("🧪 测试 Galaxea AV1 视频自动重编码功能")
    logger.info("=" * 80)
    
    # 检查 ffmpeg 可用性
    reencoder = VideoReencoder(logger=logger)
    if not reencoder.check_ffmpeg_available():
        logger.error("❌ ffmpeg 不可用，请先安装 ffmpeg")
        logger.info("   安装命令: sudo apt-get install ffmpeg")
        return False
    
    logger.info("✅ ffmpeg 可用\n")
    
    # 测试每个视频
    success_count = 0
    failed_videos = []
    
    for i, video_path in enumerate(video_files, 1):
        logger.info(f"\n{'='*80}")
        logger.info(f"测试 {i}/{len(video_files)}: {video_path.name}")
        logger.info(f"{'='*80}")
        
        if not video_path.exists():
            logger.error(f"❌ 视频文件不存在: {video_path}")
            failed_videos.append((video_path.name, "文件不存在"))
            continue
        
        # 显示文件大小
        size_mb = video_path.stat().st_size / 1024 / 1024
        logger.info(f"📊 原始文件大小: {size_mb:.2f} MB")
        
        try:
            # 阶段1：尝试不启用 auto_reencode（应该失败）
            logger.info("\n🔍 阶段1: 尝试直接打开 AV1 视频（预期失败）...")
            try:
                reader_no_auto = LazyVideoReader(
                    video_path=video_path,
                    logger=logger,
                    auto_reencode=False  # 不自动重编码
                )
                # 尝试读取第一帧
                frame = reader_no_auto[0]
                logger.warning("⚠️  意外成功：AV1 视频可以直接读取（可能系统支持硬解码）")
                reader_no_auto.close()
            except Exception as e:
                logger.info(f"✅ 符合预期：直接打开失败")
                logger.info(f"   错误类型: {type(e).__name__}")
                logger.info(f"   错误信息: {str(e)[:100]}")
            
            # 阶段2：启用 auto_reencode
            logger.info("\n🔄 阶段2: 启用 auto_reencode，自动重编码...")
            
            reader = LazyVideoReader(
                video_path=video_path,
                logger=logger,
                auto_reencode=True  # ← 启用自动重编码
            )
            
            # 获取视频信息
            num_frames = len(reader)
            logger.info(f"📹 视频信息:")
            logger.info(f"   总帧数: {num_frames}")
            logger.info(f"   是否重编码: {reader._reencoded}")
            if reader._reencoded:
                logger.info(f"   重编码路径: {reader.video_path}")
                reencoded_size_mb = reader.video_path.stat().st_size / 1024 / 1024
                logger.info(f"   重编码大小: {reencoded_size_mb:.2f} MB")
                logger.info(f"   压缩率: {(1 - reencoded_size_mb / size_mb) * 100:.1f}%")
            
            # 阶段3：读取几帧进行验证
            logger.info("\n✅ 阶段3: 读取帧进行验证...")
            test_frames = [0, num_frames // 2, num_frames - 1]  # 测试首、中、尾帧
            
            for frame_idx in test_frames:
                frame = reader[frame_idx]
                logger.info(f"   帧 {frame_idx}: shape={frame.shape}, dtype={frame.dtype}")
            
            reader.close()
            
            logger.info(f"\n✅ {video_path.name} 测试成功！")
            success_count += 1
            
        except Exception as e:
            logger.error(f"\n❌ {video_path.name} 测试失败:")
            logger.error(f"   {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            failed_videos.append((video_path.name, str(e)))
    
    # 总结
    logger.info("\n" + "=" * 80)
    logger.info("📊 测试总结")
    logger.info("=" * 80)
    logger.info(f"✅ 成功: {success_count}/{len(video_files)}")
    logger.info(f"❌ 失败: {len(failed_videos)}/{len(video_files)}")
    
    if failed_videos:
        logger.info("\n失败列表:")
        for name, error in failed_videos:
            logger.info(f"  • {name}: {error[:100]}")
    
    # 显示缓存信息
    cache_info = reencoder.get_cache_info()
    logger.info(f"\n💾 缓存信息:")
    logger.info(f"   缓存视频数: {cache_info['cached_videos']}")
    logger.info(f"   总大小: {cache_info['total_size_mb']:.2f} MB")
    logger.info(f"   临时目录: {cache_info['temp_dir']}")
    
    logger.info("\n" + "=" * 80)
    
    return success_count == len(video_files)


if __name__ == "__main__":
    success = test_galaxea_videos()
    
    if success:
        logger.info("\n🎉 所有测试通过！自动重编码功能工作正常！")
        sys.exit(0)
    else:
        logger.error("\n❌ 部分测试失败，请检查日志")
        sys.exit(1)

