# 修复：agilex_cobot_decoupled_magic 图像加载失败

**日期**: 2025-10-27  
**问题**: JPG+JSON converter 加载图像时返回空的相机列表  
**影响**: agilex_cobot_decoupled_magic:mult_sensor 数据集无法转换

---

## 🐛 问题描述

### 错误信息

```
WARNING | ⚠️  Failed to get sample image for camera 'camera_front_rgb' 
from task_path=clean_coffee_beans, episode=0: 
KeyError: '❌ Camera not found in images buffer.
   📹 Requested camera: camera_front_rgb
   📁 Location: task=clean_coffee_beans, ep_idx=0, frame_idx=0
   📋 Available cameras: []  ← 空列表！
```

### 根本原因

JPG+JSON converter 的 `_prepare_episode_images_buffer()` 方法在找不到相机目录或图像文件时**静默失败**，没有记录任何警告信息，导致：

1. 无法诊断问题
2. 返回空的 `images = {}` 字典
3. 验证失败，转换中止

### 可能的具体原因

1. **Camera base目录不存在**: `episode/camera/color/` 路径不存在
2. **Camera folder不匹配**: 配置的 `camera_folder: front` 但实际目录名不同
3. **没有图像文件**: 相机目录存在但没有 `.jpg` 或 `.png` 文件
4. **图像文件损坏**: 文件存在但无法用PIL打开

---

## ✅ 修复方案

### 添加详细的诊断日志

**修改文件**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_jpg_json.py`

**修改位置**: `_prepare_episode_images_buffer()` 方法

### 新增诊断点

#### 1️⃣ Camera基础目录检查

```python
if not camera_base_dir.exists():
    logger.warning(
        f"⚠️  Camera base directory not found for '{cam_name}'.\n"
        f"   📂 Expected: {camera_base_dir}\n"
        f"   📂 Episode: {ep_dir}\n"
        f"   💡 Skipping this camera"
    )
    continue
```

#### 2️⃣ Camera folder检查

```python
if not camera_folder:
    logger.warning(
        f"⚠️  Camera folder not specified or found for '{cam_name}'.\n"
        f"   📂 Camera base: {camera_base_dir}\n"
        f"   💡 Check config 'camera_folder' parameter"
    )
    continue
```

#### 3️⃣ Camera folder路径检查

```python
if not cam_folder_path.exists():
    available_folders = [d.name for d in camera_base_dir.iterdir() if d.is_dir()]
    logger.warning(
        f"⚠️  Camera folder not found for '{cam_name}'.\n"
        f"   📂 Expected: {cam_folder_path}\n"
        f"   📂 Camera base: {camera_base_dir}\n"
        f"   📋 Available folders: {available_folders}\n"
        f"   💡 Check if camera folder name matches"
    )
    continue
```

#### 4️⃣ 图像文件检查

```python
if not image_files:
    all_files = list(cam_folder_path.glob("*"))[:10]
    logger.warning(
        f"⚠️  No image files found for '{cam_name}'.\n"
        f"   📂 Camera folder: {cam_folder_path}\n"
        f"   📋 Files found (first 10): {[f.name for f in all_files]}\n"
        f"   💡 Expected .jpg or .png files"
    )
    continue
```

#### 5️⃣ 图像加载错误处理

```python
try:
    img = Image.open(img_file)
    ...
except Exception as e:
    logger.warning(f"⚠️  Failed to load image {img_file}: {e}")
    continue  # 继续处理其他图像
```

#### 6️⃣ 所有图像加载失败检查

```python
if not frames:
    logger.warning(
        f"⚠️  All images failed to load for '{cam_name}'.\n"
        f"   📂 Camera folder: {cam_folder_path}\n"
        f"   📊 Attempted: {len(image_files)} files"
    )
    continue
```

#### 7️⃣ 最终检查：没有加载任何相机

```python
if not images and self.logger:
    logger.error(
        f"❌ No cameras loaded for episode!\n"
        f"   📂 Episode: {ep_dir}\n"
        f"   📋 Configured cameras: {[cfg.get(CAM_NAME_KEY) for cfg in image_configs]}\n"
        f"   💡 Check episode directory structure and camera configuration"
    )
