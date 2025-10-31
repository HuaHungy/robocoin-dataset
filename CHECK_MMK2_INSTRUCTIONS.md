# 检查MMK2数据集维度 - 操作指南

**目标**: 找出MMK2数据集实际的action维度，确定应该使用哪个配置

---

## 📍 文件位置

### **数据集根目录**
```
/mnt/nas/synnas/docker/6discover_robotics_aitbot_mmk2/storage_peaches_and_pears/
```

### **具体的episode目录**（选第一个episode检查）
```
/mnt/nas/synnas/docker/6discover_robotics_aitbot_mmk2/storage_peaches_and_pears/the left hand throws the peach into the left compartment, the right hand throws the pear into the right compartment./0/
```

### **需要的文件**
```
📄 episode_0.bson              ← 包含arms、head、spine的action数据
📄 xhand_control_data.bson     ← 包含双手的action数据
```

---

## 🚀 快速检查（推荐）

### **方法1: 使用检查脚本（最简单）**

```bash
cd /home/liu/program/robocoin-dataset

# 运行检查脚本（一键输出所有信息）
python scripts/diagnostics/check_mmk2_action_dimensions.py \
    "/mnt/nas/synnas/docker/6discover_robotics_aitbot_mmk2/storage_peaches_and_pears/the left hand throws the peach into the left compartment, the right hand throws the pear into the right compartment./0"
```

**输出示例**：
```
🔍 MMK2 Action Dimension Analysis
================================================================================

📁 Episode Directory:
   /mnt/nas/.../0

--------------------------------------------------------------------------------
📄 Part 1: episode_0.bson (arms + head + spine)
--------------------------------------------------------------------------------
✅ 成功读取，共 644 帧

📋 action字段的keys: ['left_arm', 'right_arm', 'spine']

🔸 左臂 (left_arm):
   ✅ action/left_arm/joint_state/pos: 6 维
   📊 数据示例: [0.1, 0.2, 0.3]...

🔸 右臂 (right_arm):
   ✅ action/right_arm/joint_state/pos: 6 维
   📊 数据示例: [0.1, 0.2, 0.3]...

🔸 头部 (head):
   ⚠️  没有 head 字段 (这是正常的，lite版本不需要head)

🔸 脊柱 (spine):
   ✅ action/spine/joint_state/pos: 1 维
   📊 数据示例: [0.0]

📐 Part 1 小计: 13 维
   left_arm(6) + right_arm(6) + head(0) + spine(1)

--------------------------------------------------------------------------------
📄 Part 2: xhand_control_data.bson (hands)
--------------------------------------------------------------------------------
✅ 成功读取，共 644 帧

📋 action字段的keys: ['left_hand', 'right_hand']

🔸 左手 (left_hand):
   ✅ action.left_hand: 11 维  ← 注意：正常应该是12维！
   📊 数据示例: [0.1, 0.2, 0.3]...

🔸 右手 (right_hand):
   ✅ action.right_hand: 11 维  ← 注意：正常应该是12维！
   📊 数据示例: [0.1, 0.2, 0.3]...

📐 Part 2 小计: 22 维

================================================================================
📊 最终统计
================================================================================

🔢 各组件维度:
   ✅ left_arm        :  6 维
   ✅ right_arm       :  6 维
   ❌ head           :  0 维
   ✅ spine          :  1 维
   ✅ left_hand      : 11 维  ← 缺1维
   ✅ right_hand     : 11 维  ← 缺1维

================================================================================
🎯 总维度: 35 维
================================================================================

📋 配置对比:
--------------------------------------------------------------------------------
   full      : 39D  ❌ 不匹配  (期望比实际多 4 维)
              (包含head (2维))
   lite      : 37D  ❌ 不匹配  (期望比实际多 2 维)
              (不含head)

💡 建议:
--------------------------------------------------------------------------------
   ⚠️  当前维度 35D 不匹配任何现有配置！
   📝 需要创建新配置: converter_config_discover_robotics_aitbot_mmk2_35d.yaml

   🔍 可能的原因（35D = 37D - 2D）:
      → 双手各缺1维 (11+11 instead of 12+12)

   📋 下一步:
      1. 检查多个episode确认这是普遍情况
      2. 根据实际维度创建新配置文件
      3. 更新 converter_factory_config.yaml
      4. 更新数据库 device_model_version
```

---

## 🔍 手动检查（如果脚本失败）

### **Step 1: 进入episode目录**

```bash
cd "/mnt/nas/synnas/docker/6discover_robotics_aitbot_mmk2/storage_peaches_and_pears/the left hand throws the peach into the left compartment, the right hand throws the pear into the right compartment./0"

# 查看文件
ls -lh
```

应该看到：
```
episode_0.bson
xhand_control_data.bson
camera_head/
camera_left_wrist/
camera_right_wrist/
camera_third_view/
```

