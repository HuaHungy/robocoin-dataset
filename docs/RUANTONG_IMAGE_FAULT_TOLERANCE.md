# 软通(Ruantong)图像容错机制说明

**日期**: 2025-10-23  
**适用配置**: 
- `converter_config_ruantong.yaml`
- `converter_config_ruantong_gt01_no_depth.yaml`
- `converter_config_ruantong_gt02_new.yaml`

---

## 📋 容错策略

### 强制必需的相机（3个）

以下3个相机**必须存在**，否则跳过整个episode：

| 相机名称 | 标准命名 | 说明 |
|---------|---------|------|
| ~~head_color~~ | **cam_high_rgb** | 头部/高位相机（已重命名） |
| ~~hand_left_color~~ | **cam_left_wrist_rgb** | 左手腕相机（已重命名） |
| ~~hand_right_color~~ | **cam_right_wrist_rgb** | 右手腕相机（已重命名） |

**容错行为**:
```python
# 在converter中检查
required_cameras = ['cam_high_rgb', 'cam_left_wrist_rgb', 'cam_right_wrist_rgb']

for required_cam in required_cameras:
    if not camera_exists(required_cam, frame_0):
        # ❌ 跳过整个episode
        raise CriticalDataError(
            f"缺少必需相机 {required_cam}，跳过整个episode"
        )
```

### 可选相机（容错处理）

其他相机（如鱼眼相机）为可选，采用以下容错策略：

| 相机名称（旧） | 标准命名（新） | 容错策略 |
|--------------|--------------|---------|
| ~~head_center_fisheye_color~~ | **cam_high_center_fisheye_rgb** | 如有则用 |
| ~~back_left_fisheye_color~~ | **cam_back_left_fisheye_rgb** | 如有则用 |
| ~~back_right_fisheye_color~~ | **cam_back_right_fisheye_rgb** | 如有则用 |
| ~~head_left_fisheye_color~~ | **cam_high_left_fisheye_rgb** | 如有则用 |
| ~~head_right_fisheye_color~~ | **cam_high_right_fisheye_rgb** | 如有则用 |

**容错行为**:
```python
# 对于可选相机
optional_cameras = [
    'cam_high_center_fisheye_rgb',
    'cam_back_left_fisheye_rgb',
    'cam_back_right_fisheye_rgb',
    'cam_high_left_fisheye_rgb',
    'cam_high_right_fisheye_rgb',
]

for frame_idx in range(num_frames):
    for cam_name in optional_cameras:
        if camera_exists(cam_name, frame_idx):
            # ✅ 相机存在，正常读取
            image = read_image(cam_name, frame_idx)
        else:
            # ⚠️ 相机不存在，尝试复制上一帧
            if frame_idx > 0 and has_previous_frame(cam_name, frame_idx - 1):
                # 📋 复制上一帧图像
                image = copy_previous_frame(cam_name, frame_idx - 1)
                logger.warning(
                    f"Frame {frame_idx}: 相机 {cam_name} 缺失，"
                    f"已复制上一帧 (frame {frame_idx-1})"
                )
            else:
                # ❌ 第0帧或上一帧也不存在，完全移除此相机
                remove_camera_from_config(cam_name)
                logger.warning(
                    f"相机 {cam_name} 在frame {frame_idx}及之前都不存在，"
                    f"从配置中移除此相机"
                )
                break  # 不再处理此相机的后续帧
```

---

## 🔧 实现要点

### 1. 预验证阶段

在`_prevalidate_files()`中检查必需相机：

```python
def _prevalidate_files(self) -> None:
    """预验证：检查必需相机是否存在"""
    required_cameras = ['cam_high_rgb', 'cam_left_wrist_rgb', 'cam_right_wrist_rgb']
    
    for task_path in self.path_task_dict.keys():
        # 检查第一个episode的第0帧
        first_frame_dir = task_path / "camera" / "0"
        
        if not first_frame_dir.exists():
            raise FileNotFoundError(f"Episode第0帧不存在: {first_frame_dir}")
        
        missing_required = []
        for cam_name in required_cameras:
            cam_file = first_frame_dir / f"{cam_name}.jpg"
            if not cam_file.exists():
                missing_required.append(cam_name)
        
        if missing_required:
            raise CriticalDataError(
                f"❌ 缺少必需相机，跳过整个episode\n"
                f"   Task: {task_path}\n"
                f"   缺失相机: {missing_required}\n"
                f"   💡 必需相机: {required_cameras}"
            )
```

### 2. 运行时容错

在`_gen_images_frame()`中处理可选相机的缺失：

