# Server-Client完整执行流程分析

## 📋 概览

本文档详细追踪整个Server-Client的执行流程，包括任务分配、转换执行、episode跳过、结果返回、数据库更新等所有环节。

---

## 🚀 阶段1: Server启动

### 文件：`server.py` - LeFormatConverterTaskServer

```python
# 启动命令
python scripts/format_converters/tolerobot/server.py \
    --db-file=db/datasets.db \
    --host=172.16.13.140 --port=8769 \
    --is-test --auto-reencode

# 初始化
class LeFormatConverterTaskServer(TaskServer):
    def __init__(self, ...):
        # 1. 连接数据库
        self.db = DatasetDatabase(db_file)
        
        # 2. 加载转换器配置
        self.converter_factory_config = yaml.safe_load(...)
        
        # 3. 初始化父类 (TaskServer)
        super().__init__(host, port, ...)
```

### 启动WebSocket服务

```python
# task_server.py - TaskServer.start()
async def start(self):
    async with serve(self.handle_client, self.host, self.port):
        self.logger.info(f"Task server started: ws://{self.host}:{self.port}")
        await asyncio.Future()  # 永远运行
```

**状态**：Server进入监听状态，等待Client连接

---

## 🤝 阶段2: Client连接和注册

### 文件：`client.py` - LeFormatConverterTaskClient

```python
# 启动命令
python scripts/format_converters/tolerobot/multi_client.py \
    --host 172.16.13.140 --port 8769 --num-clients 4

# 每个client初始化
class LeFormatConverterTaskClient(TaskClient):
    async def run_until_no_task(self):
        # 1. 连接server
        await self.connect_to_server()
        
        # 2. 注册
        await self.register()
        
        # 3. 启动心跳
        await self._start_heartbeat()
        
        # 4. 进入主循环
        while True:
            await self.request_and_process_task()
```

### 注册流程

```python
# task_client.py
async def register(self):
    msg = {
        MSG_TYPE: REGISTER,
        MSG_CONTENT: {
            CLIENT_ID: self.client_id,
            IP: self.local_ip
        }
    }
    await self.websocket.send(json.dumps(msg))
    # 等待server响应...
```

**Server端处理注册**：

```python
# task_server.py - handle_message()
if msg_type == REGISTER:
    await self.register_client(websocket, msg_content)
    # 记录client信息
    self.client_info[websocket] = {
        CLIENT_ID: client_id,
        IP: ip,
        LAST_PONG: time.time()
    }
```

**状态**：Client已连接并注册，准备请求任务

---

## 📋 阶段3: 任务请求和分配

### Client请求任务

```python
# task_client.py - request_and_process_task()
async def request_and_process_task(self):
    # 1. 发送任务请求
    await self.websocket.send(json.dumps({
        MSG_TYPE: REQUEST_TASK,
        MSG_CONTENT: {CLIENT_ID: self.client_id}
    }))
    
    # 2. 等待server返回任务
    response = await asyncio.wait_for(
        self._response_future,
        timeout=self.timeout
    )
    
    # 3. 如果有任务，处理它
    if response[MSG_TYPE] == TASK_ASSIGNED:
        task_data = response[MSG_CONTENT]
        task_result = await self.process_task(task_data)
        
        # 4. 返回结果给server
        await self.websocket.send(json.dumps({
            MSG_TYPE: TASK_RESULT,
            MSG_CONTENT: task_result,
            TASK_ID: task_data[TASK_ID]
        }))
```

### Server生成任务

