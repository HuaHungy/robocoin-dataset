# 🔧 修复所有Converter的目录搜索深度限制

## 📝 问题背景

用户报告：生产环境的数据目录结构比测试数据复杂得多，episode可能嵌套在多层子目录中。

### 测试数据 vs 生产数据

**测试数据（简单扁平）**:
```
data/discover_robotics_aitbot_mmk2:third_view/
└── episode_24/              ← 第1层
    ├── camera_head/
    └── ...
```

**生产数据（深层嵌套）**:
```
mobile_goods/mobile_calculator_box/              ← task_path
├── mobile_calculator_box_1/                     ← 子任务（第1层）
│   ├── episode_0/                               ← episode在第2层！
│   ├── episode_1/
│   └── ...
├── mobile_calculator_box_2/                     ← 另一个子任务
│   ├── episode_0/
│   └── ...
└── local_task_info.yaml
```

**问题**: 之前的代码只针对测试数据写，武断地设定深度限制（如3层、5层、10层），导致生产环境转换失败。

---

## ✅ 修复的Converters

### 1. MMK2 Converter (`lerobot_format_converter_mmk2.py`)

**修复前**: `max_depth=3` 硬编码限制

**修复后**:
- `max_depth=100` （实际无限制）
- 添加 `visited` set 防止符号链接循环
- 新增 `_find_all_episodes()` 统一搜索方法
- BFS递归搜索，支持任意深度

**关键代码**:
```python
def _find_all_episodes(self, task_path: Path) -> list[Path]:
    """递归查找所有episode目录（BFS，无深度限制）"""
    queue = deque([(task_path, 0)])
    max_depth = 100  # 防止无限循环
    visited = set()  # 防止重复访问
    
    while queue:
        current_path, depth = queue.popleft()
        
        # 防止符号链接循环
        real_path = current_path.resolve()
        if real_path in visited:
            continue
        visited.add(real_path)
        
        # 搜索逻辑...
```

---

### 2. H5+JPG Converter (`lerobot_format_converter_h5_jpg.py`)

**修复前**: `max_depth=5` 硬编码限制

**修复后**: `max_depth=100`

**修改位置**:
```python
def find_episode_dirs(path: Path, max_depth: int = 100, current_depth: int = 0):
    """递归查找episode目录（无深度限制，使用visited避免循环）"""
```

---

### 3. MP4+JSON Converter (`lerobot_format_converter_mp4_json.py`)

**修复前**: `max_depth=10` 硬编码限制

**修复后**: `max_depth=100`

**修改位置**:
```python
episodes = self._episode_locator.locate_episodes_bfs(
    dataset_path=task_path,
    is_episode_func=self._is_episode,
    max_depth=100  # 实际上无深度限制，防止无限循环
)
```

**更新错误消息**:
```
🔍 Searched recursively (unlimited depth) using BFS.
```

---

### 4. H5+MP4 Converter (`lerobot_format_converter_h5_mp4.py`)

**修复前**: 复杂的三步搜索（glob → iterdir+glob → glob("**/*")）

**修复后**: 直接使用 `rglob()` 递归搜索

#### 修改位置1: `_prevalidate_files()`
```python
# 🔥 简化搜索逻辑：直接递归搜索所有H5文件（无深度限制）
h5_files_all = []
h5_files_all.extend(task_path.rglob("*.hdf5"))
h5_files_all.extend(task_path.rglob("*.h5"))
# 过滤隐藏和特殊目录
h5_files_all = [f for f in h5_files_all if not any(part.startswith('.') or part.startswith('@') for part in f.parts)]
```

#### 修改位置2: `_get_all_episode_h5_files()`
```python
def _get_all_episode_h5_files(self, task_path: Path) -> list[Path]:
    """获取所有episode的H5文件路径（递归搜索，无深度限制）"""
    # 🔥 简化策略：直接递归搜索（rglob无深度限制）
    h5_files = []
    h5_files.extend(task_path.rglob("*.hdf5"))
    h5_files.extend(task_path.rglob("*.h5"))
    # 过滤隐藏和特殊目录
    h5_files = [f for f in h5_files if not any(part.startswith('.') or part.startswith('@') for part in f.parts)]
```

---

### 5. H5 Converter (`lerobot_format_converter_h5.py`)

**状态**: ✅ **无需修改**

**原因**: 已经使用 `rglob()` 递归搜索，无深度限制。

---

### 6. MCAP Converter (`lerobot_format_converter_mcap.py`)

**状态**: ✅ **无需修改**

**原因**: 已经使用 `rglob()` 递归搜索，无深度限制。

---

### 7. Leju Waibu Converter (`lerobot_format_converter_leju_waibu.py`)

**修复前**: 只搜索2层 (iterdir → iterdir)

**修复后**: BFS递归搜索 + max_depth=100 + visited防循环

**修改位置**:
```python
# _get_dataset_task_paths() 中的episode搜索逻辑
# 从：
for episode_dir in subtask_dir.iterdir():  # 只搜索1层
    # ...

# 改为：
from collections import deque
queue = deque([(subtask_dir, 0)])
max_depth = 100
visited = set()

while queue:
    current_dir, depth = queue.popleft()
    # BFS递归搜索，支持任意深度
```

---

### 8. JPG+JSON Converter (`lerobot_format_converter_jpg_json.py`)

**修复前**: `max_depth=10` 硬编码限制

