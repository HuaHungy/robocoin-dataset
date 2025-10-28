# FileExistsError 修复文档

## 📌 问题描述

**错误信息**:
```
FileExistsError: [Errno 17] File exists: '/mnt/nas/synnas/docker2/robocoin-datasets/discover_robotics_aitbot_mmk2_bowl_storage_pepper'

Traceback:
  File "lerobot/datasets/lerobot_dataset.py", line 1073, in create
    obj.meta = LeRobotDatasetMetadata.create(
  File "lerobot/datasets/lerobot_dataset.py", line 317, in create
    obj.root.mkdir(parents=True, exist_ok=False)
```

**数据集**: mmk2 (以及所有使用LeRobotDataset.create的转换器)
**发生阶段**: 创建LeRobot数据集时
**频率**: 重试失败任务时，或并发转换时

---

## 🔍 根本原因

### 1. lerobot库限制

lerobot库的`LeRobotDataset.create()`方法**不支持`exist_ok`参数**：

```python
# lerobot库的create方法签名
def create(
    repo_id: str,
    fps: int,
    features: dict,
    root: str,
    robot_type: str,
    use_videos: bool = True,
    tolerance_s: float = 1e-4,
    image_writer_processes: int = 0,
    image_writer_threads: int = 4,
    video_backend: str = "pyav",
    batch_encoding_size: int = 32,
) -> LeRobotDataset:
    ...
```

**没有`exist_ok`参数！**

### 2. 内部实现问题

lerobot库内部使用：
```python
# lerobot/datasets/lerobot_dataset.py, line 317
obj.root.mkdir(parents=True, exist_ok=False)  # 硬编码为False！
```

这导致：
- 如果目录已存在 → `FileExistsError`
- 无法重试失败的转换
- 并发转换同一任务时冲突

### 3. 触发场景

#### 场景1：重试失败的转换
```
第一次转换: 创建目录 → 转换中途失败 → 目录残留
第二次转换: 尝试创建目录 → FileExistsError ❌
```

#### 场景2：并发转换（理论上不应该发生）
```
Client A: 检查目录不存在 → 准备创建
Client B: 检查目录不存在 → 准备创建
Client A: 创建目录成功
Client B: 创建目录 → FileExistsError ❌
```

#### 场景3：测试后正式转换（理论上不会）
```
测试模式: 不创建目录 ✓
正式模式: 尝试创建目录
  → 如果之前手动测试创建了目录 → FileExistsError ❌
```

---

## ✅ 解决方案

### 核心思路

既然lerobot库不支持`exist_ok`，我们在调用`create()`之前手动处理：

1. **检查目录是否存在**
2. **如果存在，删除它**（假定是之前失败的转换残留）
3. **重试机制**（处理并发竞态条件）
4. **创建新数据集**

### 代码实现

**文件**: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py`

```python
def _create_lerobot_dataset(self) -> LeRobotDataset:
    """创建LeRobot数据集
    
    🔥 处理目录已存在的情况（FileExistsError修复）：
    - 如果output_path已存在，先删除（通常是之前失败的转换残留）
    - 支持重试机制，处理并发创建的竞态条件
    - 然后创建新的数据集
    
    注意：lerobot库的create方法不支持exist_ok参数，必须手动处理
    """
    import shutil
    import time
    from pathlib import Path
    
    output_path = Path(self.output_path)
    
    # 最多重试3次（处理并发竞态条件）
    max_retries = 3
    for retry in range(max_retries):
        # 🔍 如果目录已存在，删除它
        if output_path.exists():
            if self.logger:
                self.logger.warning(
                    f"⚠️  Output directory already exists: {output_path.name}\n"
                    f"   This is likely from a previous failed conversion.\n"
                    f"   🗑️  Removing old directory to retry... (attempt {retry + 1}/{max_retries})"
                )
            try:
                shutil.rmtree(output_path)
                if self.logger:
                    self.logger.info(f"✅ Removed old directory: {output_path.name}")
            except Exception as e:
                if retry == max_retries - 1:  # 最后一次重试失败
                    raise RuntimeError(
                        f"Failed to remove existing output directory after {max_retries} attempts"
                    ) from e
                else:
                    if self.logger:
                        self.logger.warning(f"Failed to remove directory, retrying in 2s...")
                    time.sleep(2)
                    continue
        
        # 🚀 尝试创建数据集
        try:
            return LeRobotDataset.create(
                repo_id=self.repo_id,
                features=self._get_lerobot_features(),
                fps=self.fps,
                robot_type=self.device_model,
                root=self.output_path,
                video_backend=self.video_backend,
                image_writer_processes=self.image_writer_processes,
                image_writer_threads=self.image_writer_threads,
            )
        except FileExistsError as e:
            # 🔄 并发创建导致的竞态条件
            if retry == max_retries - 1:  # 最后一次重试
                raise RuntimeError(
                    f"Failed to create dataset after {max_retries} attempts due to concurrent access."
                ) from e
            else:
                if self.logger:
                    self.logger.warning(
                        f"⚠️  FileExistsError during creation (race condition?), "
                        f"retrying in 2s... (attempt {retry + 1}/{max_retries})"
                    )
                time.sleep(2)
                continue
    
    raise RuntimeError("Unexpected error in _create_lerobot_dataset")