```python
# server.py - generate_task_content()
def generate_task_content(self) -> dict | None:
    with self.db.with_session() as session:
        # 1. 查询可分配的任务
        if self.is_test:
            # 测试模式：查询annotation完成，且测试表中不存在PROCESSING/COMPLETED的
            results = (
                session.query(DmvAnnotationDB)
                .filter(DmvAnnotationDB.annotation_status == TaskStatus.COMPLETED)
                .filter(
                    ~session.query(LeFormatConvertTestDB)
                    .filter(
                        LeFormatConvertTestDB.dataset_uuid == DmvAnnotationDB.dataset_uuid,
                        LeFormatConvertTestDB.convert_status.in_([
                            TaskStatus.PROCESSING,
                            TaskStatus.COMPLETED,
                        ])
                    )
                    .exists()
                )
                .all()
            )
        else:
            # 正式模式：查询测试完成，且正式表中不存在PROCESSING/COMPLETED的
            # ...类似逻辑
        
        if not results:
            return None  # 没有任务
        
        # 2. 取第一个任务
        for item in results:
            # 3. 验证数据完整性
            dataset_item = session.query(DatasetDB)...
            if dataset_item is None:
                continue  # 跳过无效任务
            
            # 4. 构造任务路径
            dataset_path = str(Path(dataset_item.yaml_file_path).parent)
            dataset_name = dataset_item.dataset_name
            leformat_path = str(Path(self.convert_root_path) / f"{item.device_model}_{dataset_name}")
            
            # 5. 设置任务状态为PROCESSING
            upsert_leformat_convert(
                session=session,
                ds_uuid=item.dataset_uuid,
                convert_status=TaskStatus.PROCESSING,  # ⬅️ 设为PROCESSING
                device_model=item.device_model,
                device_model_version=item.device_model_version,
                is_test=self.is_test,
            )
            
            # 6. 获取转换器配置
            converter_module_path, converter_class_name, converter_config = (
                self._get_converter_module_class_config(
                    device_model=item.device_model,
                    device_model_version=item.device_model_version
                )
            )
            
            # 7. 返回任务内容
            return {
                DATASET_UUID: item.dataset_uuid,
                DATASET_NAME: dataset_name,
                LEFORMAT_PATH: leformat_path,
                DATASET_PATH: dataset_path,
                DEVICE_MODEL: item.device_model,
                CONVERTER_CONFIG: converter_config,
                CONVERTER_MODULE_PATH: converter_module_path,
                CONVERTER_CLASS_NAME: converter_class_name,
                VIDEO_BACKEND: self.video_backend,
                IMAGE_WRITER_PROCESSES: self.image_writer_processes,
                IMAGE_WRITER_THREADS: self.image_writer_threads,
                CONVERTER_LOG_DIR: str(client_log_path),
                REPO_ID: repo_id,
                CONVERTER_LOG_NAME: leformat_name,
                IS_TEST: self.is_test,
                AUTO_REENCODE: self.auto_reencode,
            }
        
        return None  # 所有任务都无效
```

**关键点**：
- ✅ 任务分配时立即设置 `convert_status = PROCESSING`
- ✅ 排除已经在 `PROCESSING` 或 `COMPLETED` 的任务
- ⚠️ **潜在问题1**：如果upsert失败，任务状态不会更新，但任务已经发给client了

**状态**：数据库中任务状态 = PROCESSING，Client收到任务内容

---

## 🔄 阶段4: Client执行转换（核心流程）

### Client处理任务

```python
# task_client.py - process_task()
async def process_task(self, task_data: dict) -> dict:
    loop = asyncio.get_event_loop()
    task_id = task_data.get(TASK_ID)
    try:
        # 在线程池中执行同步的转换任务
        task_result_content = await loop.run_in_executor(
            None, 
            self._sync_process_task,  # ⬅️ 调用同步方法
            task_data
        )
        return {
            TASK_RESULT_STATUS: TASK_SUCCESS,  # ⬅️ 成功
            TASK_RESULT_CONTENT: task_result_content
        }
    except Exception:
        self.logger.error(f"Task {task_id} failed. {traceback.format_exc()}")
        return {
            TASK_RESULT_STATUS: TASK_FAILED,  # ⬅️ 失败
            ERR_MSG: f"Task {task_id} failed. {traceback.format_exc()}",
            TASK_RESULT_CONTENT: {},
        }
```

### 同步转换流程

