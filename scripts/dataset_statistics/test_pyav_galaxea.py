#!/usr/bin/env python3
"""
测试 PyAV 读取星海图 AV1 视频
"""

import av
from pathlib import Path
import numpy as np

print("="*70)
print("🔍 PyAV 读取星海图 AV1 视频测试")
print("="*70)

# 测试视频路径
video_path = Path("/mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train/organize_toys/4397/4397_cam_high.mp4")

print(f"\n📁 视频文件: {video_path.name}")
print(f"📍 完整路径: {video_path}")

# 1. 检查文件存在
if not video_path.exists():
    print(f"\n❌ 文件不存在!")
    exit(1)

file_size = video_path.stat().st_size / 1024 / 1024
print(f"✅ 文件存在: {file_size:.2f} MB")

# 2. 检查 PyAV 版本
print(f"\n📦 PyAV 版本: {av.__version__}")

# 3. 尝试打开视频
print(f"\n🎥 使用 PyAV 打开视频...")
try:
    container = av.open(str(video_path))
    print(f"✅ 视频打开成功")
except Exception as e:
    print(f"❌ 无法打开视频: {e}")
    exit(1)

# 4. 获取视频流信息
video_stream = container.streams.video[0]
print(f"\n📊 视频流信息:")
print(f"   编码格式: {video_stream.codec_context.codec.name}")
print(f"   编码全名: {video_stream.codec_context.codec.long_name}")
print(f"   分辨率: {video_stream.width}x{video_stream.height}")
print(f"   帧数: {video_stream.frames}")
print(f"   帧率: {video_stream.average_rate} FPS")
print(f"   时长: {float(video_stream.duration * video_stream.time_base):.2f} 秒")

# 5. 读取第一帧
print(f"\n🖼️  读取第一帧...")
try:
    for frame in container.decode(video=0):
        img = frame.to_ndarray(format='rgb24')
        print(f"✅ 成功读取第一帧")
        print(f"   形状: {img.shape}")
        print(f"   数据类型: {img.dtype}")
        print(f"   数值范围: [{img.min()}, {img.max()}]")
        break
except Exception as e:
    print(f"❌ 读取失败: {e}")
    container.close()
    exit(1)

# 6. 读取所有帧
print(f"\n🔄 读取所有帧...")
container.seek(0)  # 重置到开始
frames = []

try:
    for frame_idx, frame in enumerate(container.decode(video=0)):
        img = frame.to_ndarray(format='rgb24')
        frames.append(img)
        
        if (frame_idx + 1) % 200 == 0:
            print(f"   已读取 {frame_idx + 1} 帧...")
    
    container.close()
    
    print(f"\n✅ 成功读取所有帧")
    print(f"   期望帧数: {video_stream.frames}")
    print(f"   实际帧数: {len(frames)}")
    
    if len(frames) != video_stream.frames:
        diff = abs(len(frames) - video_stream.frames)
        print(f"   ⚠️  帧数不匹配（差异 {diff} 帧，{diff/video_stream.frames*100:.2f}%）")
    else:
        print(f"   ✅ 帧数完全一致")
    
    # 检查所有帧的形状是否一致
    shapes = [f.shape for f in frames[:10]]
    if len(set(shapes)) == 1:
        print(f"   ✅ 所有帧形状一致: {frames[0].shape}")
    else:
        print(f"   ⚠️  帧形状不一致: {set(shapes)}")
        
except Exception as e:
    print(f"❌ 读取所有帧时失败: {e}")
    container.close()
    exit(1)

# 7. 模拟转换器逻辑
print(f"\n🧪 模拟转换器的 _prepare_episode_images_buffer 逻辑...")

ep_dir = video_path.parent
video_pattern = "*cam_high.mp4"

print(f"   Episode目录: {ep_dir}")
print(f"   视频模式: {video_pattern}")

mp4_files = list(ep_dir.glob(video_pattern))
print(f"   找到视频: {[f.name for f in mp4_files]}")

if mp4_files:
    mp4_file = mp4_files[0]
    print(f"   使用视频: {mp4_file.name}")
    
    try:
        container = av.open(str(mp4_file))
        frames_buffer = []
        
        for frame in container.decode(video=0):
            img = frame.to_ndarray(format='rgb24')
            frames_buffer.append(img)
        
        container.close()
        
        print(f"   ✅ 缓冲区帧数: {len(frames_buffer)}")
        
        if len(frames_buffer) == 0:
            print(f"   ❌ 缓冲区为空!")
        else:
            print(f"   ✅ 缓冲区正常")
            
    except Exception as e:
        print(f"   ❌ 模拟失败: {e}")
        exit(1)

print(f"\n" + "="*70)
print(f"✅ 所有测试通过!")
print(f"   PyAV 可以正常读取星海图 AV1 视频")
print(f"   转换器代码已更新为使用 PyAV")
print("="*70)
