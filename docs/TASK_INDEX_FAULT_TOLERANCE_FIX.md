# 修复：task_index超出范围容错

**日期**: 2025-10-27  
**问题**: `IndexError: list index out of range` when task_index is invalid  
**影响**: 所有使用 local_task_info.yaml 的 converters

---

## 🐛 问题描述

### 错误信息
```python
File "lerobot_format_converter.py", line 407, in _get_dataset_task_paths
    task = self.tasks[task_index]
IndexError: list index out of range

ValueError: Found task index error from 
/mnt/nas/.../水果分类517mm-绿白/local_task_info.yaml
```

### 根本原因

**数据质量问题**：`local_task_info.yaml` 中的 `task_index` 超出了配置文件中 `tasks` 列表的范围。

**示例场景**：
```yaml
# local_task_info.yaml
task_index: 5

# 但 converter config 中只有 3 个 tasks：
tasks:
  - task_0
  - task_1
  - task_2

# self.tasks[5] → IndexError!
```

**原因**：
1. 数据集的 `local_task_info.yaml` 文件有错误
2. Converter config 中的 tasks 列表不完整
3. 数据和配置版本不匹配

**影响**：
- 一个错误的 task_index 导致**整个数据集转换失败**
- 无法跳过有问题的任务继续处理其他任务

---

## ✅ 修复方案

### 添加容错机制

**修改文件**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py`

**修改位置**: `_get_dataset_task_paths()` 方法

**修改前**：
```python
for file in files:
    try:
        with file.open("r") as f:
            task_info_dict = yaml.safe_load(f)
            task_index = task_info_dict[TASK_INDEX_KEY]
            task = self.tasks[task_index]  # ❌ 直接访问，可能越界
            task_paths_dict[file.parent] = task
            has_task_file = True
    except Exception as e:
        raise ValueError(f"Found task index error from {file}") from e
```

**修改后**：
```python
for file in files:
    try:
        with file.open("r") as f:
            task_info_dict = yaml.safe_load(f)
            task_index = task_info_dict[TASK_INDEX_KEY]
            
            # 🆕 容错：检查task_index是否在有效范围内
            if task_index < 0 or task_index >= len(self.tasks):
                if self.logger:
                    self.logger.warning(
                        f"⚠️  Skipping task with invalid task_index.\n"
                        f"   📁 File: {file}\n"
                        f"   📊 task_index: {task_index}\n"
                        f"   📊 Valid range: 0-{len(self.tasks)-1}\n"
                        f"   💡 This task will be skipped. Check if:\n"
                        f"      1. local_task_info.yaml has incorrect task_index\n"
                        f"      2. Converter config has incomplete tasks list"
                    )
                continue  # ✅ 跳过这个任务，继续处理其他任务
            
            task = self.tasks[task_index]
            task_paths_dict[file.parent] = task
            has_task_file = True
    except KeyError as e:
        # YAML文件缺少必需字段
        if self.logger:
            self.logger.warning(
                f"⚠️  Skipping task with missing key: {e}\n"
                f"   📁 File: {file}\n"
                f"   💡 This task will be skipped."
            )
        continue
    except Exception as e:
        # 其他错误仍然抛出
        raise ValueError(f"Found task index error from {file}") from e
```

---

## 📊 修复效果对比

### 修复前
```
场景: 数据集有10个任务，第5个任务的task_index超出范围

结果: 
❌ 整个数据集转换失败
❌ 前4个正常任务也无法转换
❌ 后5个正常任务也无法转换
❌ 转换状态: FAILED
```

### 修复后
```
场景: 数据集有10个任务，第5个任务的task_index超出范围

结果:
✅ 前4个正常任务成功转换
⚠️  第5个任务被跳过（记录警告日志）
✅ 后5个正常任务成功转换
✅ 转换状态: COMPLETED (9/10 任务)
```

---

## 🔍 如何识别问题任务

### 在日志中查找

转换时会看到警告日志：

```
⚠️  Skipping task with invalid task_index.
   📁 File: /path/to/task/local_task_info.yaml
   📊 task_index: 5
   📊 Valid range: 0-2
   💡 This task will be skipped. Check if:
      1. local_task_info.yaml has incorrect task_index
      2. Converter config has incomplete tasks list
```

### 检查特定文件

```bash
# 查看有问题的 YAML 文件
cat /mnt/nas/.../水果分类517mm-绿白/local_task_info.yaml

# 检查 task_index 值
grep task_index /mnt/nas/.../水果分类517mm-绿白/local_task_info.yaml
```

---

## 🛠️ 修复数据问题

如果想修复数据（可选，不影响转换）：

### 方法1: 修正 local_task_info.yaml

```yaml
# 修改前
task_index: 5

# 修改后（根据实际任务）
task_index: 2  # 确保在有效范围内
```

### 方法2: 更新 converter config

```yaml
# 在 converter config 中添加缺失的 tasks
tasks:
  - task_0
  - task_1
  - task_2
  - task_3  # 新增
  - task_4  # 新增
  - task_5  # 新增
```

---

## 🚀 部署

**立即生效**：
1. 同步代码到所有Client机器
2. 重启Clients

```bash
# 在每台Client机器上
cd ~/robocoin-dataset
git pull origin feat/test

# 重启clients
Ctrl+C
python scripts/format_converters/tolerobot/multi_client.py \
    --host 172.16.13.140 --port 8769 --num-clients 4
```

---

## ✅ 验证

修复后，遇到invalid task_index时：
- ✅ 记录警告日志
- ✅ 跳过问题任务
- ✅ 继续处理其他任务
- ✅ 转换不会失败

---

## 📚 影响范围

所有使用 `_get_dataset_task_paths()` 的 converters：
- ✅ LerobotFormatConverter (基类)
- ✅ JPG+JSON converter
- ✅ MP4+JSON converter
- ✅ 其他所有子类（自动继承）

---

**修复状态**: ✅ 已完成  
**下一步**: 同步代码到Client机器并重启

