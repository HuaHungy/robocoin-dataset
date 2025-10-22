# 字段命名验证器使用指南

**工具**: `scripts/config_validation/field_naming_validator.py`  
**目的**: 自动检查配置文件中的字段命名是否符合规范

---

## 📋 验证规则

### 1. 关节编号规则
**✅ 正确**: 关节编号从1开始
```yaml
- left_arm_joint_1_rad
- left_arm_joint_2_rad
- left_arm_joint_3_rad
```

**❌ 错误**: 关节编号从0开始
```yaml
- left_arm_joint_0_rad  # ❌ 应该从1开始
- left_arm_joint_1_rad
- left_arm_joint_2_rad
```

### 2. 单位后缀规则

#### 关节角度
- ✅ `_rad` (弧度)
- ✅ `_deg` (角度)

#### 速度
- ✅ `_rad_s` (弧度/秒)
- ✅ `_deg_s` (角度/秒)
- ✅ `_m_s` (米/秒)

#### 力/力矩
- ✅ `_nm` (牛顿·米)
- ✅ `_n` (牛顿)

#### 位置/距离
- ✅ `_m` (米)
- ✅ `_mm` (毫米)

### 3. 字段数量验证
字段数量必须与`range_to - range_from`匹配：

```yaml
- names:
    - left_arm_joint_1_rad
    - left_arm_joint_2_rad
    - left_arm_joint_3_rad
    - left_arm_joint_4_rad
    - left_arm_joint_5_rad
    - left_arm_joint_6_rad
    - left_arm_joint_7_rad
  args:
    range_from: 0
    range_to: 7  # ✅ 7-0 = 7个字段，正确
```

---

## 🔧 使用方法

### 基本用法
```bash
python scripts/config_validation/field_naming_validator.py <配置文件路径>
```

### 示例
```bash
# 验证yinhe配置
python scripts/config_validation/field_naming_validator.py \
    scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml

# 验证realman配置
python scripts/config_validation/field_naming_validator.py \
    scripts/format_converters/tolerobot/configs/converter_config_realman_rmc_aidal_mcap.yaml

# 验证leju配置
python scripts/config_validation/field_naming_validator.py \
    scripts/format_converters/tolerobot/configs/converter_config_leju_waibu.yaml
```

---

## 📊 输出示例

### 通过验证
```
================================================================================
📋 字段命名验证报告
================================================================================
配置文件: converter_config_yinhe.yaml

✅ 未发现关键错误

✅ 未发现警告

================================================================================
✅ 字段命名检查通过！
================================================================================
```

### 发现错误
```
================================================================================
📋 字段命名验证报告
================================================================================
配置文件: converter_config_example.yaml

❌ 发现 2 个错误:

❌ [observation.state] 字段 'left_arm_joint_0_rad': 关节编号从0开始（应该从1开始）
   建议: left_arm_joint_1_rad

❌ [observation.state] sub_state[2]: 字段数量不匹配
   期望: 7 (range_from=0, range_to=7)
   实际: 6
   字段: ['left_arm_joint_1_rad', 'left_arm_joint_2_rad', 'left_arm_joint_3_rad']...

⚠️  发现 1 个警告:

⚠️  [observation.state] 字段 'body_joint_1': 缺少单位后缀
   建议添加: _rad, _deg, _m 等

================================================================================
❌ 字段命名存在错误，需要修正
================================================================================
```

---

## 🔍 检查项目

### 1. 关节编号检查
- ✅ 检测从0开始的关节编号
- ✅ 提供修正建议

### 2. 单位后缀检查
- ✅ 检测缺少单位后缀的字段
- ✅ 检测不规范的单位后缀
- ✅ 提供建议的单位后缀

### 3. 字段数量检查
- ✅ 验证字段数量与range配置是否匹配
- ✅ 显示期望和实际的数量

---

## 📝 集成到工作流程

### 推荐流程
1. **编写配置文件**
2. **运行字段命名验证器** ⬅️ **新增步骤**
3. 修正发现的错误
4. 运行深度数值分析
5. 运行配置检测器
6. 实际转换测试

### 示例工作流
```bash
# 1. 编写配置后立即验证
vim converter_config_xxx.yaml
python scripts/config_validation/field_naming_validator.py converter_config_xxx.yaml

# 2. 如果发现错误，修正后再次验证
vim converter_config_xxx.yaml
python scripts/config_validation/field_naming_validator.py converter_config_xxx.yaml

# 3. 通过验证后继续其他步骤
python scripts/analyze_xxx_numerical.py
```

---

## 💡 常见错误和修正

### 错误1: 关节从0开始
**错误配置**:
```yaml
- names:
    - left_arm_joint_0_rad
    - left_arm_joint_1_rad
    - left_arm_joint_2_rad
```

**修正**:
```yaml
- names:
    - left_arm_joint_1_rad
    - left_arm_joint_2_rad
    - left_arm_joint_3_rad
```

### 错误2: 缺少单位后缀
**错误配置**:
```yaml
- names:
    - left_arm_joint_1
    - left_arm_joint_2
```

**修正**:
```yaml
- names:
    - left_arm_joint_1_rad
    - left_arm_joint_2_rad
```

### 错误3: 字段数量不匹配
**错误配置**:
```yaml
- names:
    - left_arm_joint_1_rad
    - left_arm_joint_2_rad
    - left_arm_joint_3_rad
  args:
    range_from: 0
    range_to: 7  # ❌ 期望7个字段，实际只有3个
```

**修正**:
```yaml
- names:
    - left_arm_joint_1_rad
    - left_arm_joint_2_rad
    - left_arm_joint_3_rad
    - left_arm_joint_4_rad
    - left_arm_joint_5_rad
    - left_arm_joint_6_rad
    - left_arm_joint_7_rad
  args:
    range_from: 0
    range_to: 7  # ✅ 7个字段
```

---

## 🎯 最佳实践

### 1. 每次修改配置后都运行验证
```bash
# 创建alias便于使用
alias validate-config='python scripts/config_validation/field_naming_validator.py'

# 使用
validate-config converter_config_yinhe.yaml
```

### 2. 在CI/CD中集成
```yaml
# 示例：在GitHub Actions中
- name: Validate field naming
  run: |
    python scripts/config_validation/field_naming_validator.py \
      scripts/format_converters/tolerobot/configs/*.yaml
```

### 3. 结合其他验证工具
```bash
# 完整验证流程
python scripts/config_validation/field_naming_validator.py config.yaml
python scripts/analyze_xxx_numerical.py
python scripts/config_validation/batch_validation.py
```

---

## 🔧 扩展验证器

如果需要添加新的验证规则，编辑`field_naming_validator.py`：

```python
# 添加新的单位后缀
REQUIRED_SUFFIXES = {
    'joint': ['_rad', '_deg'],
    'vel': ['_rad_s', '_deg_s', '_m_s'],
    'custom': ['_custom_unit'],  # 添加自定义单位
}

# 添加新的验证逻辑
def _validate_custom_rule(self, field_name: str):
    # 自定义验证逻辑
    pass
```

---

## 📚 相关文档

- `CONFIG_VALIDATOR_ENHANCEMENT.md` - 配置验证工具增强
- `CONFIG_VALIDATOR_LOGIC.md` - 配置验证逻辑说明
- `YINHE_CONFIG_FIX_COMPLETE.md` - Yinhe配置修正示例

---

**工具版本**: 1.0  
**最后更新**: 2025-10-22  
**维护者**: robocoin-dataset团队

---

✅ **使用字段命名验证器，避免常见的配置错误！**

