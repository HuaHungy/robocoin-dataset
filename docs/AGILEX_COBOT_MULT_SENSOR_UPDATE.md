# Agilex Cobot Decoupled Magic (mult_sensor) 配置更新

## 📅 更新日期
2025-10-16

## 🎯 更新要点

### 关键发现：
1. **夹爪数据在关节数据中** - `position[6]` 是夹爪，不在独立的 gripper 文件夹
2. **不使用 master 数据作为 action** - 使用 `timeline_offset: 1` 
3. **包含位姿数据** - `localization/pose/puppetLeft` 和 `puppetRight`
4. **帧数不匹配** - 相机 ~511帧，关节/位姿 ~3401-3402帧

## 📊 数据集实际结构

### ✅ 有数据的文件夹

1. **关节状态数据 (4个，3401-3402帧)**
   - `arm/jointState/puppetLeft/*.json` - 3402 帧
   - `arm/jointState/puppetRight/*.json` - 3401 帧
   - `arm/jointState/masterLeft/*.json` - 3402 帧
   - `arm/jointState/masterRight/*.json` - 3401 帧
   
   **JSON 结构**:
   ```json
   {
     "position": [j0, j1, j2, j3, j4, j5, gripper],  // 7维：6关节 + 1夹爪
     "velocity": [v0, v1, v2, v3, v4, v5, v_gripper], // 7维
     "effort": [e0, e1, e2, e3, e4, e5, e_gripper]    // 7维
   }
   ```
   
   **重要**: `position[0:6]` 是关节，`position[6]` 是夹爪！

2. **RGB 相机 (3个，511-512帧)**
   - `camera/color/front/*.jpg` - 511 帧
   - `camera/color/left/*.jpg` - 512 帧
   - `camera/color/right/*.jpg` - 511 帧

3. **深度相机 (3个，511-512帧)**
   - `camera/depth/front/*.png` - 511 帧
   - `camera/depth/left/*.png` - 512 帧
   - `camera/depth/right/*.png` - 511 帧

4. **定位数据 (2个，3401-3402帧)**
   - `localization/pose/puppetLeft/*.json` - 3402 帧
   - `localization/pose/puppetRight/*.json` - 3401 帧
   
   **JSON 结构**:
   ```json
   {
     "x": 0.052265,
     "y": -0.001149,
     "z": 0.164215,
     "roll": -3.111,
     "pitch": 1.294,
     "yaw": 3.140
   }
   ```

### ❌ 空文件夹（无需处理）
- `arm/endPose/` - 空
- `gripper/encoder/` - 空（夹爪数据在关节 JSON 里）
- `imu/9axis/` - 空
- `camera/pointCloud/` - 空
- `lidar/pointCloud/` - 空
- `robotBase/vel/` - 空

## 🔧 配置文件

### 新配置文件
`converter_config_agilex_cobot_decoupled_magic_mult_sensor_new.yaml`

### 状态维度 (26维)

1. **左臂关节 (6维)** - `puppetLeft position[0:6]`
2. **左夹爪 (1维)** - `puppetLeft position[6]`
3. **右臂关节 (6维)** - `puppetRight position[0:6]`
4. **右夹爪 (1维)** - `puppetRight position[6]`
5. **左手位姿 (6维)** - `localization/pose/puppetLeft`
6. **右手位姿 (6维)** - `localization/pose/puppetRight`

**总计**: 6 + 1 + 6 + 1 + 6 + 6 = **26 维**

### 图像 (6个相机)
- 3个 RGB 相机
- 3个 Depth 相机

## 📝 配置示例

### 1. 关节配置（前6个）
```yaml
- names:
    - puppet_left_joint_0
    - puppet_left_joint_1
    - puppet_left_joint_2
    - puppet_left_joint_3
    - puppet_left_joint_4
    - puppet_left_joint_5
  args:
    joint_type: puppetLeft
    field_name: position
    range_from: 0
    range_to: 6  # 只取前6个
```

### 2. 夹爪配置（第7个）
```yaml
- names:
    - puppet_left_gripper
  args:
    joint_type: puppetLeft
    field_name: position
    range_from: 6
    range_to: 7  # 只取第7个
```

### 3. 位姿配置
```yaml
- names:
    - puppet_left_pose_x
    - puppet_left_pose_y
    - puppet_left_pose_z
    - puppet_left_pose_roll
    - puppet_left_pose_pitch
    - puppet_left_pose_yaw
  args:
    data_type: localization
    localization_side: puppetLeft
    field_names: [x, y, z, roll, pitch, yaw]
```

