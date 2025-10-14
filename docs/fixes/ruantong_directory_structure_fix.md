# 软通天擎数据集目录结构问题修复

## 问题描述

转换软通天擎（ruantong）数据集时出现错误：

```
FileNotFoundError: ❌ No episode directories found.
   📁 Task path: /mnt/nas/synnas/docker2/外部数据/软通天擎/jx01/zy/111_主机上料工序-IO挡板上料场景2/503
   📂 Directories found: ['A2D0015AC00557', '@eaDir']
   🗂️  Expected: Directories containing 'aligned_joints.h5' file
```

## 根本原因

**目录结构比预期更深**：

- **实际结构**：`task/batch/episode/aligned_joints.h5` (3层)
  ```
  503/                           ← task_path
    ├── @eaDir/                  ← 系统目录（需跳过）
    └── A2D0015AC00557/          ← 批次/设备目录
        ├── 182088/              ← Episode目录
        │   ├── aligned_joints.h5
        │   ├── camera/
        │   └── meta_info.json
        └── 182090/              ← Episode目录
            └── ...
  ```

- **原代码问题**：`_prevalidate_files()` 只检查 **1-2层深度**
  ```python
  # 只检查直接子目录
  episodes = [item for item in task_path.glob("*") 
              if item.is_dir() and (item / "aligned_joints.h5").exists()]
  
  # 只检查二级子目录
  if not episodes:
      episodes = [item for item in task_path.glob("*/*") 
                  if item.is_dir() and (item / "aligned_joints.h5").exists()]
  ```

- **结果**：找不到 episode 目录（实际在 `503/A2D0015AC00557/182088/`）

## 修复方案

### 1. 简化 `_prevalidate_files()`

**修改前**：自己实现1-2层搜索

**修改后**：使用已有的递归方法 `_get_all_episode_dirs()`

```python
def _prevalidate_files(self) -> None:
    """验证数据集文件完整性
    
    使用 _get_all_episode_dirs() 进行递归搜索，支持任意深度的嵌套结构（最多5层）
    """
    for task_path in self.path_task_dict.keys():
        # 使用现有的递归搜索方法查找所有 episode 目录
        try:
            episodes = self._get_all_episode_dirs(task_path)
        except FileNotFoundError:
            # _get_all_episode_dirs() 已经会抛出详细的错误信息
            raise
        
        # ... 验证每个 episode 的文件完整性
```

**优势**：
- ✅ 复用已有的递归搜索逻辑（**最多支持5层**）
- ✅ 自动跳过系统目录（`.` 和 `@` 开头）
- ✅ 代码简洁，避免重复

### 2. 改进错误诊断信息

**修改前**：只显示目录名列表
```
📂 Directories found: ['A2D0015AC00557', '@eaDir']
```

**修改后**：显示3层目录树结构
```python
def collect_dir_structure(path: Path, max_depth: int = 3, current_depth: int = 0, prefix: str = "") -> list[str]:
    """收集目录结构用于诊断"""
    # ... 递归构建树状结构
    structure.append(f"{indent}{prefix}{item.name}/")
```

**错误信息示例**：
```
❌ No episode directories found.
   📁 Task path: /path/to/task
   🔍 Searched up to 5 levels deep
   📂 Directory structure (first 3 levels):
   503/
     @eaDir/ [Skipped]
     A2D0015AC00557/
       182088/ [Contains aligned_joints.h5]
       182090/ [Contains aligned_joints.h5]
   🗂️  Expected: Directories containing 'aligned_joints.h5' file
   💡 Check if:
      1. Episode directories exist under task path
      2. Each episode directory contains 'aligned_joints.h5' file
      3. File permissions are correct
      4. Directory names don't start with '.' or '@' (these are skipped)
```

## 测试验证

### 测试脚本：`tools/test_ruantong_structure.py`

```bash
python tools/test_ruantong_structure.py "/mnt/nas/synnas/docker2/外部数据/软通天擎/jx01/zy/111_主机上料工序-IO挡板上料场景2/503"
```

### 测试结果

```
📂 Directory structure (first 3 levels):
└── 503/
    ├── @eaDir/ ⏭️  [Skipped]
    └── A2D0015AC00557/
        ├── 182088/ ✅ [Episode]
        ├── 182090/ ✅ [Episode]
        ... (194 episodes total)

🔍 Searching for episode directories (up to 5 levels deep)...
✅ Found 194 episode(s)
```

## 支持的目录结构

修复后的代码支持**最多5层嵌套**：

1. **扁平结构**：`task/episode/`
   ```
   task_path/
     ├── episode_001/aligned_joints.h5
     └── episode_002/aligned_joints.h5
   ```

2. **1层嵌套**：`task/batch/episode/`
   ```
   task_path/
     └── batch_A/
         ├── episode_001/aligned_joints.h5
         └── episode_002/aligned_joints.h5
   ```

3. **2层嵌套**（软通天擎）：`task/device/batch/episode/`
   ```
   task_path/
     └── A2D0015AC00557/
         └── 182088/aligned_joints.h5
   ```

4. **更深嵌套**：最多支持5层

## 关键特性

1. **递归搜索**：自动查找任意深度的 episode 目录（最多5层）
2. **系统目录过滤**：自动跳过 `.` 和 `@` 开头的目录
3. **智能停止**：找到 `aligned_joints.h5` 后不再向下搜索
4. **详细错误**：显示目录树结构，方便诊断问题
5. **权限处理**：遇到权限错误继续搜索其他目录

## 修改文件

- **主要修改**：`src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_jpg.py`
  - `_prevalidate_files()` 方法（简化为使用递归搜索）
  - `_get_all_episode_dirs()` 方法（改进错误信息）

- **测试工具**：`tools/test_ruantong_structure.py`
  - 验证目录结构检测逻辑
  - 显示可视化的目录树

## 使用建议

1. **转换前测试**：使用测试脚本验证目录结构
   ```bash
   python tools/test_ruantong_structure.py <task_path>
   ```

2. **检查错误信息**：如果转换失败，查看错误中的目录树结构

3. **目录命名规范**：
   - ✅ 使用普通命名：`episode_001`, `batch_A`, `device_001`
   - ❌ 避免特殊前缀：`.hidden`, `@system`

## 结论

通过利用已有的递归搜索方法并改进错误诊断，修复了软通天擎数据集的目录深度问题：

- ✅ **支持任意深度**（最多5层）的嵌套结构
- ✅ **自动跳过系统目录**（`@eaDir`等）
- ✅ **详细错误提示**，快速定位问题
- ✅ **测试验证通过**（194个episodes成功检测）

现在可以正常转换软通天擎数据集了！🚀
