# 软通天擎 GT02 新格式配置

## 📅 更新日期
2025-10-17

## 🎯 问题描述

### 错误信息
```
KeyError: "❌ H5 state path not found.
   🗂️  Requested h5_path: '/state/joint/position'
   📋 Available paths: ['action', 'state', 'timestamp']"
```

### 数据集路径
`/mnt/nas/synnas/docker2/外部数据/软通天擎/gt02/rt/`

## 📊 新 H5 文件结构

### 完整结构
```
/state/
  /robot/
    positions: (346, 18) dtype=float64  - 18个关节位置
    velocities: (346, 18) dtype=float64 - 18个关节速度
    efforts: (346, 18) dtype=float64    - 18个关节力矩
    temperatures: (346, 18) dtype=float64 - 18个关节温度
  
  /gripper/
    positions: (346, 2) dtype=float64    - 2个夹爪位置
    velocities: (346, 2) dtype=float64   - 2个夹爪速度
    efforts: (346, 2) dtype=float64      - 2个夹爪力矩
    temperatures: (163, 2) dtype=float64 - 2个夹爪温度 (帧数不同!)

/action/
  /robot/
    positions: (346, 18) - 全是 nan ❌
    velocities: (346, 18) - 全是 nan ❌
    efforts: (346, 18) - 全是 nan ❌
    ...
  
  /gripper/
    positions: (346, 2) - 全是 nan ❌
    ...

/timestamp: (346,) dtype=int64
```

## 🔑 关键差异

### 旧格式 (converter_config_ruantong_gt02.yaml)
```yaml
state:
  sub_state:
    - h5_path: /state/joint/position     # ❌ 不存在
      range_from: 0
      range_to: 7
    
    - h5_path: /state/end/position       # ❌ 不存在
      range_from: 0
      range_to: 3
    
    - h5_path: /state/effector/position  # ❌ 不存在
      range_from: 0
      range_to: 2
```

### 新格式 (converter_config_ruantong_gt02_new.yaml)
```yaml
state:
  sub_state:
    - names: [robot_joint_0, ..., robot_joint_17]  # ✅ 18个关节
      args:
        h5_path: /state/robot/positions
        range_from: 0
        range_to: 18
    
    - names: [gripper_left_position, gripper_right_position]  # ✅ 2个夹爪
      args:
        h5_path: /state/gripper/positions
        range_from: 0
        range_to: 2
```

## 📝 配置文件

### 新配置文件
`converter_config_ruantong_gt02_new.yaml`

### 状态维度
- **机器人关节**: 18维 (`/state/robot/positions`)
- **夹爪**: 2维 (`/state/gripper/positions`)
- **总计**: 20维

### Action 处理
```yaml
action:
  timeline_offset: 1  # Action 数据全是 nan，使用 timeline_offset
  sub_action:
    # 使用相同的 state 路径
    - h5_path: /state/robot/positions
      range_from: 0
      range_to: 18
```

## ⚠️ 注意事项

### 1. 关节数量变化
- **旧格式**: 14个关节 (7左臂 + 7右臂)
- **新格式**: 18个关节 (robot_joint_0 ~ robot_joint_17)

### 2. 夹爪温度帧数不一致
```
state/gripper/temperatures: shape=(163, 2)  # ⚠️ 只有163帧
state/gripper/positions: shape=(346, 2)     # 346帧
```
**解决方案**: 不使用 temperatures 数据

### 3. Action 数据全是 NaN
```
action/robot/positions: 全是 nan
action/gripper/positions: 全是 nan
```
**解决方案**: 使用 `timeline_offset: 1`，从 state 的下一帧获取 action

### 4. 数据示例
```python
# 第一帧数据
state/robot/positions[0]: 
[ 1.22e-01, -1.14e-01, -5.03e-01, nan, 3.14e-02, 3.13e-01, 
 -1.64e+00,  1.59e+00,  1.79e+00, 8.51e-03, 5.39e-01, 8.72e-06,
 -3.00e-01,  1.60e+00, -1.60e+00, -1.80e+00, 4.75e-06, -1.52e-05]

state/gripper/positions[0]: [0., 0.]
```

**⚠️ 注意**: `robot_joint_3` 是 nan！

## 🔧 如何使用

### 1. 注册新版本
```yaml
# converter_factory_config.yaml
ruantong:
  - version: gt02_new
    verison_description: GT02 new format with robot/gripper structure
    converter_type: lerobot_format_converter_h5_jpg.LerobotFormatConverterH5Jpg
    converter_config_path: converter_config_ruantong_gt02_new.yaml
```

### 2. 转换数据集
```bash
python scripts/convert_dataset.py \
  --device_model ruantong \
  --version gt02_new \
  --dataset_path "/mnt/nas/synnas/docker2/外部数据/软通天擎/gt02/rt"
```

## 🐛 已知问题

### 1. robot_joint_3 是 NaN
某些关节位置包含 NaN 值，需要在转换时处理

### 2. 温度数据帧数不匹配
temperatures 数据只有 163 帧，而 positions 有 346 帧

### 3. Action 数据无效
所有 action 数据都是 NaN，必须使用 timeline_offset

## 📚 相关文件
- 旧配置: `converter_config_ruantong_gt02.yaml`
- 新配置: `converter_config_ruantong_gt02_new.yaml`
- 转换器: `lerobot_format_converter_h5_jpg.py`

## 🔍 如何识别格式

### 检查 H5 文件结构
```python
import h5py

f = h5py.File('aligned_joints.h5', 'r')
if 'state/robot' in f:
    print("新格式 - 使用 converter_config_ruantong_gt02_new.yaml")
elif 'state/joint' in f:
    print("旧格式 - 使用 converter_config_ruantong_gt02.yaml")
```

### 快速命令
```bash
python3 -c "import h5py; f=h5py.File('aligned_joints.h5','r'); print(list(f['state'].keys()))"
# 新格式输出: ['gripper', 'robot']
# 旧格式输出: ['joint', 'end', 'waist', 'head', 'effector', ...]
```

## ✅ 验证清单

- [x] 创建新配置文件
- [x] 状态维度正确 (18 + 2 = 20维)
- [x] Action 使用 timeline_offset
- [ ] 需要测试转换
- [ ] 需要处理 NaN 值
- [ ] 需要验证转换结果