```python
# client.py - _sync_process_task()
def _sync_process_task(self, task_content: dict) -> dict:
    try:
        # 1. 解析任务参数
        dataset_path = Path(task_content.get(DATASET_PATH))
        output_path = Path(task_content.get(LEFORMAT_PATH))
        device_model = task_content.get(DEVICE_MODEL)
        converter_config = task_content.get(CONVERTER_CONFIG)
        # ... 其他参数
        
        # 2. 设置logger
        logger = setup_logger(converter_log_name, converter_log_dir, logging.INFO)
        
        # 3. 创建转换器实例
        converter: LerobotFormatConverter = LerobotFormatConverterFactory.create_converter(
            dataset_path=dataset_path,
            device_model=device_model,
            output_path=output_path,
            converter_config=converter_config,
            converter_module_path=module_path,
            converter_class_name=class_name,
            repo_id=repo_id,
            video_backend=video_backend,
            image_writer_processes=image_writer_proecesses,
            image_writer_threads=image_writer_threads,
            logger=logger,
            auto_reencode=auto_reencode,
        )
        
        try:
            # 4. 获取总episode数
            total_episodes = converter.get_episodes_num()
            
            # 5. 执行转换（迭代每个episode）
            converted_count = 0
            for task_content, task_ep_idx, ep_idx in tqdm(
                converter.convert(is_test),  # ⬅️ 生成器，逐个返回episode
                total=total_episodes,
                desc="Converting Dataset",
                unit="episode",
            ):
                self.logger.info(f"Converted episode {task_ep_idx} of task {task_content}, total ep_idx is:{ep_idx}")
                converted_count += 1
            
            # 6. 统计跳过的episodes
            skipped_count = total_episodes - converted_count
            if skipped_count > 0:
                self.logger.warning(
                    f"📊 Conversion completed with some episodes skipped:\n"
                    f"   Total episodes found: {total_episodes}\n"
                    f"   Successfully converted: {converted_count}\n"
                    f"   Skipped (data quality issues): {skipped_count}\n"
                    f"   ✅ Check error/ directories for skipped files"
                )
            else:
                self.logger.info(f"✅ Conversion completed successfully: {converted_count}/{total_episodes} episodes")
            
            # 7. 保存episode source mapping（仅正式模式）
            if not is_test:
                converter.save_episode_source_mapping()
            
            return {}  # ⬅️ 返回空dict，表示成功
            
        finally:
            # 8. 清理资源（防止semaphore泄漏）
            try:
                if hasattr(converter, 'lerobot_dataset') and converter.lerobot_dataset is not None:
                    converter.lerobot_dataset.stop_image_writer()
                    self.logger.debug("✅ 已清理image writer资源")
            except Exception as e:
                self.logger.warning(f"⚠️  清理converter资源时出错: {e}")
    
    except Exception as e:
        raise RuntimeError(f"convert dataset {dataset_path} failed") from e
```

**关键点**：
- ✅ `converted_count` 只统计成功转换的episodes
- ✅ `skipped_count = total_episodes - converted_count` 统计跳过的
- ✅ 跳过的episodes不影响任务状态（任务仍然是SUCCESS）
- ⚠️ **潜在问题2**：返回值 `{}` 不包含跳过信息，Server无法知道有多少episodes被跳过

---

## 🔍 阶段5: Episode级别的转换（详细）

### Converter的convert()方法

```python
# lerobot_format_converter.py - convert()
def convert(self, is_test: bool = False):
    """生成器：逐个yield转换后的episode"""
    
    # 1. 获取所有任务路径
    task_paths_dict = self._get_dataset_task_paths()
    
    # 2. 初始化LeRobotDataset
    dataset = self._create_lerobot_dataset()
    self.lerobot_dataset = dataset
    
    # 3. 遍历每个任务
    for task_path, task in task_paths_dict.items():
        # 获取该任务的episode数量
        task_episodes_num = self._get_task_episodes_num(task_path)
        
        # 4. 遍历每个episode
        for ep_idx in range(task_episodes_num):
            try:
                # 5. 调用带容错的转换方法
                result = self._convert_episode_with_fault_tolerance(
                    task_path=task_path,
                    task=task,
                    ep_idx=ep_idx,
                    dataset=dataset,
                    is_test=is_test
                )
                
                # 6. 如果成功，yield结果
                if result is not None:
                    yield result  # ⬅️ 返回给client
                # 如果result是None，表示被跳过，不yield
                
            except CriticalDataError as e:
                # 7. 关键数据错误：跳过episode
                self.logger.warning(f"⚠️  Skipping episode {ep_idx}: {e}")
                self._log_skipped_episode(task_path, ep_idx, str(e))
                continue  # ⬅️ 不yield，直接跳过
            
            except Exception as e:
                # 8. 其他错误：也跳过
                self.logger.error(f"❌ Unexpected error in episode {ep_idx}: {e}")
                self._log_skipped_episode(task_path, ep_idx, str(e))
                continue  # ⬅️ 不yield，直接跳过
```

