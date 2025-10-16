# Mayi 数据集转换器更新说明

## 📅 更新日期
2025-10-16

## 🎯 更新原因
Mayi 数据集实际结构与原配置不符：
- ❌ `arm/jointState/` 文件夹为空，没有关节数据
- ✅ 包含丰富的传感器数据：gripper, IMU, localization

## 📊 数据集实际结构

### 有数据的文件夹（各 838 帧）

1. **图像数据 - RGB (5个相机)**
   - `camera/color/camera_realsense_c/*.jpg` - RealSense 中心相机
   - `camera/color/pikaDepthCamera_l/*.jpg` - Pika 左深度相机 RGB
   - `camera/color/pikaDepthCamera_r/*.jpg` - Pika 右深度相机 RGB
   - `camera/color/pikaFisheyeCamera_l/*.jpg` - Pika 左鱼眼相机
   - `camera/color/pikaFisheyeCamera_r/*.jpg` - Pika 右鱼眼相机

2. **图像数据 - Depth (3个相机)**
   - `camera/depth/pikaDepthCamera_c/*.png` - 中心深度图
   - `camera/depth/pikaDepthCamera_l/*.png` - 左深度图
   - `camera/depth/pikaDepthCamera_r/*.png` - 右深度图

3. **夹爪数据 (2个)**
   - `gripper/encoder/pika_l/*.json` - 左夹爪
   - `gripper/encoder/pika_r/*.json` - 右夹爪
   - 字段：`{"angle": 1.72, "distance": 0}`

4. **IMU 数据 (2个)**
   - `imu/9axis/pika_l/*.json` - 左手 IMU
   - `imu/9axis/pika_r/*.json` - 右手 IMU
   - 字段：
     ```json
     {
       "angular_velocity": {"x": -0.313, "y": -0.076, "z": -0.313},
       "linear_acceleration": {"x": 0.058, "y": 6.431, "z": 7.45},
       "orientation": {"w": -0.019, "x": 0.539, "y": 0.841, "z": 0.006}
     }
     ```

5. **定位数据 (2个)**
   - `localization/pose/pika_l/*.json` - 左手位姿
   - `localization/pose/pika_r/*.json` - 右手位姿
   - 字段：
     ```json
     {
       "x": -0.043, "y": 0.087, "z": -0.176,
       "roll": 0.049, "pitch": 0.913, "yaw": 0.080
     }
     ```

### 空文件夹（无需处理）
- `arm/jointState/` - 空
- `arm/endPose/` - 空
- `lidar/pointCloud/` - 空
- `robotBase/vel/` - 空
- `tf/transform/` - 空
- `camera/pointCloud/` - 空

## 🔧 配置文件更新

### 新配置文件
`converter_config_mayi_new.yaml`

### 状态维度 (36维)

1. **夹爪 (4维)**
   - 左: angle + distance (2维)
   - 右: angle + distance (2维)

2. **IMU (20维)**
   - 左手: angular_velocity(3) + linear_acceleration(3) + orientation(4) = 10维
   - 右手: angular_velocity(3) + linear_acceleration(3) + orientation(4) = 10维

3. **位姿 (12维)**
   - 左手: x, y, z, roll, pitch, yaw (6维)
   - 右手: x, y, z, roll, pitch, yaw (6维)

### 图像配置 (8个相机)
- 5个 RGB 相机
- 3个 Depth 相机（配置 `is_depth: true`）

## 💻 代码修改

### 文件：`lerobot_format_converter_jpg_json.py`

#### 1. 图像加载支持深度图
```python
# 新增参数
is_depth = args.get('is_depth', False)

# 根据类型选择目录
if is_depth:
    camera_base_dir = ep_dir / "camera" / "depth"
else:
    camera_base_dir = ep_dir / "camera" / "color"

# 深度图处理
if is_depth:
    img_array = np.array(img)
    if img_array.ndim == 2:
        img_array = np.stack([img_array] * 3, axis=-1)
```

#### 2. 新增数据加载方法
```python
def _load_imu_data(self, ep_dir: Path, imu_side: str) -> list[dict]:
    """加载IMU数据"""
    imu_dir = ep_dir / "imu" / "9axis" / imu_side
    # ...

def _load_localization_data(self, ep_dir: Path, localization_side: str) -> list[dict]:
    """加载定位/位姿数据"""
    localization_dir = ep_dir / "localization" / "pose" / localization_side
    # ...
```