```python
def _gen_images_frame(self, task_path: Path, ep_idx: int, frame_idx: int) -> dict:
    """生成单帧的图像数据"""
    images_dict = {}
    
    for cam_config in self.converter_config['features']['observation']['images']:
        cam_name = cam_config['cam_name']
        
        # 构造图像路径
        frame_dir = task_path / "camera" / str(frame_idx)
        img_path = frame_dir / f"{cam_name}.jpg"
        
        # 检查必需相机
        required_cameras = ['cam_high_rgb', 'cam_left_wrist_rgb', 'cam_right_wrist_rgb']
        
        if not img_path.exists():
            if cam_name in required_cameras:
                # ❌ 必需相机缺失 -> 抛出错误，跳过episode
                raise CriticalDataError(
                    f"Frame {frame_idx}: 必需相机 {cam_name} 缺失"
                )
            else:
                # ⚠️ 可选相机缺失 -> 尝试复制上一帧
                if frame_idx > 0:
                    prev_path = task_path / "camera" / str(frame_idx - 1) / f"{cam_name}.jpg"
                    if prev_path.exists():
                        # 📋 复制上一帧
                        image = Image.open(prev_path)
                        self.logger.warning(
                            f"Frame {frame_idx}: {cam_name} 缺失，"
                            f"已复制frame {frame_idx-1}"
                        )
                    else:
                        # ❌ 上一帧也不存在，跳过此相机
                        self.logger.warning(
                            f"Frame {frame_idx}: {cam_name} 及上一帧都缺失，跳过此相机"
                        )
                        continue
                else:
                    # ❌ 第0帧就缺失，跳过此相机
                    self.logger.warning(
                        f"Frame 0: {cam_name} 不存在，跳过此相机"
                    )
                    continue
        else:
            # ✅ 正常读取
            image = Image.open(img_path)
        
        # 转换为numpy数组
        images_dict[cam_name] = np.array(image)
    
    return images_dict
```

### 3. 动态移除相机

如果某个可选相机在第0帧就不存在，应该从配置中移除：

```python
def __init__(self, ...):
    """初始化时检查并移除不可用的相机"""
    super().__init__(...)
    
    # 检查第一个task的第一个episode的第0帧
    first_task_path = list(self.path_task_dict.keys())[0]
    frame_0_dir = first_task_path / "camera" / "0"
    
    if frame_0_dir.exists():
        # 移除不存在的可选相机
        available_images = []
        required_cameras = ['cam_high_rgb', 'cam_left_wrist_rgb', 'cam_right_wrist_rgb']
        
        for cam_config in self.converter_config['features']['observation']['images']:
            cam_name = cam_config['cam_name']
            cam_file = frame_0_dir / f"{cam_name}.jpg"
            
            if cam_file.exists():
                available_images.append(cam_config)
            elif cam_name in required_cameras:
                # 必需相机不存在会在预验证阶段抛错
                available_images.append(cam_config)
            else:
                # 可选相机不存在，移除
                self.logger.info(
                    f"ℹ️  相机 {cam_name} 在数据中不存在，已从配置中移除"
                )
        
        # 更新配置
        self.converter_config['features']['observation']['images'] = available_images
```

---

## 📊 各版本差异

### ruantong (default_version)

**相机列表**:
- ✅ **cam_high_rgb** (必需)
- ✅ **cam_left_wrist_rgb** (必需)
- ✅ **cam_right_wrist_rgb** (必需)
- 🔶 cam_high_center_fisheye_rgb (可选)
- 🔶 cam_back_left_fisheye_rgb (可选)
- 🔶 cam_back_right_fisheye_rgb (可选)
- 🔶 cam_high_left_fisheye_rgb (可选)
- 🔶 cam_high_right_fisheye_rgb (可选)

**总计**: 8个相机（3个必需 + 5个可选鱼眼）

### ruantong_gt01_no_depth

**相机列表**:
- ✅ **cam_high_rgb** (必需) - ⚠️ 数据中可能没有，需确认
- ✅ **cam_left_wrist_rgb** (必需)
- ✅ **cam_right_wrist_rgb** (必需)
- 🔶 cam_high_center_fisheye_rgb (可选)
- 🔶 cam_back_left_fisheye_rgb (可选)
- 🔶 cam_back_right_fisheye_rgb (可选)
- 🔶 cam_high_left_fisheye_rgb (可选) - 配置中缺失，需添加
- 🔶 cam_high_right_fisheye_rgb (可选) - 配置中缺失，需添加

**总计**: 8个相机（3个必需 + 5个可选鱼眼）

**⚠️ 注意**: 根据之前的诊断，gt01_no_depth数据中可能没有`cam_high_rgb`（原`head_color`），需要：
1. 运行诊断脚本确认
2. 如果确实没有，需要调整必需相机列表

### ruantong_gt02_new

**相机列表**:
- ✅ **cam_high_rgb** (必需)
- ✅ **cam_left_wrist_rgb** (必需)
- ✅ **cam_right_wrist_rgb** (必需)

**总计**: 3个相机（全部必需，无鱼眼）

---

## 🎯 总结

### 容错规则

1. **必需相机 (3个)**:
   - `cam_high_rgb`
   - `cam_left_wrist_rgb`
   - `cam_right_wrist_rgb`
   - **任何一个缺失 → 跳过整个episode**

2. **可选相机 (鱼眼等)**:
   - 如果某帧缺失 → 复制上一帧
   - 如果第0帧就缺失 → 从配置中移除该相机
   - **不影响episode的转换**

### 实现位置

- ✅ `_prevalidate_files()`: 检查必需相机
- ✅ `__init__()`: 动态移除不可用的可选相机
- ✅ `_gen_images_frame()`: 运行时容错（复制上一帧）

### 日志记录

- **必需相机缺失**: `CriticalDataError` + 跳过episode
- **可选相机缺失**: `logger.warning()` + 复制上一帧或移除相机

---

**文档版本**: v1.0  
**状态**: 设计完成，待实施  
**相关文件**: 
- `converter_config_ruantong.yaml` (已重命名相机)
- `converter_config_ruantong_gt01_no_depth.yaml` (已重命名相机)
- `converter_config_ruantong_gt02_new.yaml` (已重命名相机)