### 带容错的Episode转换

```python
# lerobot_format_converter.py - _convert_episode_with_fault_tolerance()
def _convert_episode_with_fault_tolerance(
    self,
    task_path: Path,
    task: str,
    ep_idx: int,
    dataset: LeRobotDataset,
    is_test: bool
) -> tuple | None:
    """
    带容错机制的episode转换
    返回: (task, ep_idx, global_ep_idx) 或 None（跳过）
    """
    try:
        # 1. 获取原始episode索引
        original_ep_idx = self._get_original_episode_index(task_path, ep_idx)
        
        # 2. 验证H5文件（如果适用）
        if hasattr(self, '_invalid_h5_files'):
            h5_file_path = self._get_episode_h5_path(task_path, ep_idx)
            if h5_file_path in self._invalid_h5_files:
                raise CriticalDataError(f"H5 file is corrupted: {h5_file_path}")
        
        # 3. 验证episode结构（如果适用）
        if hasattr(self, '_invalid_episodes'):
            ep_dir = self._get_episode_directory(task_path, ep_idx)
            if ep_dir in self._invalid_episodes:
                raise CriticalDataError(f"Episode structure is invalid: {ep_dir}")
        
        # 4. 准备episode数据
        episode_buffers = self._prepare_episode_buffers(task_path, task, ep_idx)
        
        # 5. 写入LeRobotDataset
        global_ep_idx = len(dataset)  # 当前全局索引
        for key, buffer in episode_buffers.items():
            dataset[key][global_ep_idx] = buffer
        
        # 6. 测试模式：只转换2个episodes
        if is_test and global_ep_idx >= 1:
            self.logger.info(f"✅ Test mode: Converted 2 episodes, stopping")
            return None  # ⬅️ 返回None，停止转换
        
        # 7. 返回成功结果
        return (task, ep_idx, global_ep_idx)
        
    except CriticalDataError as e:
        # 关键数据错误：记录并跳过
        self.logger.warning(f"⚠️  CriticalDataError in episode {original_ep_idx}: {e}")
        self._log_skipped_episode(task_path, original_ep_idx, str(e))
        return None  # ⬅️ 返回None，表示跳过
    
    except DataQualityError as e:
        # 数据质量错误：记录并跳过
        self.logger.warning(f"⚠️  DataQualityError in episode {original_ep_idx}: {e}")
        self._log_skipped_episode(task_path, original_ep_idx, str(e))
        return None  # ⬅️ 返回None，表示跳过
    
    except FrameCountMismatchError as e:
        # 帧数不匹配错误（超过容忍度）：记录并跳过
        self.logger.error(f"❌ FrameCountMismatchError in episode {original_ep_idx}: {e}")
        self._log_skipped_episode(task_path, original_ep_idx, str(e))
        return None  # ⬅️ 返回None，表示跳过
    
    except Exception as e:
        # 其他未预期错误：记录并重新抛出
        self.logger.error(f"❌ Unexpected error in episode {original_ep_idx}: {e}", exc_info=True)
        raise
```

### Episode跳过的原因

根据代码，episode会在以下情况被跳过（返回None）：

1. **H5文件损坏**：
   ```python
   if h5_file_path in self._invalid_h5_files:
       raise CriticalDataError(...)
   ```

2. **Episode结构无效**：
   ```python
   if ep_dir in self._invalid_episodes:
       raise CriticalDataError(...)
   ```

3. **JSON解析失败**（MP4+JSON格式）：
   ```python
   # lerobot_format_converter_mp4_json.py
   def _load_json_data(self, json_path: Path) -> dict:
       try:
           with open(json_path, 'r') as f:
               return json.load(f)
       except json.JSONDecodeError as e:
           raise CriticalDataError(f"Failed to parse JSON: {e}") from e
   ```