**修复后**: `max_depth=100`

**修改位置**:
```python
episodes = self._episode_locator.locate_episodes_bfs(
    dataset_path=task_path,
    is_episode_func=self._is_episode,
    max_depth=100,  # 实际无深度限制，防止无限循环
)
```

---

### 9. Rosbag Converter (`lerobot_format_converter_rosbag.py`)

**状态**: ✅ **无需修改**

**原因**: 已经使用 `rglob()` 递归搜索，无深度限制。

```python
rosbag_files = list(path.rglob("*.bag"))  # 递归搜索，无限制
```

---

## 📊 修复总结

| Converter | 修复前 | 修复后 | 状态 |
|-----------|--------|--------|------|
| H5 | ✅ rglob (无限制) | - | 无需修改 |
| H5+MP4 | ⚠️ 复杂的三步搜索 | ✅ rglob (无限制) | **已修复** |
| H5+JPG | ❌ max_depth=5 | ✅ max_depth=100 | **已修复** |
| MP4+JSON | ⚠️ max_depth=10 | ✅ max_depth=100 | **已修复** |
| MCAP | ✅ rglob (无限制) | - | 无需修改 |
| MMK2 | ❌ 只搜索1层 | ✅ BFS+max_depth=100 | **已修复** |
| Leju Waibu | ❌ 只搜索2层 | ✅ BFS+max_depth=100 | **已修复** |
| JPG+JSON | ⚠️ max_depth=10 | ✅ max_depth=100 | **已修复** |
| Rosbag | ✅ rglob (无限制) | - | 无需修改 |

---

## 🔑 核心原则

### ❌ 错误做法
- 武断设定深度限制（3层、5层、10层）
- 只针对测试数据写代码
- 假设数据结构简单

### ✅ 正确做法
- **使用 `rglob()` 或 BFS 递归搜索**
- **只设置防止无限循环的保护性限制（如100层）**
- **使用 `visited` set 防止符号链接循环**
- **过滤隐藏和特殊目录（`.`, `@` 开头）**
- **支持任意深度的目录结构**

---

## 🚀 性能考虑

**Q**: 递归搜索会不会很慢？

**A**: 不会。原因：
1. **现代文件系统递归搜索已经足够快**
2. **使用了缓存机制**（`_h5_files_cache` 等）
3. **过滤隐藏目录减少搜索范围**
4. **绝大多数情况下，数据不会真的嵌套100层**

**Q**: 为什么不用多步策略（先1层，再2层，最后递归）？

**A**: 
1. **代码复杂，容易出错**
2. **维护成本高**
3. **性能提升微乎其微**
4. **不够健壮，容易遗漏深层数据**

---

## 🛡️ 安全机制

所有converters都包含以下安全机制：

1. **防止无限循环**: `max_depth=100`
2. **防止符号链接循环**: `visited` set（MMK2）
3. **过滤特殊目录**: 跳过 `.` 和 `@` 开头的目录
4. **错误处理**: `try-except` 捕获权限错误等异常

---

## 📋 测试建议

### 测试用例
1. **扁平结构**: `task_path/episode_X/`
2. **1层嵌套**: `task_path/sub/episode_X/`
3. **2层嵌套**: `task_path/sub1/sub2/episode_X/`
4. **深层嵌套**: `task_path/a/b/c/d/e/episode_X/`
5. **混合结构**: 同一个task_path下有不同深度的episode

### 测试命令
```bash
# 测试MMK2 converter
python scripts/format_converters/tolerobot/client.py \
    --dataset-path /path/to/nested/structure \
    --device-model discover_robotics_aitbot_mmk2

# 测试H5+MP4 converter
python scripts/format_converters/tolerobot/client.py \
    --dataset-path /path/to/nested/structure \
    --device-model agilex_cobot_decoupled_magic
```

---

## 🔄 同步到生产环境

**步骤**:
1. 停止所有运行中的clients
2. 同步代码到所有机器:
   ```bash
   cd ~/robocoin-dataset
   git pull origin feat/test
   ```
3. 重启clients

**修改的文件**:
- `lerobot_format_converter_mmk2.py`
- `lerobot_format_converter_h5_jpg.py`
- `lerobot_format_converter_mp4_json.py`
- `lerobot_format_converter_h5_mp4.py`
- `lerobot_format_converter_leju_waibu.py` 🆕
- `lerobot_format_converter_jpg_json.py` 🆕
- `lerobot_format_converter.py` (异常导入 + 资源清理) 🆕
- `client.py` (资源清理) 🆕

**其他修复**:
- Semaphore资源泄漏修复（详见 `SEMAPHORE_LEAK_FIX.md`）
- 数据库字段缺失修复（详见 `DATABASE_FIELD_MISSING_FIX.md`）

**数据库修复脚本**:
- `fix_null_device_model.sql` - 修复旧数据中的 NULL 字段

---

## 🙏 教训

1. **不要武断设定限制**
   - 任何"最多N层"的假设都可能被打破
   
2. **不要只针对测试数据写代码**
   - 测试数据往往比生产数据简单
   
3. **设计时考虑最坏情况**
   - 支持任意深度的嵌套
   - 防止无限循环和符号链接循环
   
4. **保持代码简单**
   - 直接用rglob，不要过度优化

---

**修复日期**: 2025-10-25  
**修复人**: AI Assistant (Claude Sonnet 4.5)
