# 银河(Yinhe)验证器修复说明

## 修复日期
2025年10月20日

## 发现的问题

### 1. ❌ 任务发现不完整
**问题**: 只发现了3个任务（fold_clothe, steamer_storage_baozi, take_snack），遗漏了2个

**实际情况**:
- ✅ fold_clothe: 3,978 episodes (简单结构)
- ✅ steamer_storage_baozi: 10,527 episodes (复杂结构)
- ✅ take_snack: 5,786 episodes (复杂结构)
- ❌ use_dryer: 1,628 episodes (复杂结构) - **之前遗漏**
- ❌ use_washing_machine: 3,794 episodes (复杂结构) - **之前遗漏**

**总计**: 25,713 episodes (之前只发现了19,982个，遗漏了5,731个)

**根本原因**: 
- `discover_datasets()` 只遍历一级子目录
- `use_dryer` 目录为空（无robot_id子目录）
- 需要硬编码所有已知任务确保完整性

### 2. ❌ Episode发现不完整
**问题**: `find_episodes_fast()` 只支持简单结构，不支持复杂结构

**数据集结构有两种**:

**简单结构** (1个任务):
```
task/
  ├── device_model_annotation.yaml
  └── robot_id/
      └── episode/
          └── data.json  ← Episode特征文件
```
例如: `fold_clothe/dieyifu-11/20250915_101229_record0/data.json`

**复杂结构** (4个任务):
```
task/
  ├── device_model_annotation.yaml
  └── subtask/
      └── robot_id/
          └── episode/
              └── data.json  ← Episode特征文件
```
例如: `use_washing_machine/clothes_into_washing_machine/xiyiji-11/20250915_101229_record0/data.json`

**复杂结构任务列表**:
- `steamer_storage_baozi`: 有多个subtask (zhengbaozi-3, zhengbaozi-34, zhengbaozi-46等)
- `take_snack`: 有多个subtask (bianlifeng-22, bianlifeng-32等)
- `use_dryer`: subtasks = [take_out_the_clothes, open_the_dryer]
- `use_washing_machine`: subtasks = [clothes_output_washing_machine, clothes_into_washing_machine]

### 3. ⚠️ 100%正确率不合理
**问题**: 早上验证显示100%正确，但正式转换时有很多报错

**可能原因**:
1. 验证规则不够严格（只检查文件存在性，不检查内容）
2. 遗漏了某些必要的字段验证
3. 配置文件加载失败，使用了过于宽松的默认配置

**建议增强**:
- [ ] 检查JSON字段的数据类型和长度
- [ ] 检查视频文件是否可读（至少检查文件大小）
- [ ] 检查必要字段的数组长度是否一致
- [ ] 添加更详细的错误日志

## 修复内容

### 修复1: 硬编码所有已知任务
```python
KNOWN_TASKS = [
    "fold_clothe",
    "steamer_storage_baozi",
    "take_snack",
    "use_dryer",
    "use_washing_machine"
]
```

**优点**:
- 确保不会遗漏任何任务
- 可以检测新增的未知任务
- 可以报告缺失的任务

### 修复2: 支持复杂结构的Episode发现
```python
def _search_episodes(search_dir: Path, depth: int = 0, max_depth: int = 3):
    """递归搜索episodes，限制深度避免过深"""
    # 检查是否是episode目录（包含data.json）
    if (item / "data.json").exists():
        episodes.append(item)
    else:
        # 继续往下搜索
        _search_episodes(item, depth + 1, max_depth)
```

**优点**:
- 支持任意深度的目录结构
- 自动适应简单和复杂结构
- 限制最大深度避免无限递归

## 验证结果对比

### 修复前 (早上的结果)
```
总Episodes: 19,982
✅ 有效: 19,982 (100.0%)
❌ 无效: 0 (0.0%)

按任务统计:
  fold_clothe: 3,978/3,978 (100.0%)
  steamer_storage_baozi: 10,249/10,249 (100.0%)
  take_snack: 5,755/5,755 (100.0%)
```

**问题**:
- 只发现3个任务
- 遗漏5,731个episodes
- 100%正确率不合理

### 修复后 (预期)
```
总Episodes: 25,713
✅ 有效: ？？？
❌ 无效: ？？？

按任务统计:
  fold_clothe: 3,978 episodes
  steamer_storage_baozi: 10,527 episodes  (+278)
  take_snack: 5,786 episodes  (+31)
  use_dryer: 1,628 episodes  (新增)
  use_washing_machine: 3,794 episodes  (新增)
```

## 使用建议

### 1. 重新运行完整验证
```bash
python3 scripts/dataset_statistics/yinhe_preconversion_validator_v2.py \
  --dataset-path /mnt/nas/synnas/docker/外部数据/银河通用 \
  --workers 8
```

**预期结果**:
- 发现所有5个任务
- 发现所有25,713个episodes
- 获得真实的错误率（不应该是100%）

### 2. 检查配置问题报告
```bash
cat /mnt/nas/synnas/docker/外部数据/银河通用/validation_config_issues.txt
```

如果有配置问题（错误率≥90%），优先修正配置

### 3. 移动错误数据（可选）
```bash
# 只有在确认错误率<10%时才移动
python3 scripts/dataset_statistics/yinhe_preconversion_validator_v2.py \
  --dataset-path /mnt/nas/synnas/docker/外部数据/银河通用 \
  --workers 8 \
  --move-errors
```

## 数据集详情

| 任务名称 | Episodes | Robot IDs | 结构类型 | Subtasks |
|---------|---------|-----------|---------|----------|
| fold_clothe | 3,978 | 28 | 简单 | - |
| steamer_storage_baozi | 10,527 | 51 | **复杂** | zhengbaozi-* |
| take_snack | 5,786 | 37 | **复杂** | bianlifeng-* |
| use_dryer | 1,628 | 7 | **复杂** | take_out_the_clothes, open_the_dryer |
| use_washing_machine | 3,794 | 19 | **复杂** | clothes_output_washing_machine, clothes_into_washing_machine |
| **总计** | **25,713** | **142** | - | - |

## 需要进一步调查

1. **为什么早上报告100%正确**?
   - 检查是否使用了默认配置（配置文件加载失败）
   - 检查是否validation规则过于宽松
   - 对比正式转换时的错误日志

2. **正式转换时的错误类型**?
   - JSON字段缺失？
   - 视频文件损坏？
   - 数据格式不匹配？

3. **是否需要更严格的验证**?
   - 检查JSON数组长度一致性
   - 检查视频文件可读性
   - 验证数据的数值范围

## 下一步

1. ✅ 运行修复后的验证器
2. 📊 对比新旧结果，找出差异
3. 🔍 分析真实的错误类型
4. 📝 根据转换错误补充验证规则
5. 🧹 清理错误数据或修正配置