4. **所有相机加载失败**（MP4+JSON格式）：
   ```python
   if not videos_dict:
       raise CriticalDataError("All cameras failed to load")
   ```

5. **帧数不匹配超过容忍度**（H5+MP4格式）：
   ```python
   # lerobot_format_converter_h5_mp4.py
   def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
       # ...
       frame_diff = abs(h5_frame_num - video_frame_num)
       if frame_diff > 30:
           raise CriticalDataError(f"Frame count mismatch: {frame_diff} frames")
   ```

6. **缺少必要文件**（H5+JPG格式）：
   ```python
   # lerobot_format_converter_h5_jpg.py
   if not aligned_joints_file.exists():
       raise CriticalDataError(f"Missing aligned_joints.h5")
   if not camera_dir.exists():
       raise CriticalDataError(f"Missing camera/ directory")
   ```

7. **缺少必要相机**（多种格式）：
   ```python
   missing_cameras = required_cameras - available_cameras
   if missing_cameras:
       raise CriticalDataError(f"Missing required cameras: {missing_cameras}")
   ```

8. **测试模式限制**：
   ```python
   if is_test and global_ep_idx >= 1:
       return None  # 测试模式只转换2个episodes
   ```

**关键流程**：
```
converter.convert() 迭代
    ↓
发现episode要跳过
    ↓
返回 None（不yield）
    ↓
Client的 for 循环不会计数这个episode
    ↓
converted_count 不增加
    ↓
最后统计: skipped_count = total - converted_count
```

---

## 📤 阶段6: Client返回结果

### Client发送结果

```python
# task_client.py - request_and_process_task()
# 转换完成后
task_result = await self.process_task(task_data)

# 发送结果给server
await self.websocket.send(json.dumps({
    MSG_TYPE: TASK_RESULT,
    TASK_ID: task_data[TASK_ID],
    CLIENT_ID: self.client_id,
    MSG_CONTENT: task_result  # ⬅️ 包含 TASK_RESULT_STATUS 和 TASK_RESULT_CONTENT
}))
```

**task_result 内容**：
```python
# 成功情况
{
    TASK_RESULT_STATUS: TASK_SUCCESS,  # "success"
    TASK_RESULT_CONTENT: {}  # ⚠️ 空dict，不包含跳过信息
}

# 失败情况
{
    TASK_RESULT_STATUS: TASK_FAILED,  # "failed"
    ERR_MSG: "Task xxx failed. Traceback...",
    TASK_RESULT_CONTENT: {}
}
```

⚠️ **发现问题3**：
- `TASK_RESULT_CONTENT` 是空的 `{}`
- 没有传递跳过的episodes数量
- Server无法知道转换了多少episodes、跳过了多少

---

## 💾 阶段7: Server处理结果并更新数据库

### Server接收结果

```python
# task_server.py - handle_message()
elif msg_type == TASK_RESULT:
    client_id = msg.get(CLIENT_ID)
    task_id = msg.get(TASK_ID)
    
    self.logger.info(f"Received task result | Client ID: {client_id} | Task ID: {task_id}")
    
    try:
        task_result_content = msg.get(MSG_CONTENT)
        task_content = self.get_task_content(task_id)
        
        # 调用子类的 handle_task_result
        await asyncio.to_thread(
            self.handle_task_result,
            task_content=task_content,
            task_result_content=task_result_content,
        )
        
        # ✅ 成功日志
        self.logger.info(f"✅ Successfully handled task result for {task_id}")
        
    except Exception as e:
        # ✅ 详细错误日志
        self.logger.error(
            f"❌ Error handling task result for {task_id}: {e}",
            exc_info=True
        )
```

### Server更新数据库

