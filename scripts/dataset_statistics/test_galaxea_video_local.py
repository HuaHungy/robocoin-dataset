#!/usr/bin/env python3
"""
在本地测试星海图视频读取
"""

import cv2
from pathlib import Path

print("="*70)
print("🔍 星海图视频读取测试")
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

# 2. 检查OpenCV版本
print(f"\n📦 OpenCV版本: {cv2.__version__}")

# 3. 尝试打开视频
print(f"\n🎥 尝试打开视频...")
cap = cv2.VideoCapture(str(video_path))

if not cap.isOpened():
    print(f"❌ 无法打开视频文件!")
    print(f"   可能原因：")
    print(f"   1. OpenCV缺少H.264/H.265解码器")
    print(f"   2. 缺少ffmpeg支持")
    print(f"   3. 视频文件格式不支持")
    
    # 显示编译信息
    print(f"\n📋 OpenCV编译信息（Video I/O相关）:")
    build_info = cv2.getBuildInformation()
    for line in build_info.split('\n'):
        if any(kw in line.lower() for kw in ['ffmpeg', 'video', 'avcodec', 'gstreamer']):
            print(f"   {line.strip()}")
    
    exit(1)

print(f"✅ 视频打开成功")

# 4. 获取视频属性
frame_count_prop = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)

print(f"\n📊 视频属性:")
print(f"   帧数: {frame_count_prop}")
print(f"   分辨率: {width}x{height}")
print(f"   帧率: {fps} FPS")

# 5. 尝试读取第一帧
print(f"\n🖼️  尝试读取第一帧...")
ret, frame = cap.read()

if not ret:
    print(f"❌ 无法读取第一帧!")
    print(f"   属性显示有 {frame_count_prop} 帧，但实际无法读取")
    print(f"   这通常表示codec/解码器问题")
    cap.release()
    exit(1)

print(f"✅ 成功读取第一帧")
print(f"   形状: {frame.shape}")
print(f"   数据类型: {frame.dtype}")

# 6. 读取所有帧（模拟转换器的行为）
print(f"\n🔄 读取所有帧（模拟转换器）...")
frames = []
frame_idx = 0

cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # 重置到开始

while True:
    ret, frame = cap.read()
    if not ret:
        break
    frames.append(frame)
    frame_idx += 1
    
    if frame_idx % 200 == 0:
        print(f"   已读取 {frame_idx} 帧...")

cap.release()

print(f"\n✅ 成功读取所有帧")
print(f"   期望帧数: {frame_count_prop}")
print(f"   实际帧数: {len(frames)}")

if len(frames) != frame_count_prop:
    print(f"   ⚠️  帧数不匹配（差异 {abs(len(frames) - frame_count_prop)} 帧）")
else:
    print(f"   ✅ 帧数一致")

# 7. 模拟转换器的准备缓冲区逻辑
print(f"\n🧪 模拟转换器的 _prepare_episode_images_buffer 逻辑...")

ep_dir = video_path.parent
video_pattern = "*cam_high.mp4"

print(f"   Episode目录: {ep_dir}")
print(f"   视频模式: {video_pattern}")

mp4_files = list(ep_dir.glob(video_pattern))
print(f"   找到视频: {[f.name for f in mp4_files]}")

if not mp4_files:
    print(f"   ❌ 未找到匹配的视频文件!")
    exit(1)

mp4_file = mp4_files[0]
print(f"   使用视频: {mp4_file.name}")

cap = cv2.VideoCapture(str(mp4_file))
if not cap.isOpened():
    print(f"   ❌ 无法打开视频")
    exit(1)

frames_buffer = []
while True:
    ret, frame = cap.read()
    if not ret:
        break
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frames_buffer.append(frame_rgb)

cap.release()

print(f"   ✅ 缓冲区帧数: {len(frames_buffer)}")

if len(frames_buffer) == 0:
    print(f"\n❌ 关键问题：缓冲区为空!")
    print(f"   这就是转换器报告0帧的原因")
    print(f"   可能原因：")
    print(f"   1. cv2.VideoCapture 打开成功但无法解码帧")
    print(f"   2. while循环第一次 cap.read() 就返回 False")
    exit(1)
else:
    print(f"   ✅ 缓冲区正常，包含 {len(frames_buffer)} 帧")

print(f"\n" + "="*70)
print(f"✅ 所有测试通过!")
print(f"   本地环境可以正常读取星海图视频")
print(f"   如果服务器报告0帧，说明服务器的OpenCV有问题")
print("="*70)