#### 3. 扩展状态缓冲区
```python
def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> dict:
    buffer = {
        # 关节数据（pika, aloha等）
        'puppet_left': ...,
        'puppet_right': ...,
        
        # 夹爪数据
        'gripper_pika_l': self._load_gripper_data(ep_dir, 'pika_l'),
        'gripper_pika_r': self._load_gripper_data(ep_dir, 'pika_r'),
        
        # IMU数据（mayi）
        'imu_pika_l': self._load_imu_data(ep_dir, 'pika_l'),
        'imu_pika_r': self._load_imu_data(ep_dir, 'pika_r'),
        
        # 定位数据（mayi）
        'localization_pika_l': self._load_localization_data(ep_dir, 'pika_l'),
        'localization_pika_r': self._load_localization_data(ep_dir, 'pika_r'),
    }
```

#### 4. 支持新数据类型的状态提取
```python
def _get_frame_sub_states(...) -> np.ndarray:
    data_type = args_dict.get('data_type', 'joint')
    
    if data_type == 'gripper':
        # 夹爪数据处理
        gripper_side = args_dict.get('gripper_side', 'pika_l')
        field_name = args_dict.get('field_name', 'angle')
        buffer_key = f'gripper_{gripper_side}'
        # ...
    
    elif data_type == 'imu':
        # IMU数据处理
        imu_side = args_dict.get('imu_side', 'pika_l')
        field_name = args_dict.get('field_name', 'angular_velocity')
        subfields = args_dict.get('subfields', ['x', 'y', 'z'])
        buffer_key = f'imu_{imu_side}'
        # ...
    
    elif data_type == 'localization':
        # 定位数据处理
        localization_side = args_dict.get('localization_side', 'pika_l')
        field_names = args_dict.get('field_names', ['x', 'y', 'z', 'roll', 'pitch', 'yaw'])
        buffer_key = f'localization_{localization_side}'
        # ...
    
    else:
        # 传统关节数据处理
        # ...
```

## 🔑 配置示例

### Gripper 配置
```yaml
- names:
    - mayi_left_gripper_angle
  args:
    data_type: gripper
    gripper_side: pika_l
    field_name: angle
```

### IMU 配置
```yaml
- names:
    - mayi_left_imu_angular_velocity_x
    - mayi_left_imu_angular_velocity_y
    - mayi_left_imu_angular_velocity_z
  args:
    data_type: imu
    imu_side: pika_l
    field_name: angular_velocity
    subfields: [x, y, z]
```

### Localization 配置
```yaml
- names:
    - mayi_left_pose_x
    - mayi_left_pose_y
    - mayi_left_pose_z
    - mayi_left_pose_roll
    - mayi_left_pose_pitch
    - mayi_left_pose_yaw
  args:
    data_type: localization
    localization_side: pika_l
    field_names: [x, y, z, roll, pitch, yaw]
```

### Depth Camera 配置
```yaml
- cam_name: pikaDepthCamera_c_depth
  args:
    cam_name: pikaDepthCamera_c_depth
    camera_folder: pikaDepthCamera_c
    is_depth: true
```

## ✅ 兼容性

### 向后兼容
- ✅ 原有的 Pika 和 Aloha 数据集配置仍然有效
- ✅ 传统的 `joint_type` 配置方式保持不变
- ✅ 新增 `data_type` 字段，默认为 `'joint'`

### 支持的数据类型
1. `joint` - 传统关节数据（默认）
2. `gripper` - 夹爪数据（新）
3. `imu` - IMU 传感器数据（新）
4. `localization` - 定位/位姿数据（新）

## 🚀 使用方法

### 1. 使用新配置文件
```bash
# 在 converter_factory_config.yaml 中注册新版本
mayi:
- version: new_version
  verison_description: mayi with sensor data (gripper, IMU, localization)
  converter_type: lerobot_format_converter_jpg_json.LerobotFormatConverterJpgJson
  converter_config_path: converter_config_mayi_new.yaml
```

### 2. 转换数据集
```python
converter = LerobotFormatConverterFactory.create_converter(
    dataset_path="data/mayi",
    device_model="mayi",
    version="new_version",
    # ...
)
converter.convert()
```

## 📝 注意事项

1. **帧数对齐**: 所有数据源（图像、gripper、IMU、localization）都有 838 帧，已验证对齐
2. **深度图格式**: 单通道深度图会自动扩展为3通道以兼容 LeRobot 格式
3. **零值填充**: 如果某帧数据缺失，自动填充零值
4. **JSON 字段**: 确保 JSON 文件包含配置中指定的所有字段

## 🐛 已知问题
无

## 📚 参考
- 原配置: `converter_config_mayi.yaml`
- 新配置: `converter_config_mayi_new.yaml`
- 转换器: `lerobot_format_converter_jpg_json.py`