```python
# server.py - handle_task_result()
def handle_task_result(self, task_content: dict, task_result_content: dict) -> None:
    # 1. 提取任务信息
    ds_uuid = task_content.get(DATASET_UUID)
    leformat_path = task_content.get(LEFORMAT_PATH, "")
    device_model = task_content.get(DEVICE_MODEL)
    
    # 2. 提取结果信息
    task_status = task_result_content.get(TASK_RESULT_STATUS)
    task_status_msg = task_result_content.get(ERR_MSG)
    
    # 3. 确定最终状态
    convert_status = TaskStatus.COMPLETED if task_status == TASK_SUCCESS else TaskStatus.FAILED
    
    # 4. 查询 device_model_version
    device_model_version = None
    with self.db.with_session() as session:
        dmv_item = (
            session.query(DmvAnnotationDB)
            .filter(DmvAnnotationDB.dataset_uuid == ds_uuid)
            .first()
        )
        if dmv_item:
            device_model_version = dmv_item.device_model_version
    
    # 5. 更新数据库
    with self.db.with_session() as session:
        upsert_leformat_convert(
            session=session,
            ds_uuid=ds_uuid,
            convert_status=convert_status,  # ⬅️ COMPLETED 或 FAILED
            leformat_path=leformat_path,
            err_message=task_status_msg,
            device_model=device_model,
            device_model_version=device_model_version,
            is_test=self.is_test,
        )
        self.logger.info(
            f"Upsert {ds_uuid} convert status to {convert_status}, "
            f"device_model={device_model}, device_model_version={device_model_version}, "
            f"update_message: {task_status_msg}"
        )
```

### 数据库更新（upsert）

```python
# leformat_converter.py - upsert_leformat_convert()
def upsert_leformat_convert(...) -> None:
    # 重试机制：最多3次
    for attempt in range(3):
        try:
            # 1. 查询是否存在
            item = session.query(leformat_convert_db).filter(...).first()
            
            if item is None:
                # 2. 创建新记录
                item = leformat_convert_db(
                    dataset_uuid=ds_uuid,
                    convert_status=convert_status,  # ⬅️ COMPLETED 或 FAILED
                    convert_path=leformat_path,
                    version_uuid="v0",  # ✅ 修复后：提供值
                    err_message=err_message,
                    device_model=device_model,
                    device_model_version=device_model_version,
                    updated_at=datetime.now(),
                )
            else:
                # 3. 更新现有记录
                item.convert_status = convert_status  # ⬅️ PROCESSING → COMPLETED/FAILED
                item.updated_at = datetime.now()
                if err_message is not None:
                    item.err_message = err_message
                if leformat_path is not None:
                    item.convert_path = leformat_path
                if device_model is not None:
                    item.device_model = device_model
                if device_model_version is not None:
                    item.device_model_version = device_model_version
            
            # 4. 提交
            session.add(item)
            session.commit()  # ⬅️ 提交事务
            return  # 成功
            
        except IntegrityError as e:
            # 5. 并发冲突：回滚并重试
            session.rollback()
            if attempt < 2:
                continue
            else:
                raise RuntimeError(...) from e
        
        except Exception as e:
            session.rollback()
            raise RuntimeError(...) from e
```

**状态**：
- ✅ 数据库状态从 `PROCESSING` 更新为 `COMPLETED` 或 `FAILED`
- ✅ 所有字段（device_model, device_model_version, version_uuid）正确填写
- ✅ 时间戳更新

---

## 🔁 阶段8: 循环继续

Client完成一个任务后，自动请求下一个任务：

```python
# task_client.py - run_until_no_task()
async def run_until_no_task(self) -> None:
    while True:
        result = await self.request_and_process_task()
        
        if result == NO_TASK_AVAILABLE:
            self.logger.info("✅ No more tasks available, exiting")
            break  # 退出循环
        
        if result == TASK_SUCCESS:
            self.logger.info("✅ Task completed successfully, requesting next task")
            # 继续循环，请求下一个任务
```

---

## 🐛 发现的问题汇总

### ⚠️ 问题1: 任务分配失败时的状态不一致

**位置**：`server.py - generate_task_content()`

**问题**：
```python
# 先更新数据库状态
upsert_leformat_convert(
    session=session,
    ds_uuid=item.dataset_uuid,
    convert_status=TaskStatus.PROCESSING,  # ⬅️ 设为PROCESSING
    ...
)

# 然后构造任务返回值
return {...}  # ⬅️ 如果这之前的代码抛异常怎么办？
```

