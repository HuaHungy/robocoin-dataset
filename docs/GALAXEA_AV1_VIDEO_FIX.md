# 星海图 AV1 视频解码问题修复指南

## 问题现象

转换星海图数据集时报错：
```
IndexError: ❌ Frame index out of range for camera video.
📊 All camera frame counts: {'cam_high': 0, 'cam_left_wrist': 0, 'cam_right_wrist': 0}
```

## 问题根因

**视频使用 AV1 编码格式，而当前 OpenCV 不支持 AV1 解码**

错误日志显示：
```
[av1 @ 0x5692c3bf5480] Your platform doesn't support hardware accelerated AV1 decoding.
[av1 @ 0x5692c3bf5480] Failed to get pixel format.
[av1 @ 0x5692c3bf5480] Missing Sequence Header.
```

视频编码信息：
```json
{
  "codec_name": "av1",
  "codec_long_name": "Alliance for Open Media AV1",
  "codec_tag": "av01",
  "width": 1280,
  "height": 720,
  "bit_rate": "2935006"
}
```

## 解决方案

### 方案1: 安装支持 AV1 的 OpenCV (推荐)

#### 1.1 使用 conda 安装 (最可靠)

```bash
# 安装 libdav1d (AV1 解码器)
conda install -c conda-forge dav1d

# 重新安装 opencv
conda install -c conda-forge opencv
```

#### 1.2 从源码编译 OpenCV (如果conda不可用)

```bash
# 安装 AV1 解码库
sudo apt-get update
sudo apt-get install -y libdav1d-dev

# 安装 ffmpeg 及依赖
sudo apt-get install -y \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev

# 重新安装 opencv-python
pip uninstall -y opencv-python opencv-contrib-python
pip install --no-binary opencv-python opencv-python
```

### 方案2: 转换视频为 H.264 格式 (如果无法升级OpenCV)

创建批量转换脚本 `convert_av1_to_h264.py`:

```python
#!/usr/bin/env python3
"""
将星海图 AV1 视频转换为 H.264 格式
"""

import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import argparse

def convert_video(mp4_file: Path, output_dir: Path = None):
    """转换单个视频"""
    
    if output_dir is None:
        output_file = mp4_file.with_suffix('.h264.mp4')
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / mp4_file.name
    
    # 如果输出文件已存在，跳过
    if output_file.exists():
        print(f"⏭️  跳过（已存在）: {output_file.name}")
        return True
    
    cmd = [
        'ffmpeg',
        '-i', str(mp4_file),
        '-c:v', 'libx264',      # 使用 H.264 编码
        '-preset', 'medium',     # 编码速度（ultrafast/fast/medium/slow）
        '-crf', '23',            # 质量（0-51，越小越好，默认23）
        '-c:a', 'copy',          # 音频直接复制
        '-y',                    # 覆盖输出文件
        str(output_file)
    ]
    
    try:
        print(f"🔄 转换中: {mp4_file.name} -> {output_file.name}")
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        print(f"✅ 完成: {output_file.name}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ 失败: {mp4_file.name}")
        print(f"   错误: {e.stderr.decode()}")
        return False

def main():
    parser = argparse.ArgumentParser(description='将星海图 AV1 视频转换为 H.264')
    parser.add_argument('--dataset-path', required=True, help='数据集路径')
    parser.add_argument('--task', help='任务名称（可选，不指定则处理所有任务）')
    parser.add_argument('--workers', type=int, default=4, help='并发数')
    parser.add_argument('--output-suffix', default='_h264', help='输出目录后缀')
    
    args = parser.parse_args()
    
    dataset_path = Path(args.dataset_path)
    
    # 查找所有 AV1 视频
    if args.task:
        task_dirs = [dataset_path / args.task]
    else:
        task_dirs = [d for d in dataset_path.iterdir() if d.is_dir()]
    
    mp4_files = []
    for task_dir in task_dirs:
        mp4_files.extend(task_dir.rglob('*.mp4'))
    
    print(f"📁 数据集路径: {dataset_path}")
    print(f"🎥 找到视频文件: {len(mp4_files)} 个")
    print(f"⚙️  并发数: {args.workers}")
    print(f"=" * 70)
    
    # 并行转换
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        results = list(executor.map(convert_video, mp4_files))
    
    success_count = sum(results)
    print(f"\n" + "=" * 70)
    print(f"✅ 成功: {success_count}/{len(mp4_files)}")
    print(f"❌ 失败: {len(mp4_files) - success_count}/{len(mp4_files)}")

if __name__ == '__main__':
    main()
```

使用方法：
```bash
# 转换单个任务
python3 convert_av1_to_h264.py \
  --dataset-path /mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train \
  --task organize_toys \
  --workers 8

# 转换所有任务
python3 convert_av1_to_h264.py \
  --dataset-path /mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train \
  --workers 8
```

转换完成后，更新配置文件中的视频路径或重命名视频文件。

### 方案3: 使用 PyAV 替代 OpenCV (代码修改)

如果不想转换视频，可以修改转换器使用 PyAV 库读取视频：

```bash
pip install av
```

修改 `lerobot_format_converter_h5_mp4.py` 中的视频读取代码：

```python
import av

def _prepare_episode_images_buffer_pyav(self, ep_dir: Path, cam_name: str) -> list:
    """使用 PyAV 读取视频（支持 AV1）"""
    video_pattern = self.conversion_config.converter_config.cam_name[cam_name]
    mp4_files = list(ep_dir.glob(video_pattern))
    
    if not mp4_files:
        raise FileNotFoundError(f"No video found for pattern {video_pattern}")
    
    mp4_file = mp4_files[0]
    frames_buffer = []
    
    # 使用 PyAV 读取
    container = av.open(str(mp4_file))
    
    for frame in container.decode(video=0):
        # 转换为 numpy array
        img = frame.to_ndarray(format='rgb24')
        frames_buffer.append(img)
    
    container.close()
    return frames_buffer
```

## 验证修复

运行诊断脚本：
```bash
python3 scripts/dataset_statistics/test_galaxea_video_local.py
```

预期输出：
```
✅ 所有测试通过!
   本地环境可以正常读取星海图视频
   缓冲区正常，包含 1588 帧
```

## 其他星海图数据集检查

检查所有星海图视频是否使用 AV1 编码：

```bash
# 检查视频编码
find /mnt/nas/synnas/docker/外部数据/ -name "*.mp4" -type f | \
  while read f; do
    codec=$(ffprobe -v quiet -select_streams v:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$f")
    if [ "$codec" = "av1" ]; then
      echo "AV1: $f"
    fi
  done
```

## 推荐方案选择

- **有 conda 环境**: 使用方案1.1（conda 安装 dav1d + opencv）
- **无 conda，有 sudo**: 使用方案1.2（apt 安装 libdav1d + 重装opencv）
- **无法修改系统**: 使用方案2（转换视频为 H.264）
- **代码可修改**: 使用方案3（PyAV 库）

## 参考资料

- AV1 编码: https://en.wikipedia.org/wiki/AV1
- dav1d 解码器: https://code.videolan.org/videolan/dav1d
- PyAV 库: https://github.com/PyAV-Org/PyAV
