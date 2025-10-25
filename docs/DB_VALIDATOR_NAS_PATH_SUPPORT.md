# 数据库验证器 - NAS路径支持

## 概述

`db_validator_fixed.py` 现在支持**双路径策略**，能够自动适配生产环境（NAS路径）和开发环境（本地路径）。

## 核心特性

### 路径选择优先级

1. **优先使用 NAS 路径** (生产环境)
   - 从数据库 `device_model_annotation.annotatio_file_path` 读取
   - 如果路径存在 → 直接使用
   - 示例：`/mnt/nas/synnao/docker/agilex_cobot_decoupled_magic:h5_mp4_new/`

2. **回退到本地映射路径** (开发环境)
   - 构建路径：`data/{device_model}:{device_model_version}/`
   - 如果 NAS 路径不存在 → 使用本地路径
   - 示例：`data/agilex_cobot_decoupled_magic:h5_mp4_new/`

3. **都不存在**
   - 跳过该任务
   - 记录警告日志

### 路径来源追踪

每个任务配置都包含 `path_source` 字段：
- `"NAS"` - 使用生产环境 NAS 路径
- `"local"` - 使用开发环境本地路径

## 使用场景

### 场景 1：生产环境（NAS 已挂载）

```yaml
数据库记录:
  device_model: agilex_cobot_decoupled_magic
  device_model_version: h5_mp4_new
  annotatio_file_path: /mnt/nas/synnao/docker/agilex_cobot_decoupled_magic:h5_mp4_new/

验证器行为:
  ✅ 检查 /mnt/nas/synnao/docker/agilex_... → 存在
  ✅ 使用 NAS 路径
  ✅ path_source = "NAS"
```

### 场景 2：开发环境（NAS 未挂载）

```yaml
数据库记录:
  device_model: agilex_cobot_decoupled_magic
  device_model_version: h5_mp4_new
  annotatio_file_path: /mnt/nas/synnao/docker/agilex_cobot_decoupled_magic:h5_mp4_new/

验证器行为:
  ❌ 检查 /mnt/nas/synnao/docker/agilex_... → 不存在（NAS未挂载）
  ✅ 检查 data/agilex_cobot_decoupled_magic:h5_mp4_new/ → 存在
  ✅ 使用本地路径
  ✅ path_source = "local"
```

### 场景 3：数据集不可用

```yaml
验证器行为:
  ❌ 检查 NAS 路径 → 不存在
  ❌ 检查本地路径 → 不存在
  ⚠️ 跳过该任务
```

## 命令行使用

### 基础测试（快速验证）

```bash
python scripts/config_validation/db_validator_fixed.py \
  --db-path /path/to/database.db \
  --num-samples 1
```

### 完整测试

```bash
python scripts/config_validation/db_validator_fixed.py \
  --db-path /path/to/database.db \
  --num-samples 2
```

### 调试模式

```bash
python scripts/config_validation/db_validator_fixed.py \
  --db-path /path/to/database.db \
  --num-samples 1 \
  --log-level DEBUG
```

### 自定义路径

```bash
python scripts/config_validation/db_validator_fixed.py \
  --db-path /path/to/database.db \
  --data-root /custom/data/path \
  --output-dir /custom/output/path
```

## 验证报告

### 报告结构增强

```json
{
  "metadata": {
    "total_db_tasks": 50,
    "local_available_tasks": 18,
    "path_sources": {
      "nas_paths": 15,      // ← 使用 NAS 路径的任务数
      "local_paths": 3      // ← 使用本地路径的任务数
    }
  },
  "summary": {
    "successful_tasks": 16,
    "partial_tasks": 1,
    "failed_tasks": 0,
    "skipped_tasks": 1
  },
  "validation_results": [
    {
      "device_model": "agilex_cobot_decoupled_magic",
      "device_model_version": "h5_mp4_new",
      "dataset_path": "/mnt/nas/synnao/docker/...",
      "path_source": "NAS",    // ← 新增字段
      "validation_status": "success"
    }
  ]
}
```