**场景**：
1. 数据库状态设为 `PROCESSING`
2. 后续代码（如查询DatasetDB）失败
3. 返回 `None`，没有任务分配
4. 但数据库状态已经是 `PROCESSING` 了
5. 这个任务永远不会被分配（因为查询会排除PROCESSING）

**建议修复**：
```python
# 先收集所有信息，最后再更新数据库
try:
    # 1. 验证数据
    dataset_item = session.query(DatasetDB)...
    if dataset_item is None:
        continue
    
    # 2. 构造所有内容
    task_content = {...}
    
    # 3. 最后更新数据库（确保前面都成功）
    upsert_leformat_convert(...)
    
    # 4. 返回
    return task_content
except Exception as e:
    # 如果失败，数据库状态不会改变
    self.logger.error(f"Failed to generate task: {e}")
    continue
```

---

### ⚠️ 问题2: 跳过的episodes信息丢失

**位置**：`client.py - _sync_process_task()`

**问题**：
```python
# Client统计了跳过的episodes
skipped_count = total_episodes - converted_count
self.logger.warning(f"Skipped: {skipped_count}")

# 但返回值是空的
return {}  # ⚠️ 没有包含跳过信息
```

**影响**：
- Server不知道转换了多少episodes
- Server不知道跳过了多少episodes
- 数据库中没有记录这些统计信息
- 无法追踪数据质量问题

**建议修复**：
```python
# Client返回详细信息
return {
    "total_episodes": total_episodes,
    "converted_episodes": converted_count,
    "skipped_episodes": skipped_count,
}

# Server记录到数据库
# 需要在models.py添加字段：
# total_episodes = Column(Integer, nullable=True)
# converted_episodes = Column(Integer, nullable=True)
# skipped_episodes = Column(Integer, nullable=True)
```

---

### ⚠️ 问题3: handle_task_result的非原子操作

**位置**：`server.py - handle_task_result()`

**问题**：
```python
# 第一个session：查询
with self.db.with_session() as session:
    dmv_item = session.query(DmvAnnotationDB)...
    device_model_version = dmv_item.device_model_version

# ⏰ 时间窗口：dmv_item可能被修改

# 第二个session：更新
with self.db.with_session() as session:
    upsert_leformat_convert(
        device_model_version=device_model_version,  # 可能已过期
        ...
    )
```

**建议修复**：
```python
# 合并为一个session
with self.db.with_session() as session:
    # 查询
    dmv_item = session.query(DmvAnnotationDB)...
    device_model_version = dmv_item.device_model_version if dmv_item else None
    
    # 立即更新（同一事务）
    upsert_leformat_convert(
        session=session,
        device_model_version=device_model_version,
        ...
    )
```

---

### ⚠️ 问题4: 全局数据库锁设计缺陷

**位置**：`database.py - with_session()`

**问题**：
```python
@contextmanager
def with_session(self) -> Generator[Session, None, None]:
    with self._db_lock:  # ⬅️ 全局锁，串行化所有数据库访问
        gen = self.get_session()
        session = next(gen)
        try:
            yield session
        finally:
            gen.close()
```

**影响**：
- 所有数据库访问完全串行化
- 即使是只读查询也要等待
- 无法利用SQLite的并发读能力
- 成为性能瓶颈

**建议修复**：
```python
# 去除Python级别的锁，依赖SQLite自己的锁机制
@contextmanager
def with_session(self) -> Generator[Session, None, None]:
    gen = self.get_session()
    session = next(gen)
    try:
        yield session
    finally:
        gen.close()

# 配置SQLite连接
self.engine = create_engine(
    database_url,
    connect_args={
        "check_same_thread": False,
        "timeout": 30.0,  # 等待锁的超时时间
    },
    pool_size=10,
    max_overflow=20,
)
```

---