```

---

## 📊 修复效果对比

### 修复前

```
[无任何日志]
KeyError: Available cameras: []
```

❌ 完全不知道哪里出了问题

### 修复后

```
⚠️  Camera base directory not found for 'camera_front_rgb'.
   📂 Expected: /path/to/episode/camera/color
   📂 Episode: /path/to/episode
   💡 Skipping this camera

⚠️  Camera folder not found for 'camera_left_rgb'.
   📂 Expected: /path/to/episode/camera/color/left
   📂 Camera base: /path/to/episode/camera/color
   📋 Available folders: ['Left', 'Right', 'Front']
   💡 Check if camera folder name matches

❌ No cameras loaded for episode!
   📂 Episode: /path/to/episode
   📋 Configured cameras: ['camera_front_rgb', 'camera_left_rgb', 'camera_right_rgb']
   💡 Check episode directory structure and camera configuration
```

✅ 清晰地知道每个相机失败的原因和可用的选项

---

## 🔍 如何使用新的诊断信息

### 场景1: Camera base目录不存在

**日志**:
```
⚠️  Camera base directory not found for 'camera_front_rgb'.
   📂 Expected: /path/to/episode/camera/color
   📂 Episode: /path/to/episode
```

**可能原因**:
- Episode目录结构不是JPG+JSON格式
- 可能是其他格式（H5, MP4+JSON等）
- 数据集配置错误

**解决方案**:
1. 检查episode目录结构
2. 确认数据集格式
3. 使用正确的converter

### 场景2: Camera folder名称不匹配

**日志**:
```
⚠️  Camera folder not found for 'camera_left_rgb'.
   📂 Expected: /path/to/episode/camera/color/left
   📂 Camera base: /path/to/episode/camera/color
   📋 Available folders: ['Left', 'Right', 'Front']  ← 注意大小写！
```

**可能原因**:
- 配置文件中 `camera_folder: left` 但实际是 `Left`（大小写不匹配）
- 配置文件中 `camera_folder: front` 但实际是 `head` 或其他名称

**解决方案**:
1. 修改配置文件的 `camera_folder` 参数匹配实际目录名
2. 或重命名数据集中的相机目录

### 场景3: 没有图像文件

**日志**:
```
⚠️  No image files found for 'camera_front_rgb'.
   📂 Camera folder: /path/to/episode/camera/color/front
   📋 Files found (first 10): ['000000.jpeg', '000001.jpeg', ...]
   💡 Expected .jpg or .png files
```

**可能原因**:
- 图像文件扩展名是 `.jpeg` 而不是 `.jpg`
- 或者是其他格式（`.bmp`, `.tiff` 等）

**解决方案**:
- 扩展 `image_files` 的 glob 模式以包含 `.jpeg`

---

## 🚀 部署

### 同步代码到Client机器

```bash
# 在每台Client机器上
cd ~/robocoin-dataset
git pull origin feat/test

# 重启clients
Ctrl+C
python scripts/format_converters/tolerobot/multi_client.py \
    --host 172.16.13.140 --port 8769 --num-clients 4
```

### 验证

重新运行失败的任务后，应该能看到详细的诊断信息，明确指出问题所在。

---

## 📚 相关问题

### ⚠️ Semaphore泄漏

同时出现的 semaphore 泄漏警告：
```
UserWarning: resource_tracker: There appear to be 2 leaked semaphore objects
```

**原因**: Client机器可能还在使用旧代码，没有包含之前的 semaphore 修复。

**解决方案**: 同步代码后重启Client（见上面部署步骤）。

---

**修复状态**: ✅ 已完成  
**下一步**: 
1. 同步代码到所有Client机器
2. 重新运行agilex_cobot_decoupled_magic:mult_sensor测试
3. 根据新的诊断日志修复实际问题（目录结构/配置）

