#!/usr/bin/env python3
"""
视频帧数验证工具 - 使用示例

演示如何使用video_frame_validator模块验证视频帧数
"""

import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入验证工具
from robocoin_dataset.format_converter.tolerobot.video_frame_validator import (
    get_video_frame_count_ffprobe,
    validate_video_frame_count,
    get_video_info_ffprobe,
)


def example_1_get_frame_count():
    """示例1: 获取视频帧数"""
    print("\n" + "="*60)
    print("示例1: 获取视频帧数")
    print("="*60)
    
    video_path = Path("data/aloha/episode_2/camera_front.mp4")
    
    if not video_path.exists():
        print(f"⚠️ 视频文件不存在: {video_path}")
        print("💡 请替换为实际的视频文件路径")
        return
    
    try:
        frame_count = get_video_frame_count_ffprobe(video_path, logger)
        print(f"✅ 视频总帧数: {frame_count}")
    except RuntimeError as e:
        print(f"❌ 获取帧数失败: {e}")


def example_2_validate_frame_count():
    """示例2: 验证视频帧数与数据匹配"""
    print("\n" + "="*60)
    print("示例2: 验证视频帧数与数据匹配")
    print("="*60)
    
    video_path = Path("data/aloha/episode_2/camera_front.mp4")
    expected_frame_count = 1200  # 假设从H5文件读取的帧数
    
    if not video_path.exists():
        print(f"⚠️ 视频文件不存在: {video_path}")
        print("💡 请替换为实际的视频文件路径")
        return
    
    try:
        validate_video_frame_count(
            video_path=video_path,
            expected_frame_count=expected_frame_count,
            data_source="H5 file (qpos dataset)",
            logger=logger,
            tolerance=1  # 允许±1帧误差
        )
        print("✅ 视频帧数验证通过！")
    except ValueError as e:
        print(f"❌ 帧数不匹配:\n{e}")
    except RuntimeError as e:
        print(f"❌ 验证失败: {e}")


def example_3_get_video_info():
    """示例3: 获取完整视频信息"""
    print("\n" + "="*60)
    print("示例3: 获取完整视频信息")
    print("="*60)
    
    video_path = Path("data/aloha/episode_2/camera_front.mp4")
    
    if not video_path.exists():
        print(f"⚠️ 视频文件不存在: {video_path}")
        print("💡 请替换为实际的视频文件路径")
        return
    
    try:
        info = get_video_info_ffprobe(video_path, logger)
        print(f"📹 视频信息:")
        print(f"   分辨率: {info['width']}x{info['height']}")
        print(f"   帧率: {info['fps']:.2f} fps")
        print(f"   时长: {info['duration']:.2f} 秒")
        print(f"   总帧数: {info['frame_count']}")
    except RuntimeError as e:
        print(f"❌ 获取视频信息失败: {e}")


def example_4_batch_validation():
    """示例4: 批量验证多个视频"""
    print("\n" + "="*60)
    print("示例4: 批量验证多个视频")
    print("="*60)
    
    episode_dir = Path("data/aloha/episode_2")
    expected_frame_count = 1200
    
    if not episode_dir.exists():
        print(f"⚠️ Episode目录不存在: {episode_dir}")
        print("💡 请替换为实际的episode目录路径")
        return
    
    # 获取所有MP4文件
    mp4_files = list(episode_dir.glob("*.mp4"))
    
    if not mp4_files:
        print(f"⚠️ 未找到MP4文件: {episode_dir}")
        return
    
    print(f"📂 找到 {len(mp4_files)} 个视频文件")
    
    results = {
        "validated": [],
        "mismatched": [],
        "failed": []
    }
    
    for mp4_file in mp4_files:
        try:
            validate_video_frame_count(
                video_path=mp4_file,
                expected_frame_count=expected_frame_count,
                data_source="H5 file",
                logger=None,  # 不打印详细日志
                tolerance=1
            )
            results["validated"].append(mp4_file.name)
            print(f"  ✅ {mp4_file.name}: 验证通过")
        except ValueError as e:
            results["mismatched"].append(mp4_file.name)
            print(f"  ❌ {mp4_file.name}: 帧数不匹配")
        except RuntimeError as e:
            results["failed"].append(mp4_file.name)
            print(f"  ⚠️ {mp4_file.name}: 验证失败")
    
    print(f"\n📊 验证结果:")
    print(f"   通过: {len(results['validated'])}/{len(mp4_files)}")
    print(f"   不匹配: {len(results['mismatched'])}/{len(mp4_files)}")
    print(f"   失败: {len(results['failed'])}/{len(mp4_files)}")


def example_5_with_h5_file():
    """示例5: 结合H5文件的完整验证流程"""
    print("\n" + "="*60)
    print("示例5: 结合H5文件的完整验证流程")
    print("="*60)
    
    episode_dir = Path("data/aloha/episode_2")
    h5_file = episode_dir / "data.hdf5"
    
    if not h5_file.exists():
        print(f"⚠️ H5文件不存在: {h5_file}")
        print("💡 请替换为实际的H5文件路径")
        return
    
    # 从H5文件读取预期帧数
    try:
        import h5py
        with h5py.File(h5_file, 'r') as f:
            if 'qpos' in f:
                expected_frame_count = f['qpos'].shape[0]
                print(f"📊 从H5文件读取帧数: {expected_frame_count} (qpos)")
            elif 'action' in f:
                expected_frame_count = f['action'].shape[0]
                print(f"📊 从H5文件读取帧数: {expected_frame_count} (action)")
            else:
                print("❌ H5文件中没有qpos或action数据集")
                return
    except Exception as e:
        print(f"❌ 读取H5文件失败: {e}")
        return
    
    # 验证所有视频
    mp4_files = list(episode_dir.glob("*.mp4"))
    print(f"📹 找到 {len(mp4_files)} 个视频文件")
    
    all_match = True
    for mp4_file in mp4_files:
        try:
            validate_video_frame_count(
                video_path=mp4_file,
                expected_frame_count=expected_frame_count,
                data_source="H5 file",
                logger=logger,
                tolerance=1
            )
        except ValueError:
            all_match = False
    
    if all_match:
        print("\n✅ 所有视频帧数与H5数据匹配！")
    else:
        print("\n⚠️ 存在帧数不匹配的视频")


def main():
    """运行所有示例"""
    print("="*60)
    print("视频帧数验证工具 - 使用示例")
    print("="*60)
    
    # 运行各个示例
    example_1_get_frame_count()
    example_2_validate_frame_count()
    example_3_get_video_info()
    example_4_batch_validation()
    example_5_with_h5_file()
    
    print("\n" + "="*60)
    print("所有示例执行完毕")
    print("="*60)


if __name__ == "__main__":
    main()