```

---

## 🎯 修复效果

### Before
```
❌ 第一次转换失败 → 目录残留
❌ 第二次转换 → FileExistsError → 任务永远失败
❌ 需要手动删除目录才能重试
```

### After
```
✅ 第一次转换失败 → 目录残留
✅ 第二次转换 → 自动检测并删除旧目录
✅ 继续创建新数据集 → 成功转换
✅ 并发冲突 → 自动重试（最多3次）
```

---

## 🔧 技术细节

### 重试机制

**最多重试3次**，每次间隔2秒，处理：

1. **文件系统延迟**
   - 删除操作可能需要时间生效
   - sleep(2)确保文件系统同步

2. **并发竞态条件**
   - Client A删除目录 → Client B创建目录 → Client A尝试创建
   - 重试机制确保最终一个成功

3. **权限/锁定问题**
   - 目录被其他进程占用
   - 重试给予时间释放资源

### 日志示例

**正常情况（旧目录存在）**:
```
⚠️  Output directory already exists: discover_robotics_aitbot_mmk2_bowl_storage_pepper
   This is likely from a previous failed conversion.
   🗑️  Removing old directory to retry... (attempt 1/3)
✅ Removed old directory: discover_robotics_aitbot_mmk2_bowl_storage_pepper
```

**并发冲突（重试成功）**:
```
⚠️  FileExistsError during creation (race condition?), retrying in 2s... (attempt 1/3)
⚠️  Output directory already exists: ...
   🗑️  Removing old directory to retry... (attempt 2/3)
✅ Removed old directory: ...
```

**重试失败（3次后仍失败）**:
```
⚠️  FileExistsError during creation (race condition?), retrying in 2s... (attempt 3/3)
❌ Failed to create dataset after 3 attempts due to concurrent access.
   Output path: /mnt/nas/synnas/docker2/robocoin-datasets/...
   This indicates multiple clients are trying to convert the same task.
```

---

## 📊 影响范围

### 受益的所有转换器

所有使用`LeRobotDataset.create()`的转换器：
- ✅ `LerobotFormatConverterH5Mp4` (galaxea, alohanew)
- ✅ `LerobotFormatConverterMp4Json` (yinhe)
- ✅ `LerobotFormatConverterH5Jpg` 
- ✅ `LerobotFormatConverterH5`
- ✅ `LerobotFormatConverterJpgJson`
- ✅ `LerobotFormatConverterLejuWaibu` (leju)
- ✅ `LerobotFormatConverterMmk2` (mmk2)
- ✅ 所有其他继承自`LerobotFormatConverter`的转换器

### 不受影响

- `LerobotFormatConverterLerobot` - 直接使用已有数据集，不创建新的

---

## ⚠️ 注意事项

### 1. 数据丢失风险

如果目录已存在但**不是**失败的转换残留（例如，是有效的数据集），会被删除！

**缓解措施**:
- Server应确保不会重复分配已完成的任务
- 数据库状态管理防止重复转换
- 如果真的需要保留，应在删除前备份

### 2. 并发控制

虽然有重试机制，但**不应该**有多个client转换同一任务：
- Server的任务分配逻辑应防止这种情况
- 数据库锁或状态管理
- 如果频繁出现并发冲突，说明Server端有问题

### 3. 性能影响

- `shutil.rmtree()`可能需要时间（大目录）
- 重试机制增加总转换时间（sleep 2秒 × 重试次数）
- 但相比手动干预，仍然是值得的

---

## 🚀 部署步骤

### 1. 更新代码

**所有节点**:
```bash
cd ~/robocoin-dataset
git pull origin feat/test
```

### 2. 重启服务

**Server**:
```bash
# 停止Server进程
# 重新启动Server
```

**Client** (所有节点):
```bash
# 停止Client进程
cd ~/robocoin-dataset
git pull origin feat/test
# 重新启动Client
```

### 3. 验证日志

**正常重试**:
```
⚠️  Output directory already exists: ...
🗑️  Removing old directory to retry...
✅ Removed old directory: ...
```

**没有FileExistsError**:
```
# 不应该再看到这个错误
FileExistsError: [Errno 17] File exists: ...
```

---

## 🔍 排查建议

如果问题仍然存在：

### 1. 检查代码版本

```bash
cd ~/robocoin-dataset
git log --oneline -3 | grep "FileExistsError"
```

### 2. 检查目录权限

```bash
ls -ld /mnt/nas/synnas/docker2/robocoin-datasets/
# 确保有写权限
```

### 3. 检查并发任务

```sql
-- 检查是否有多个client在处理同一任务
SELECT dataset_name, convert_status, COUNT(*) as count
FROM lerobot_format_convert
WHERE convert_status = 'PROCESSING'
GROUP BY dataset_name, convert_status
HAVING count > 1;
```

### 4. 手动清理

如果重试仍然失败，手动删除残留目录：
```bash
rm -rf /mnt/nas/synnas/docker2/robocoin-datasets/discover_robotics_aitbot_mmk2_bowl_storage_pepper
```

---

## 📝 相关文档

- `docs/ALL_FIXES_20251028.md` - 今日所有修复总结
- `docs/CRITICAL_BUG_TASK_RETRY.md` - FAILED任务重试问题
- `docs/GALAXEA_VIDEO_DECODE_FIX.md` - galaxea视频解码修复

---

**修复时间**: 2025-10-28  
**影响版本**: feat/test分支  
**状态**: ✅ 已修复，待部署  
**优先级**: 🔥 高（影响所有转换器的重试功能）

