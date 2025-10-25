# 🔧 修复数据库字段缺失问题

## 📝 问题描述

用户报告：转换完成后，数据库表 `lerobot_format_convert` / `lerobot_format_convert_test` 中的某些条目：
- `device_model` 字段为 **NULL**
- `device_model_version` 字段为 **NULL**

这导致后续无法根据这两个字段查询或统计转换结果。

---

## 🔴 根本原因

### 问题代码调用链

**1. 任务生成阶段** (`generate_task_content` in server.py)
```python
# ✅ 从数据库读取了 device_model 和 device_model_version
item = session.query(DmvAnnotationDB)...
device_model = item.device_model
device_model_version = item.device_model_version

# ✅ 初始化转换状态为 PROCESSING
upsert_leformat_convert(
    session=session,
    ds_uuid=item.dataset_uuid,
    convert_status=TaskStatus.PROCESSING,
    is_test=self.is_test,
)
# ❌ 但是没有传递 device_model 和 device_model_version！

# ✅ 把这些信息发送给 client
task_content = {
    DEVICE_MODEL: item.device_model,  # 发送给 client
    ...
}
```

**2. 任务完成阶段** (`handle_task_result` in server.py)
```python
# ✅ 从 task_content 可以获取 device_model
device_model = task_content.get(DEVICE_MODEL)

# ❌ 但是调用 upsert 时没有传递！
upsert_leformat_convert(
    session=session,
    ds_uuid=ds_uuid,
    convert_status=convert_status,
    leformat_path=leformat_path,
    err_message=task_status_msg,
    is_test=self.is_test,
)
# ❌ 缺少 device_model 和 device_model_version 参数！
```

**3. 数据库更新函数** (`upsert_leformat_convert` in leformat_converter.py)
```python
def upsert_leformat_convert(
    session: Session,
    ds_uuid: str,
    convert_status: TaskStatus,
    err_message: str | None = None,
    leformat_path: str | None = None,
    is_test: bool = False,
) -> None:
    # ❌ 参数列表中根本没有 device_model 和 device_model_version！
    
    if item is None:
        item = leformat_convert_db(
            dataset_uuid=ds_uuid,
            convert_status=convert_status,
            convert_path=leformat_path,
            err_message=err_message,
            # ❌ 创建时没有设置 device_model 和 device_model_version
        )
    else:
        item.convert_status = convert_status
        # ❌ 更新时也没有更新 device_model 和 device_model_version
```

**结果**：数据库中的 `device_model` 和 `device_model_version` 始终是 **NULL**！

---

## ✅ 修复方案

### 修复1: 扩展 `upsert_leformat_convert` 函数签名

**文件**: `src/robocoin_dataset/database/services/leformat_converter.py`

**修改**:
```python
def upsert_leformat_convert(
    session: Session,
    ds_uuid: str,
    convert_status: TaskStatus,
    err_message: str | None = None,
    leformat_path: str | None = None,
    device_model: str | None = None,  # 🆕 添加参数
    device_model_version: str | None = None,  # 🆕 添加参数
    is_test: bool = False,
) -> None:
```

### 修复2: 创建记录时设置字段

**文件**: `src/robocoin_dataset/database/services/leformat_converter.py`

**修改**:
```python
if item is None:
    # 创建新记录
    item = leformat_convert_db(
        dataset_uuid=ds_uuid,
        convert_status=convert_status,
        convert_path=leformat_path,
        err_message=err_message,
        device_model=device_model,  # 🆕 设置字段
        device_model_version=device_model_version,  # 🆕 设置字段
        updated_at=datetime.now(),
    )
```

### 修复3: 更新记录时更新字段

**文件**: `src/robocoin_dataset/database/services/leformat_converter.py`

**修改**:
```python
else:
    # 更新现有记录
    item.convert_status = convert_status
    item.updated_at = datetime.now()
    if err_message is not None:
        item.err_message = err_message
    if leformat_path is not None:
        item.convert_path = leformat_path
    # 🆕 更新字段（如果提供）
    if device_model is not None:
        item.device_model = device_model
    if device_model_version is not None:
        item.device_model_version = device_model_version
```

### 修复4: 任务初始化时传递字段

**文件**: `src/robocoin_dataset/format_converter/tolerobot/server.py`

**位置**: `generate_task_content` 方法