### **Step 2: 使用Python检查BSON文件**

```python
import bson
from pathlib import Path

# 检查 episode_0.bson
episode_dir = Path("/mnt/nas/synnas/docker/6discover_robotics_aitbot_mmk2/storage_peaches_and_pears/the left hand throws the peach into the left compartment, the right hand throws the pear into the right compartment./0")

with open(episode_dir / "episode_0.bson", "rb") as f:
    data = bson.decode_all(f.read())
    frame = data[0]  # 第一帧
    action = frame['action']
    
    print("episode_0.bson 中的 action 组件:")
    print(f"  action keys: {list(action.keys())}")
    
    if 'left_arm' in action:
        print(f"  left_arm/joint_state/pos: {len(action['left_arm']['joint_state']['pos'])} 维")
    
    if 'right_arm' in action:
        print(f"  right_arm/joint_state/pos: {len(action['right_arm']['joint_state']['pos'])} 维")
    
    if 'head' in action:
        print(f"  head/joint_state/pos: {len(action['head']['joint_state']['pos'])} 维")
    else:
        print(f"  head: 不存在 (0维)")
    
    if 'spine' in action:
        print(f"  spine/joint_state/pos: {len(action['spine']['joint_state']['pos'])} 维")

# 检查 xhand_control_data.bson
with open(episode_dir / "xhand_control_data.bson", "rb") as f:
    data = bson.decode_all(f.read())
    frame = data[0]
    action = frame['action']
    
    print("\nxhand_control_data.bson 中的 action 组件:")
    print(f"  action keys: {list(action.keys())}")
    
    if 'left_hand' in action:
        print(f"  left_hand: {len(action['left_hand'])} 维")
    
    if 'right_hand' in action:
        print(f"  right_hand: {len(action['right_hand'])} 维")

# 计算总维度
print("\n总维度 = left_arm + right_arm + head + spine + left_hand + right_hand")
```

---

## 🎯 预期结果

### **场景1: 如果是37D（lite版本）**
```
left_arm: 6
right_arm: 6
head: 0
spine: 1
left_hand: 12
right_hand: 12
总计: 37D ✅

→ 使用配置: third_view_lite
→ 数据库设置: device_model_version = 'third_view_lite'
```

### **场景2: 如果是39D（full版本）**
```
left_arm: 6
right_arm: 6
head: 2
spine: 1
left_hand: 12
right_hand: 12
总计: 39D ✅

→ 使用配置: third_view_full
→ 数据库设置: device_model_version = 'third_view_full'
```

### **场景3: 如果是35D（需要新配置）**
```
left_arm: 6
right_arm: 6
head: 0
spine: 1
left_hand: 11  ← 少1维
right_hand: 11  ← 少1维
总计: 35D ⚠️

→ 需要创建新配置: converter_config_mmk2_35d.yaml
→ 数据库设置: device_model_version = '35d_version'
```

---

## 📝 检查多个episode确认

**不要只检查一个episode！** 至少检查3-5个episode确认是普遍情况：

```bash
# 检查episode 0
python scripts/diagnostics/check_mmk2_action_dimensions.py "/path/to/task/0"

# 检查episode 1
python scripts/diagnostics/check_mmk2_action_dimensions.py "/path/to/task/1"

# 检查episode 2
python scripts/diagnostics/check_mmk2_action_dimensions.py "/path/to/task/2"
```

**如果所有episode都是35D** → 确认需要创建新配置

**如果有的37D有的35D** → 可能是数据采集过程中的变化，建议联系数据提供方

---

## 🔧 确认后的处理

### **如果是37D或39D（匹配现有配置）**

```sql
-- 只需更新数据库
UPDATE dmv_annotation 
SET device_model_version = 'third_view_lite'  -- 或 'third_view_full'
WHERE dataset_uuid = '你的数据集UUID';
```

### **如果是35D（需要新配置）**

参考 `MMK2_DIMENSION_MISMATCH_GUIDE.md` 中的详细步骤：

1. 创建配置文件 `converter_config_mmk2_35d.yaml`
2. 修改action部分的维度（删除缺失的字段）
3. 更新 `converter_factory_config.yaml`
4. 更新数据库

---

## ❓ 需要帮助？

运行检查脚本后，把输出发给我，我帮你：
1. 确认实际维度
2. 判断应该使用哪个配置
3. 如果需要，帮你创建新配置文件

---

**快速开始**: 
```bash
python scripts/diagnostics/check_mmk2_action_dimensions.py "/mnt/nas/synnas/docker/6discover_robotics_aitbot_mmk2/storage_peaches_and_pears/the left hand throws the peach into the left compartment, the right hand throws the pear into the right compartment./0"
```

把输出贴给我！📊