### 日志输出示例

```
✅ 验证报告已保存: outputs/db_validation_fixed/db_validation_report_20251024_153000.json
   - 数据库任务总数: 50
   - 本地可用任务: 18
     • NAS路径: 15      ← 生产环境数据
     • 本地路径: 3      ← 开发环境数据
   - 验证成功: 16
   - 部分成功: 1
   - 失败: 0
   - 跳过: 1
```

## 技术实现

### 关键方法：`map_db_task_to_local()`

```python
def map_db_task_to_local(self, db_task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """将数据库任务映射到本地配置"""
    
    # 1. 优先使用 NAS 路径
    db_path_str = db_task.get("annotatio_file_path")
    if db_path_str:
        db_path = Path(db_path_str)
        if db_path.exists():
            dataset_path = db_path
            path_source = "NAS"
    
    # 2. 回退到本地路径
    if dataset_path is None:
        local_path = self.data_root / f"{device_model}:{device_model_version}"
        if local_path.exists():
            dataset_path = local_path
            path_source = "local"
    
    # 3. 都不存在
    if dataset_path is None:
        return None
    
    # 返回配置（包含 path_source）
    return {
        "dataset_path": str(dataset_path),
        "path_source": path_source,
        # ... 其他字段
    }
```

## 核心优势

### ✅ 自动适配环境
- 生产环境自动使用 NAS 路径
- 开发环境自动使用本地路径
- **无需手动切换配置**

### ✅ 透明的路径追踪
- 报告显示使用了哪种路径
- 便于调试和问题定位
- 统计不同路径来源的任务数量

### ✅ 向后兼容
- 保持原有的命令行接口
- 不影响现有的工作流
- 开发环境下行为不变

## 测试建议

### 在生产环境测试

1. **获取数据库路径**
   ```bash
   # 确认数据库文件位置
   ls -lh /path/to/database.db
   
   # 确认 NAS 是否已挂载
   df -h | grep /mnt/nas
   ```

2. **快速测试**
   ```bash
   python scripts/config_validation/db_validator_fixed.py \
     --db-path /path/to/database.db \
     --num-samples 1 \
     --log-level INFO
   ```

3. **检查报告**
   - 确认 `nas_paths > 0`（说明 NAS 路径有效）
   - 查看是否有失败的任务
   - 检查 episode 验证结果

4. **完整验证**
   ```bash
   python scripts/config_validation/db_validator_fixed.py \
     --db-path /path/to/database.db \
     --num-samples 2
   ```

## 故障排查

### 问题：所有任务都使用本地路径（`local_paths = N`, `nas_paths = 0`）

**可能原因：**
- NAS 未挂载
- NAS 挂载点不正确
- 数据库中的 `annotatio_file_path` 为空

**解决方法：**
```bash
# 检查 NAS 挂载
df -h | grep /mnt/nas

# 检查数据库路径
sqlite3 /path/to/database.db "SELECT annotatio_file_path FROM device_model_annotation LIMIT 5;"
```

### 问题：大量任务被跳过

**可能原因：**
- NAS 未挂载且本地数据不完整
- 数据库中的路径与实际不符

**解决方法：**
- 生产环境：确保 NAS 已正确挂载
- 开发环境：确保 `data/` 目录包含必要的数据集

## 相关文档

- [三阶段验证系统](THREE_PHASE_VALIDATION_SYSTEM.md)
- [Schema 对比工具](../scripts/config_validation/schema_comparator.py)
- [原始使用指南](DB_VALIDATOR_FIXED_GUIDE.md)

## 更新日志

- **2024-10-24**: 添加 NAS 路径支持和回退机制
- **2024-10-24**: 添加路径来源追踪（`path_source` 字段）
- **2024-10-24**: 增强验证报告，添加路径统计信息

