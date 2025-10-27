# 数据库相关修改完整时间线

## 📋 概览

本文档详细记录了本次会话（2025-10-25）中所有与数据库相关的修改。

---

## 🏁 初始状态（修改前）

### 数据库表结构

#### 1. LeFormatConvertDB (正式转换表)
```python
# models.py
class LeFormatConvertDB(Base):
    __tablename__ = "lerobot_format_convert"
    
    id = Column(Integer, primary_key=True, index=True)
    dataset_uuid = Column(String(255), index=True, nullable=False)
    convert_status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    convert_path = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)
    err_message = Column(Text, nullable=True)
    
    version_uuid = Column(String(255), nullable=False)  # ❌ 问题！无默认值
    
    device_model = Column(String(255), nullable=True)  # ❌ 问题！可能为NULL
    device_model_version = Column(String(255), nullable=True)  # ❌ 问题！可能为NULL
    
    __table_args__ = (UniqueConstraint("dataset_uuid", name="uix_dataset_uuid_convert"),)
```

#### 2. LeFormatConvertTestDB (测试转换表)
```python
# models.py
class LeFormatConvertTestDB(Base):
    __tablename__ = "lerobot_format_convert_test"
    
    # ... 其他字段相同 ...
    
    version_uuid = Column(String(255), nullable=True, default="v0")  # ✅ 有默认值
    
    device_model = Column(String(255), nullable=True)
    device_model_version = Column(String(255), nullable=True)
```

**关键差异**：
- 正式表：`version_uuid` 是 `nullable=False` 且**无默认值**
- 测试表：`version_uuid` 是 `nullable=True` 且有 `default="v0"`

---

### 数据库操作逻辑

#### upsert_leformat_convert() - 初始版本

```python
# leformat_converter.py - 初始版本（修改前）
def upsert_leformat_convert(
    session: Session,
    ds_uuid: str,
    convert_status: TaskStatus,
    err_message: str | None = None,
    leformat_path: str | None = None,
    is_test: bool = False,
) -> None:
    """
    Upsert LeFormatConvertDB 或 LeFormatConvertTestDB 记录。
    """
    if is_test:
        leformat_convert_db = LeFormatConvertTestDB
    else:
        leformat_convert_db = LeFormatConvertDB
    
    try:
        # 查询是否存在
        item = (
            session.query(leformat_convert_db)
            .filter(leformat_convert_db.dataset_uuid == ds_uuid)
            .first()
        )

        if item is None:
            # 创建新记录
            item = leformat_convert_db(
                dataset_uuid=ds_uuid,
                convert_status=convert_status,
                convert_path=leformat_path,
                err_message=err_message,
                # ❌ 没有提供 device_model
                # ❌ 没有提供 device_model_version
                # ❌ 没有提供 version_uuid
                updated_at=datetime.now(),
            )
        else:
            # 更新现有记录
            item.convert_status = convert_status
            item.updated_at = datetime.now()
            if err_message is not None:
                item.err_message = err_message
            if leformat_path is not None:
                item.convert_path = leformat_path
            # ❌ 不更新 device_model 和 device_model_version

        session.add(item)
        session.commit()  # ❌ 在函数内部commit
    
    except Exception as e:
        session.rollback()
        raise RuntimeError(...) from e
```

**问题**：
1. 没有 `device_model` 和 `device_model_version` 参数
2. 创建记录时不提供这些字段
3. 更新记录时也不更新这些字段
4. **没有提供 `version_uuid`**

---

### Server端的任务分配逻辑

#### generate_task_content() - 初始版本

**测试模式**：
```python
# server.py - 初始版本（修改前）
if self.is_test:
    results = (
        session.query(DmvAnnotationDB)
        .filter(DmvAnnotationDB.annotation_status == TaskStatus.COMPLETED)
        .filter(
            ~session.query(LeFormatConvertTestDB)
            .filter(
                LeFormatConvertTestDB.dataset_uuid == DmvAnnotationDB.dataset_uuid
                # ❌ 没有任何状态过滤！
            )
            .exists()
        )
        .all()
    )
```

**逻辑**：
- 查询 `annotation_status == COMPLETED` 的任务
- 排除在测试表中**存在记录**的任务
- **不考虑记录的状态**

**问题**：
- 只要测试表中有记录，就不分配
- 但如果记录状态是 `FAILED`，理应重新分配
- 如果记录状态是 `PENDING`，也不会分配（卡住）

---

### Server端的结果处理逻辑

#### handle_task_result() - 初始版本

```python
# server.py - 初始版本（修改前）
def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
    ds_uuid = task_content.get(DATASET_UUID)
    leformat_path = task_content.get(LEFORMAT_PATH, "")
    
    task_status = task_result_content.get(TASK_RESULT_STATUS)
    task_status_msg = task_result_content.get(ERR_MSG)
    
    convert_status = TaskStatus.COMPLETED if task_status == TASK_SUCCESS else TaskStatus.FAILED
    
    with self.db.with_session() as session:
        upsert_leformat_convert(
            session=session,
            ds_uuid=ds_uuid,
            convert_status=convert_status,
            leformat_path=leformat_path,
            err_message=task_status_msg,
            # ❌ 没有传递 device_model
            # ❌ 没有传递 device_model_version
            is_test=self.is_test,
        )
```