**修改**:
```python
# 初始化转换状态为 PROCESSING
upsert_leformat_convert(
    session=session,
    ds_uuid=item.dataset_uuid,
    convert_status=TaskStatus.PROCESSING,
    device_model=item.device_model,  # 🆕 传递字段
    device_model_version=item.device_model_version,  # 🆕 传递字段
    is_test=self.is_test,
)
```

### 修复5: 任务完成时传递字段

**文件**: `src/robocoin_dataset/format_converter/tolerobot/server.py`

**位置**: `handle_task_result` 方法

**修改**:
```python
def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
    ds_uuid = task_content.get(DATASET_UUID)
    leformat_path = task_content.get(LEFORMAT_PATH, "")
    device_model = task_content.get(DEVICE_MODEL)  # 🆕 获取 device_model
    
    # 🆕 从数据库查询 device_model_version
    device_model_version = None
    with self.db.with_session() as session:
        dmv_item = (
            session.query(DmvAnnotationDB)
            .filter(DmvAnnotationDB.dataset_uuid == ds_uuid)
            .first()
        )
        if dmv_item:
            device_model_version = dmv_item.device_model_version
    
    # ... 
    
    upsert_leformat_convert(
        session=session,
        ds_uuid=ds_uuid,
        convert_status=convert_status,
        leformat_path=leformat_path,
        err_message=task_status_msg,
        device_model=device_model,  # 🆕 传递字段
        device_model_version=device_model_version,  # 🆕 传递字段
        is_test=self.is_test,
    )
```

---

## 📊 修复前后对比

### 修复前

**数据库记录**:
```
dataset_uuid: fe39c248-771e-4c86-bd6e-a994444407a8
convert_status: COMPLETED
convert_path: /mnt/nas/...
device_model: NULL          ❌
device_model_version: NULL  ❌
```

**问题**:
- 无法按 `device_model` 查询转换结果
- 无法统计各设备型号的转换状态
- 数据不完整

### 修复后

**数据库记录**:
```
dataset_uuid: fe39c248-771e-4c86-bd6e-a994444407a8
convert_status: COMPLETED
convert_path: /mnt/nas/...
device_model: discover_robotics_aitbot_mmk2  ✅
device_model_version: third_view             ✅
```

**改进**:
- ✅ 可以按 `device_model` 查询
- ✅ 可以统计各设备型号转换情况
- ✅ 数据完整

---

## 🔍 问题为什么会发生？

### 1. 并发修复的副作用？

**不是！** 并发修复（IntegrityError retry）**没有导致字段丢失**。

并发修复只是添加了重试机制：
```python
except IntegrityError:
    session.rollback()
    continue  # 重试
```

这不会影响字段的设置，因为**字段本来就没有被传递**。

### 2. 真正的原因

这是一个**从一开始就存在的bug**：

1. **设计时遗漏**
   - 在设计 `upsert_leformat_convert` 函数时，忘记添加这两个参数
   
2. **初始实现不完整**
   - 只实现了核心字段（`convert_status`, `convert_path`, `err_message`）
   - 遗漏了元数据字段（`device_model`, `device_model_version`）

3. **调用方也没有传递**
   - `generate_task_content` 和 `handle_task_result` 都没有传递这些字段
   - 形成了完整的"遗漏链"

4. **为什么现在才发现？**
   - 之前可能没有需要按 `device_model` 查询的需求
   - 或者一直使用 `DmvAnnotationDB` 表（源表）查询，没注意到 `LeFormatConvertDB` 表不完整

---

## 🚀 部署步骤

### 1. 代码同步

在所有机器上执行：
```bash
cd ~/robocoin-dataset
git pull origin feat/test
```

### 2. 重启 Server

```bash
# 停止旧的server
Ctrl+C

# 启动新的server
python scripts/format_converters/tolerobot/server.py \
    --db-file=/path/to/datasets.db \
    --host=0.0.0.0 \
    --port=8769 \
    ...
```

### 3. 重启所有 Clients

```bash
# 停止旧的clients
Ctrl+C

# 启动新的clients
python scripts/format_converters/tolerobot/multi_client.py \
    --host <server_ip> \
    --port 8769 \
    --num-clients 4
```

### 4. 验证修复

**查询新转换的记录**:
```sql
SELECT 
    dataset_uuid,
    device_model,
    device_model_version,
    convert_status,
    updated_at
FROM lerobot_format_convert
WHERE updated_at > '2025-10-25 12:00:00'
ORDER BY updated_at DESC
LIMIT 10;
```

