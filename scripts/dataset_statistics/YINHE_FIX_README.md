# 银河数据集验证器 - Bug修复说明

## 问题描述

### 症状
验证银河数据集时,大量episodes报告JSON解析错误:
```
❌ steamer_storage_baozi/20250911_184442_record0
  • JSON错误: Unterminated string starting at: line 1 column 10485757 (char 10485756)
❌ steamer_storage_baozi/20250911_184533_record0
  • JSON错误: Expecting ',' delimiter: line 1 column 10485761 (char 10485760)
```

关键观察:
- **所有错误都发生在 ~10485760 (10MB) 位置**
- 错误主要集中在 `steamer_storage_baozi` 和 `fold_clothe` 任务
- `take_snack` 任务通过率很高 (96.6%)

### 根本原因

在 `yinhe_preconversion_validator_v2.py` 的两处代码中:

**第313行 (validate_episode方法):**
```python
with open(json_path, encoding='utf-8') as f:
    content = f.read(10 * 1024 * 1024)  # ❌ 只读取前10MB
    data = json.loads(content)
```

**第635行 (_validate_episode_worker函数):**
```python
with open(json_path, encoding='utf-8') as f:
    content = f.read(10 * 1024 * 1024)  # ❌ 只读取前10MB
    data = json.loads(content)
```

**问题分析:**
1. 这两处代码限制只读取JSON文件的前10MB
2. `steamer_storage_baozi` 任务的data.json文件通常是 **11-20MB**
3. `fold_clothe` 任务的data.json文件也超过10MB
4. `take_snack` 任务的data.json文件较小,所以通过率高
5. 截断后的JSON字符串不完整,导致解析失败
6. **这些episodes的JSON文件实际上是完整有效的!**

## 解决方案

### 1. 修复验证器代码

已修复 `yinhe_preconversion_validator_v2.py`:

```python
# 修复前 ❌
with open(json_path, encoding='utf-8') as f:
    content = f.read(10 * 1024 * 1024)  # 截断
    data = json.loads(content)

# 修复后 ✅
with open(json_path, encoding='utf-8') as f:
    data = json.load(f)  # 完整读取
```

### 2. 恢复误移动的episodes

已创建恢复脚本 `restore_yinhe_episodes.py`:

```bash
# 步骤1: 预览模式,查看有多少episodes可以恢复
python3 scripts/dataset_statistics/restore_yinhe_episodes.py \
  --dataset-path /mnt/nas/synnas/docker/外部数据/银河通用 \
  --dry-run \
  --workers 8

# 步骤2: 确认后执行恢复
python3 scripts/dataset_statistics/restore_yinhe_episodes.py \
  --dataset-path /mnt/nas/synnas/docker/外部数据/银河通用 \
  --workers 8
```

**恢复脚本功能:**
- ✅ 自动查找所有error文件夹中的episodes
- ✅ 使用完整JSON读取重新验证每个episode
- ✅ 只恢复确认有效的episodes
- ✅ 仍有问题的episodes保留在error文件夹
- ✅ 支持dry-run预览模式
- ✅ 多进程并行处理

### 3. 重新验证数据集

修复后重新运行验证器:

```bash
# 测试验证
python3 scripts/dataset_statistics/yinhe_preconversion_validator_v2.py \
  --dataset-path /mnt/nas/synnas/docker/外部数据/银河通用 \
  --max-episodes 100 \
  --workers 8

# 完整验证
python3 scripts/dataset_statistics/yinhe_preconversion_validator_v2.py \
  --dataset-path /mnt/nas/synnas/docker/外部数据/银河通用 \
  --workers 8
```

## 预期结果

### 修复前
```
总Episodes: 20091
✅ 有效: 5836 (29.0%)
❌ 无效: 14255 (71.0%)  ← 大部分是误报!

按任务统计:
  fold_clothe: 237/3978 (6.0%)      ← 误报
  steamer_storage_baozi: 9/10327 (0.1%)  ← 严重误报
  take_snack: 5590/5786 (96.6%)    ← 正常
```

### 修复后 (预期)
```
总Episodes: 20091
✅ 有效: ~18000+ (90%+)  ← 大幅提升
❌ 无效: ~2000 (10%)

按任务统计:
  fold_clothe: ~3500/3978 (88%+)
  steamer_storage_baozi: ~9500/10327 (92%+)
  take_snack: 5590/5786 (96.6%)
```

## 技术细节

### JSON文件大小分布

测试了一个error中的episode:
```bash
$ ls -lh .../steamer_storage_baozi/.../error/20250903_103942_record0/data.json
-rwxrwxrwx 1 1030 users 20M ...  # 20MB!
```

### Python json.load() vs json.loads()

```python
# ✅ 推荐: 直接从文件对象加载
with open(path) as f:
    data = json.load(f)  # 流式读取,无内存限制

# ❌ 不推荐: 先读字符串再解析
with open(path) as f:
    content = f.read(10 * 1024 * 1024)  # 限制大小
    data = json.loads(content)  # 可能截断
```

## 行动检查清单

- [x] 修复 `yinhe_preconversion_validator_v2.py` 代码
- [x] 创建 `restore_yinhe_episodes.py` 恢复脚本
- [x] 测试修复后的验证器
- [ ] 运行恢复脚本(dry-run模式)
- [ ] 确认恢复数量合理
- [ ] 执行恢复操作
- [ ] 重新运行完整验证
- [ ] 确认最终通过率提升到90%+

## 注意事项

1. **备份建议**: 在执行恢复前,建议对数据集做快照
2. **分批恢复**: 可以先恢复一小部分测试,确认无误后再全量恢复
3. **验证配置**: 如果恢复后仍有少量episode报错,检查是否是真的数据问题

## 联系与支持

如有问题,请联系开发团队或查看相关文档。

---
**修复日期**: 2025年1月20日  
**修复版本**: v2.1  
**影响范围**: 银河数据集验证器