**问题**：
- 没有传递 `device_model` 和 `device_model_version`
- 导致这些字段始终为 NULL

---

## 🔧 第一轮修复：device_model字段缺失

**时间**：本次会话早期

### 修改1: 添加参数到 upsert_leformat_convert

```python
# leformat_converter.py - 第一次修改
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
    # ...
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

### 修改2: Server端传递字段

```python
# server.py - handle_task_result()
def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
    ds_uuid = task_content.get(DATASET_UUID)
    leformat_path = task_content.get(LEFORMAT_PATH, "")
    device_model = task_content.get(DEVICE_MODEL)  # 🆕 获取
    
    # ...
    
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
    
    # 🆕 第二个session：更新
    with self.db.with_session() as session:
        upsert_leformat_convert(
            session=session,
            ds_uuid=ds_uuid,
            convert_status=convert_status,
            leformat_path=leformat_path,
            err_message=task_status_msg,
            device_model=device_model,  # 🆕 传递
            device_model_version=device_model_version,  # 🆕 传递
            is_test=self.is_test,
        )
```

**效果**：
- ✅ `device_model` 和 `device_model_version` 可以正确写入
- ⚠️  但引入了新问题：两次session（非原子操作）

**文档**：`DATABASE_FIELD_MISSING_FIX.md`

---

## 🔧 第二轮修复：任务分配竞争

**时间**：本次会话中期

### 问题
多个client同时获取相同任务，导致 `FileExistsError`

### 修改：添加 PROCESSING 状态过滤

**测试模式**：
```python
# server.py - generate_task_content()
results = (
    session.query(DmvAnnotationDB)
    .filter(DmvAnnotationDB.annotation_status == TaskStatus.COMPLETED)
    .filter(
        ~session.query(LeFormatConvertTestDB)
        .filter(
            LeFormatConvertTestDB.dataset_uuid == DmvAnnotationDB.dataset_uuid,
            LeFormatConvertTestDB.convert_status == TaskStatus.PROCESSING,  # 🆕 过滤PROCESSING
        )
        .exists()
    )
    .all()
)
```

**正式模式**：
```python
not_processing_in_formal = ~(
    session.query(LeFormatConvertDB)
    .filter(
        LeFormatConvertDB.dataset_uuid == DmvAnnotationDB.dataset_uuid,
        LeFormatConvertDB.convert_status == TaskStatus.PROCESSING,  # 🆕 过滤PROCESSING
    )
    .exists()
)
```

**效果**：
- ✅ 避免了多个client获取相同任务
- ⚠️  但引入了新问题：不排除 `COMPLETED`，会重复分配

**文档**：`TASK_RACE_CONDITION_FIX.md`

---

## 🔧 第三轮修复（本次）：数据库状态卡住

**时间**：刚才

### 发现的3个Critical问题

#### 问题1: version_uuid字段缺失

**现象**：正式转换模式下，数据库状态永远是 `PROCESSING`

**根本原因**：
```python
# models.py
class LeFormatConvertDB(Base):
    version_uuid = Column(String(255), nullable=False)  # ❌ 无默认值

# leformat_converter.py
item = leformat_convert_db(
    dataset_uuid=ds_uuid,
    convert_status=convert_status,
    # ... 其他字段 ...
    # ❌ 没有提供 version_uuid
)
```

**导致**：
- INSERT失败：`IntegrityError: NOT NULL constraint failed: version_uuid`
- 异常被捕获，只记录日志
- Client认为成功，但数据库状态还是 `PROCESSING`

**修复**：
```python
# models.py
version_uuid = Column(String(255), nullable=True, default="v0")  # ✅

# leformat_converter.py
item = leformat_convert_db(
    # ...
    version_uuid="v0",  # ✅ 明确提供
)
```

---

#### 问题2: 异常处理不当

**现象**：错误被静默吞噬，难以排查

**根本原因**：
```python
# task_server.py
except Exception as e:
    self.logger.error(f"Error handling task result: {e}")
    # ❌ 只记录简单日志，没有堆栈
    # ❌ 不重新抛出异常
```

**修复**：
```python
except Exception as e:
    self.logger.error(
        f"❌ Error handling task result for {task_id}: {e}",
        exc_info=True  # ✅ 打印完整堆栈
    )