**预期结果**:
- `device_model` 不为 NULL ✅
- `device_model_version` 不为 NULL ✅

---

## 🔧 修复旧数据（可选）

如果需要修复之前的 NULL 记录，可以运行以下SQL：

```sql
-- 从 DmvAnnotationDB 表回填数据
UPDATE lerobot_format_convert AS lfc
SET 
    device_model = dmv.device_model,
    device_model_version = dmv.device_model_version
FROM device_model_annotation AS dmv
WHERE lfc.dataset_uuid = dmv.dataset_uuid
  AND lfc.device_model IS NULL;

-- 测试表也同样处理
UPDATE lerobot_format_convert_test AS lfc
SET 
    device_model = dmv.device_model,
    device_model_version = dmv.device_model_version
FROM device_model_annotation AS dmv
WHERE lfc.dataset_uuid = dmv.dataset_uuid
  AND lfc.device_model IS NULL;
```

**统计修复效果**:
```sql
-- 修复前，统计NULL记录数
SELECT COUNT(*) 
FROM lerobot_format_convert 
WHERE device_model IS NULL;

-- 修复后，应该为0
SELECT COUNT(*) 
FROM lerobot_format_convert 
WHERE device_model IS NULL;
```

---

## 📁 修改的文件

1. **`src/robocoin_dataset/database/services/leformat_converter.py`**
   - 添加 `device_model` 和 `device_model_version` 参数
   - 创建记录时设置这两个字段
   - 更新记录时更新这两个字段

2. **`src/robocoin_dataset/format_converter/tolerobot/server.py`**
   - `generate_task_content`: 初始化时传递字段
   - `handle_task_result`: 完成时传递字段
   - 增强日志：显示 device_model 和 device_model_version

---

## 💡 教训

### 1. 完整性检查

**问题**: 添加新字段时，只在数据库 schema 中添加，忘记在业务逻辑中设置。

**解决**: 
- 添加字段后，检查所有写入点
- 使用 NOT NULL 约束（如果可能）强制设置

### 2. 端到端测试

**问题**: 没有测试覆盖字段是否正确写入。

**解决**:
- 转换完成后查询数据库验证
- 添加数据完整性检查

### 3. 参数传递链

**问题**: 参数在调用链中丢失（有数据但不传递）。

**解决**:
- 追踪数据流：source → intermediate → sink
- 确保每一层都传递必要参数

### 4. 并发修复要小心

**教训**: 虽然这次并发修复没有导致字段丢失，但在修改数据库操作时要格外小心：
- 重试时要重新查询最新数据
- 更新时不要覆盖其他线程的修改
- 使用事务隔离级别

---

## ⚠️ 注意事项

### 1. 向后兼容

修复后的代码**完全向后兼容**：
- 参数是可选的（`Optional[str]`）
- 如果调用方不传递，也不会报错
- 只是字段会保持 NULL

### 2. 数据一致性

修复只影响**新的转换记录**：
- 修复前的记录仍然是 NULL
- 需要手动运行 SQL 回填（见上文）
- 或者重新转换（不推荐，成本高）

### 3. 性能影响

**几乎无影响**：
- 只是多传递了2个字符串参数
- 数据库多写入2个字段
- 额外的一次数据库查询（查 device_model_version）

### 4. 日志增强

现在转换完成时会显示：
```
Upsert {uuid} convert status to COMPLETED, 
device_model=discover_robotics_aitbot_mmk2, 
device_model_version=third_view, 
update_message={msg}
```

更容易调试和监控。

---

## 📚 相关问题

这个bug暴露了几个相关问题：

1. **数据库 Schema 和业务逻辑脱节**
   - Schema 有字段但业务逻辑不设置
   - 需要更好的同步机制

2. **调用链复杂导致参数丢失**
   - `DmvAnnotationDB` → `generate_task_content` → `handle_task_result` → `upsert`
   - 参数在某一环丢失

3. **缺少数据完整性验证**
   - 转换完成后没有验证所有字段是否正确
   - 应该添加 assertion 或 validation

---

**修复日期**: 2025-10-25  
**修复人**: AI Assistant (Claude Sonnet 4.5)  
**问题严重性**: 🔴 High（影响数据完整性）  
**修复优先级**: 🔥 Critical（必须立即修复）