## 📊 完整流程图

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Server启动                                                        │
│    • 连接数据库                                                      │
│    • 加载配置                                                        │
│    • 启动WebSocket服务                                               │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Client连接                                                        │
│    • 连接server                                                      │
│    • 注册client_id                                                   │
│    • 启动心跳                                                        │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. Client请求任务                                                    │
│    • 发送 REQUEST_TASK                                               │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. Server分配任务                                                    │
│    • 查询可分配任务（排除PROCESSING/COMPLETED）                      │
│    • 设置状态 = PROCESSING ⬅️ ⚠️ 问题1：如果后续失败？             │
│    • 构造任务内容                                                    │
│    • 返回 TASK_ASSIGNED                                              │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. Client执行转换                                                    │
│    • 创建Converter实例                                               │
│    • 获取总episodes数: total_episodes                                │
│    • 初始化计数: converted_count = 0                                 │
│    ├──────────────────────────────────────────────────────────────┐ │
│    │ For each episode:                                            │ │
│    │   • converter.convert() yield一个episode                     │ │
│    │   • _convert_episode_with_fault_tolerance()                  │ │
│    │       ├─ 验证H5文件                                          │ │
│    │       ├─ 验证episode结构                                     │ │
│    │       ├─ 准备数据buffers                                     │ │
│    │       ├─ 写入LeRobotDataset                                  │ │
│    │       └─ 返回(task, ep_idx, global_ep_idx) 或 None          │ │
│    │                                                              │ │
│    │   • 如果返回了值（不是None）:                                 │ │
│    │       converted_count += 1                                   │ │
│    │                                                              │ │
│    │   • 如果返回None（跳过）:                                    │ │
│    │       不计数，继续下一个                                      │ │
│    │                                                              │ │
│    │   跳过原因:                                                  │ │
│    │   • H5文件损坏                                               │ │
│    │   • Episode结构无效                                          │ │
│    │   • JSON解析失败                                             │ │
│    │   • 所有相机加载失败                                          │ │
│    │   • 帧数不匹配 > 30帧                                        │ │
│    │   • 缺少必要文件/相机                                         │ │
│    │   • 测试模式限制                                              │ │
│    └──────────────────────────────────────────────────────────────┘ │
│    • 统计跳过: skipped_count = total - converted_count              │
│    • 清理资源（semaphore）                                           │
│    • 返回 {} ⬅️ ⚠️ 问题2：没有包含跳过信息                         │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 6. Client返回结果                                                    │
│    • 发送 TASK_RESULT                                                │
│    • TASK_RESULT_STATUS: SUCCESS 或 FAILED                           │
│    • TASK_RESULT_CONTENT: {} ⬅️ 空的                                │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 7. Server处理结果                                                    │
│    • 接收结果                                                        │
│    • 查询device_model_version ⬅️ ⚠️ 问题3：第1个session            │
│    • 更新数据库 ⬅️ ⚠️ 问题3：第2个session（非原子）                 │
│        convert_status = COMPLETED (如果SUCCESS)                      │
│        convert_status = FAILED (如果FAILED)                          │
│    • 日志: "✅ Successfully handled task result"                     │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 8. 循环继续                                                          │
│    • Client请求下一个任务                                            │
│    • 重复步骤3-7                                                     │
│    • 直到没有更多任务                                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 总结

### Episode跳过的完整流程

1. **Converter检测到问题**：
   - H5损坏、结构无效、JSON解析失败等
   - 抛出 `CriticalDataError` 或 `DataQualityError`

2. **convert()捕获异常**：
   - 记录日志：`⚠️ Skipping episode X`
   - 写入 `error/corrupted_episodes.txt`
   - `continue` 到下一个episode（不yield）

3. **Client不计数跳过的episode**：
   - `for` 循环只计数yield的episodes
   - `converted_count` 不包括跳过的
   - `skipped_count = total - converted`

4. **任务仍然标记为成功**：
   - 只要没有致命错误，任务就是 `TASK_SUCCESS`
   - 跳过的episodes不影响任务状态

5. **Server不知道跳过信息**：
   - Client返回 `{}`，没有统计数据
   - Server只知道任务完成了
   - 数据库只记录 `COMPLETED`

### 当前存在的4个问题

1. ⚠️ **任务分配失败时状态不一致**：数据库已设PROCESSING，但任务分配失败
2. ⚠️ **跳过的episodes信息丢失**：Server和数据库不知道跳过了多少
3. ⚠️ **非原子操作**：两次session之间有时间窗口
4. ⚠️ **全局数据库锁**：串行化所有数据库访问，性能瓶颈

---

**创建日期**: 2025-10-25  
**文档类型**: 完整流程分析 + 问题发现