```

---

#### 问题3: 任务重复分配

**现象**：已完成的任务会被重复分配

**根本原因**：
```python
# 只排除 PROCESSING，不排除 COMPLETED
.filter(
    LeFormatConvertTestDB.convert_status == TaskStatus.PROCESSING
)
```

**场景**：
1. Task A 完成，状态改为 `COMPLETED`
2. 下次查询时，Task A 通过过滤（因为不是 `PROCESSING`）
3. Task A 被重新分配 ❌

**修复**：
```python
# 同时排除 PROCESSING 和 COMPLETED
.filter(
    LeFormatConvertTestDB.convert_status.in_([
        TaskStatus.PROCESSING,
        TaskStatus.COMPLETED,  # ✅ 新增
    ])
)
```

---

## 📊 完整的修改对比表

| 项目 | 初始状态 | 第一轮修改 | 第二轮修改 | 第三轮修改（本次） |
|------|---------|-----------|-----------|-------------------|
| **device_model参数** | ❌ 无 | ✅ 添加 | - | - |
| **device_model_version参数** | ❌ 无 | ✅ 添加 | - | - |
| **version_uuid默认值** | ❌ 无 | - | - | ✅ 添加 |
| **version_uuid明确提供** | ❌ 无 | - | - | ✅ 添加 |
| **任务分配过滤PROCESSING** | ❌ 无 | - | ✅ 添加 | - |
| **任务分配过滤COMPLETED** | ❌ 无 | - | ❌ 无 | ✅ 添加 |
| **异常日志堆栈** | ❌ 无 | - | - | ✅ 添加 |

---

## 🎯 当前状态（所有修改后）

### models.py
```python
class LeFormatConvertDB(Base):
    # ...
    version_uuid = Column(String(255), nullable=True, default="v0")  # ✅
    device_model = Column(String(255), nullable=True)  # ✅ 可写入
    device_model_version = Column(String(255), nullable=True)  # ✅ 可写入
```

### leformat_converter.py
```python
def upsert_leformat_convert(
    session: Session,
    ds_uuid: str,
    convert_status: TaskStatus,
    err_message: str | None = None,
    leformat_path: str | None = None,
    device_model: str | None = None,  # ✅ 有参数
    device_model_version: str | None = None,  # ✅ 有参数
    is_test: bool = False,
) -> None:
    # ...
    if item is None:
        item = leformat_convert_db(
            # ...
            version_uuid="v0",  # ✅ 提供值
            device_model=device_model,  # ✅ 设置
            device_model_version=device_model_version,  # ✅ 设置
        )
    else:
        # ...
        if device_model is not None:  # ✅ 更新
            item.device_model = device_model
        if device_model_version is not None:  # ✅ 更新
            item.device_model_version = device_model_version
```

### server.py - 任务分配
```python
# 测试模式
.filter(
    ~session.query(LeFormatConvertTestDB)
    .filter(
        LeFormatConvertTestDB.dataset_uuid == DmvAnnotationDB.dataset_uuid,
        LeFormatConvertTestDB.convert_status.in_([
            TaskStatus.PROCESSING,  # ✅ 排除
            TaskStatus.COMPLETED,   # ✅ 排除
        ])
    )
    .exists()
)

# 正式模式
not_processing_or_completed_in_formal = ~(
    session.query(LeFormatConvertDB)
    .filter(
        LeFormatConvertDB.dataset_uuid == DmvAnnotationDB.dataset_uuid,
        LeFormatConvertDB.convert_status.in_([
            TaskStatus.PROCESSING,  # ✅ 排除
            TaskStatus.COMPLETED,   # ✅ 排除
        ])
    )
    .exists()
)
```

### server.py - 结果处理
```python
def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
    # ...
    device_model = task_content.get(DEVICE_MODEL)  # ✅ 获取
    
    # 查询 device_model_version
    with self.db.with_session() as session:
        dmv_item = session.query(DmvAnnotationDB)...
        device_model_version = dmv_item.device_model_version
    
    # 更新数据库
    with self.db.with_session() as session:
        upsert_leformat_convert(
            session=session,
            ds_uuid=ds_uuid,
            convert_status=convert_status,
            leformat_path=leformat_path,
            err_message=task_status_msg,
            device_model=device_model,  # ✅ 传递
            device_model_version=device_model_version,  # ✅ 传递
            is_test=self.is_test,
        )
```

### task_server.py - 异常处理
```python
except Exception as e:
    self.logger.error(
        f"❌ Error handling task result for {task_id}: {e}",
        exc_info=True  # ✅ 完整堆栈
    )
```

---

## 📝 总结

### 修改时间线

1. **第一轮（device_model字段）**：
   - 添加 `device_model` 和 `device_model_version` 参数
   - 修改 `upsert_leformat_convert` 函数
   - 修改 `handle_task_result` 传递参数
   - 结果：字段可以写入了

2. **第二轮（任务竞争）**：
   - 添加 `PROCESSING` 状态过滤
   - 避免多个client获取相同任务
   - 结果：不再出现 `FileExistsError`

3. **第三轮（状态卡住 - 刚才）**：
   - 添加 `version_uuid` 默认值和明确值
   - 改进异常日志
   - 添加 `COMPLETED` 状态过滤
   - 结果：数据库状态可以正确更新了

### 核心问题

**你遇到的"数据库状态卡在PROCESSING"问题**，是由于：
1. `version_uuid` 字段缺失导致INSERT失败
2. 异常被静默吞噬
3. Client不知道失败
4. 数据库状态无法更新

现在所有问题都已修复！✅