### 4. Action 配置
```yaml
action:
  timeline_offset: 1  # 使用时间偏移，不使用 master
  sub_action:
    # 使用相同的 puppetLeft/puppetRight 配置
    - names:
        - puppet_left_joint_0
        # ...
      args:
        joint_type: puppetLeft  # 不使用 masterLeft
        field_name: position
        range_from: 0
        range_to: 6
```

## 💻 代码修改

### 文件：`lerobot_format_converter_jpg_json.py`

#### 扩展状态缓冲区别名
```python
def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> dict:
    buffer = {
        # 支持驼峰命名和下划线命名
        'puppetLeft': self._load_joint_state_data(ep_dir, 'puppetLeft'),
        'puppetRight': self._load_joint_state_data(ep_dir, 'puppetRight'),
        'puppet_left': self._load_joint_state_data(ep_dir, 'puppetLeft'),
        'puppet_right': self._load_joint_state_data(ep_dir, 'puppetRight'),
        
        # 定位数据支持多种命名
        'localization_puppetLeft': self._load_localization_data(ep_dir, 'puppetLeft'),
        'localization_puppetRight': self._load_localization_data(ep_dir, 'puppetRight'),
        'localization_pika_l': self._load_localization_data(ep_dir, 'pika_l'),
        'localization_pika_r': self._load_localization_data(ep_dir, 'pika_r'),
    }
```

## 🔑 与原配置的差异

### 原配置 (converter_config_agilex_cobot_decoupled_magic_mult_sensor.yaml)
```yaml
state:
  sub_state:
    - names: [master_left_joint_0, ..., master_left_joint_6]  # ❌ 7维，包含夹爪
      args:
        joint_type: puppetLeft  # ❌ 名字不一致
        range_to: 7

action:
  sub_action:
    - args:
        joint_type: masterLeft  # ❌ 使用 master 数据
        range_to: 7
```

### 新配置 (new 版本)
```yaml
state:
  sub_state:
    # ✅ 分开配置关节和夹爪
    - names: [puppet_left_joint_0, ..., puppet_left_joint_5]  # 6维关节
      args:
        joint_type: puppetLeft
        range_from: 0
        range_to: 6
    
    - names: [puppet_left_gripper]  # 1维夹爪
      args:
        joint_type: puppetLeft
        range_from: 6
        range_to: 7
    
    # ✅ 新增位姿数据
    - names: [puppet_left_pose_x, ..., puppet_left_pose_yaw]
      args:
        data_type: localization
        localization_side: puppetLeft

action:
  timeline_offset: 1  # ✅ 使用时间偏移
  sub_action:
    # ✅ 使用 puppetLeft，不使用 masterLeft
    - args:
        joint_type: puppetLeft
        range_to: 6
```

## ⚠️ 注意事项

1. **帧数不匹配问题**
   - 相机数据: ~511 帧
   - 关节/位姿数据: ~3401 帧
   - 转换时需要处理采样率差异

2. **夹爪数据位置**
   - 不在单独的 gripper 文件夹
   - 在关节 JSON 的 `position[6]`
   - 使用 `range_from: 6, range_to: 7` 提取

3. **不使用 master 数据**
   - action 使用 `timeline_offset: 1`
   - 使用 puppet 数据的下一帧作为 action
   - master 数据存在但不使用

4. **命名规范**
   - 配置使用: `puppetLeft`, `puppetRight`
   - 代码支持别名: `puppet_left`, `puppet_right`

## 🚀 使用方法

### 注册新版本
```yaml
# converter_factory_config.yaml
agilex_cobot_decoupled_magic:
  - version: mult_sensor_new
    verison_description: mult_sensor with localization, separate gripper extraction
    converter_type: lerobot_format_converter_jpg_json.LerobotFormatConverterJpgJson
    converter_config_path: converter_config_agilex_cobot_decoupled_magic_mult_sensor_new.yaml
```

### 转换数据集
```python
converter = LerobotFormatConverterFactory.create_converter(
    dataset_path="data/agilex_cobot_decoupled_magic",
    device_model="agilex_cobot_decoupled_magic",
    version="mult_sensor_new",
    # ...
)
converter.convert()
```

## 📚 相关文件
- 原配置: `converter_config_agilex_cobot_decoupled_magic_mult_sensor.yaml`
- 新配置: `converter_config_agilex_cobot_decoupled_magic_mult_sensor_new.yaml`
- 转换器: `lerobot_format_converter_jpg_json.py`
- Mayi 更新文档: `MAYI_CONVERTER_UPDATE.md`
