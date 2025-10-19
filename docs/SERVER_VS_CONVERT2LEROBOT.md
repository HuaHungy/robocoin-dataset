# Server vs Convert2Lerobot 架构对比

## 📊 概览

项目提供了两种数据集转换方式：
1. **单机模式** (`convert2lerobot.py`) - 适合本地调试和小规模转换
2. **分布式模式** (`server.py` + `client.py`) - 适合生产环境和大规模批量转换

---

## 🎯 模式对比

| 特性 | convert2lerobot.py | server.py + client.py |
|------|-------------------|---------------------|
| **架构** | 单机直接运行 | 分布式 Server-Client |
| **数据源** | 命令行参数 | 数据库 (datasets.db) |
| **并行能力** | 单进程串行 | 多客户端并行 |
| **任务分配** | 手动指定 | 自动调度 |
| **状态跟踪** | 无 | 数据库持久化 |
| **错误恢复** | 手动重试 | 自动重试 |
| **适用场景** | 开发/测试/单个数据集 | 生产/批量/多数据集 |
| **依赖项** | ✅ 最小依赖 | ❌ 需要数据库、WebSocket |
| **学习曲线** | ✅ 简单 | ❌ 需要理解分布式系统 |

---

## 1️⃣ 单机模式 (convert2lerobot.py)

### 架构图
```
┌──────────────────────────────────┐
│  用户手动执行命令                   │
│  python convert2lerobot.py        │
│    --dataset-path data/ruantong  │
│    --output-path outputs/...     │
│    --device-model ruantong_a2d   │
│    --repo-id robocoin/test       │
└────────────┬─────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│  LerobotFormatConverterFactory      │
│  创建对应的转换器实例                  │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│  LerobotFormatConverter             │
│  (H5, H5+JPG, G1, MMK2, etc.)      │
│  ┌───────────────────────────────┐  │
│  │ 1. 读取源数据                  │  │
│  │ 2. 逐 episode 转换             │  │
│  │ 3. 保存 LeRobot 格式           │  │
│  │ 4. 生成映射文件                │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│  输出目录                             │
│  ├── meta.json                      │
│  ├── info.json                      │
│  ├── episode_source_mapping.json ✅  │
│  ├── data/                          │
│  └── videos/                        │
└─────────────────────────────────────┘
```

### 使用示例

```bash
# 基本用法
python scripts/format_converters/tolerobot/convert2lerobot.py \
  --dataset_path "data/ruantong" \
  --output_path "outputs/lerobot_converter" \
  --device_model "ruantong_a2d" \
  --device_model_version "gt02_version" \
  --factory_config_path "scripts/format_converters/tolerobot/configs/converter_factory_config.yaml" \
  --repo_id "robocoin/ruantong_test"

# 测试模式（只转换第一个 episode）
python scripts/format_converters/tolerobot/convert2lerobot.py \
  --dataset_path "data/ruantong" \
  --output_path "outputs/test" \
  --device_model "ruantong_a2d" \
  --repo_id "robocoin/test" \
  --is-test

# 高性能配置
python scripts/format_converters/tolerobot/convert2lerobot.py \
  --dataset_path "data/ruantong" \
  --output_path "outputs/lerobot_converter" \
  --device_model "ruantong_a2d" \
  --repo_id "robocoin/test" \
  --image_writer_processes 8 \
  --image_writer_threads 8 \
  --video_backend pyav
```

### 优点
- ✅ 简单直接，易于理解和使用
- ✅ 无需配置数据库
- ✅ 无需启动服务器
- ✅ 适合快速测试和调试
- ✅ 可以精确控制转换哪个数据集
- ✅ 日志输出直观，便于跟踪问题

### 缺点
- ❌ 一次只能处理一个数据集
- ❌ 无法并行处理多个数据集
- ❌ 失败后需要手动重启
- ❌ 无状态跟踪
- ❌ 不适合大规模批量转换

---

## 2️⃣ 分布式模式 (server.py + client.py)

### 架构图
```
┌────────────────────────────────────────────────────────┐
│             数据库 (datasets.db)                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ DmvAnnotationDB: 数据集标注状态                    │  │
│  │ LeFormatConvertDB: 正式转换状态                    │  │
│  │ LeFormatConvertTestDB: 测试转换状态                │  │
│  │ DatasetDB: 数据集基本信息和路径                    │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────┬──────────────────────────────────────────┘
              │ 查询待转换任务
              ▼
┌──────────────────────────────────────────────────────────┐
│          Server (LeFormatConverterTaskServer)            │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 1. 查询数据库：标注完成 + 未转换的数据集             │  │
│  │ 2. 生成任务内容 (dataset_path, config, etc.)       │  │
│  │ 3. 通过 WebSocket 分发任务给客户端                  │  │
│  │ 4. 接收客户端结果                                   │  │
│  │ 5. 更新数据库状态                                   │  │
│  └────────────────────────────────────────────────────┘  │
└─────┬──────────────────────────────┬─────────────────────┘
      │ Task 1                       │ Task 2
      │ WebSocket                    │ WebSocket
      ▼                              ▼
┌──────────────────┐          ┌──────────────────┐
│  Client 1        │          │  Client 2        │
│  机器A/GPU 0     │          │  机器B/GPU 1     │
│  ┌────────────┐  │          │  ┌────────────┐  │
│  │ Converter  │  │   ...    │  │ Converter  │  │
│  │ 转换数据集  │  │          │  │ 转换数据集  │  │
│  │ 保存映射✅  │  │          │  │ 保存映射✅  │  │
│  └────────────┘  │          │  └────────────┘  │
└──────────────────┘          └──────────────────┘
      │                              │
      │ Result                       │ Result
      └──────────┬───────────────────┘
                 ▼
        数据库状态更新 ✅
```

### 使用示例

#### 启动 Server
```bash
# 测试模式 - 只转换未进入测试表的数据集
python scripts/format_converters/tolerobot/server.py \
  --db-file=db/datasets.db \
  --host=0.0.0.0 \
  --port=8766 \
  --converter-factory-config-path=scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
  --convert-root-path=/mnt/nas/robocoin-datasets-test \
  --specific-device-model=ruantong_a2d \
  --is-test

# 正式模式 - 转换测试完成但未正式转换的数据集
python scripts/format_converters/tolerobot/server.py \
  --db-file=db/datasets.db \
  --host=172.16.18.160 \
  --port=8765 \
  --converter-factory-config-path=scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
  --convert-root-path=/mnt/nas/robocoin-datasets \
  --image-writer-processes=8 \
  --image-writer-threads=8 \
  --video-backend=pyav
```

#### 启动 Client (可以启动多个)
```bash
# Client 1 (机器 A)
python scripts/format_converters/tolerobot/client.py \
  --server-uri=ws://172.16.18.160:8765

# Client 2 (机器 B)
python scripts/format_converters/tolerobot/client.py \
  --server-uri=ws://172.16.18.160:8765

# Client 3 (机器 C)
python scripts/format_converters/tolerobot/client.py \
  --server-uri=ws://172.16.18.160:8765
```

### 工作流程

1. **Server 启动**：
   - 连接数据库
   - 加载转换器工厂配置
   - 监听 WebSocket 连接

2. **Client 连接**：
   - 连接到 Server
   - 发送心跳保活
   - 请求任务

3. **Server 生成任务** (`generate_task_content`):
   ```python
   # 查询条件（测试模式）
   - annotation_status == COMPLETED
   - NOT IN LeFormatConvertTestDB
   - (可选) device_model == specific_device_model
   
   # 查询条件（正式模式）
   - annotation_status == COMPLETED
   - LeFormatConvertTestDB.convert_status == COMPLETED
   - NOT IN LeFormatConvertDB
   
   # 返回任务内容
   return {
       DATASET_UUID: uuid,
       DATASET_PATH: source_path,
       LEFORMAT_PATH: output_path,
       DEVICE_MODEL: device_model,
       CONVERTER_CONFIG: config,
       REPO_ID: repo_id,
       # ... 所有转换参数
   }
   ```

4. **Client 执行转换** (`_sync_process_task`):
   ```python
   # 创建转换器（和 convert2lerobot.py 完全一样）
   converter = LerobotFormatConverterFactory.create_converter(...)
   
   # 执行转换
   for task, task_ep_idx, ep_idx in converter.convert():
       pass
   
   # 保存映射文件 ✅
   converter.save_episode_source_mapping()
   
   # 返回结果
   return {TASK_RESULT_STATUS: TASK_SUCCESS}
   ```

5. **Server 处理结果** (`handle_task_result`):
   ```python
   # 更新数据库
   upsert_leformat_convert(
       ds_uuid=dataset_uuid,
       convert_status=COMPLETED or FAILED,
       leformat_path=output_path,
       err_message=error_msg,
       is_test=is_test
   )
   ```

### 优点
- ✅ 支持多客户端并行转换
- ✅ 自动任务分配和调度
- ✅ 状态持久化到数据库
- ✅ 失败自动重试
- ✅ 适合大规模批量转换
- ✅ 可以在多台机器上分布式运行
- ✅ 统一的任务队列管理
- ✅ 可以暂停/恢复转换流程

### 缺点
- ❌ 架构复杂，需要理解分布式系统
- ❌ 需要配置和维护数据库
- ❌ 需要启动和管理 Server
- ❌ 调试相对困难
- ❌ 依赖项较多（WebSocket, 数据库等）

---

## 🔧 核心代码共享

**关键点**：两种模式使用相同的转换核心！

```python
# convert2lerobot.py (单机模式)
converter = LerobotFormatConverterFactory.create_converter(
    dataset_path=dataset_path,
    device_model=device_model,
    output_path=output_path,
    converter_config=converter_config,
    # ...
)
for task, task_ep_idx, ep_idx in converter.convert(is_test):
    logger.info(f"Converted episode {ep_idx}")

# 保存映射文件 ✅
if not is_test:
    converter.save_episode_source_mapping()

# ================================

# client.py (分布式模式)
converter = LerobotFormatConverterFactory.create_converter(
    dataset_path=dataset_path,
    device_model=device_model,
    output_path=output_path,
    converter_config=converter_config,
    # ...
)
for task, task_ep_idx, ep_idx in converter.convert(is_test):
    self.logger.info(f"Converted episode {ep_idx}")

# 保存映射文件 ✅
if not is_test:
    converter.save_episode_source_mapping()
```

**结论**：两者调用完全相同的转换逻辑，只是任务获取方式不同！

---

## 📋 数据库表结构

分布式模式依赖以下数据库表：

### 1. DmvAnnotationDB
```sql
- dataset_uuid: UUID
- device_model: 设备型号
- device_model_version: 设备版本
- annotation_status: 标注状态 (COMPLETED/PROCESSING/FAILED)
```

### 2. LeFormatConvertTestDB (测试转换)
```sql
- dataset_uuid: UUID
- convert_status: 转换状态 (COMPLETED/PROCESSING/FAILED)
- leformat_path: 输出路径
- err_message: 错误信息
```

### 3. LeFormatConvertDB (正式转换)
```sql
- dataset_uuid: UUID
- convert_status: 转换状态 (COMPLETED/PROCESSING/FAILED)
- leformat_path: 输出路径
- err_message: 错误信息
```

### 4. DatasetDB
```sql
- dataset_uuid: UUID
- dataset_name: 数据集名称
- yaml_file_path: 数据集配置文件路径
```

---

## 🚀 使用建议

### 什么时候用 convert2lerobot.py？
- ✅ 开发和调试新的转换器
- ✅ 测试单个数据集转换
- ✅ 快速验证配置是否正确
- ✅ 不想配置数据库和服务器
- ✅ 临时性的一次性转换任务

### 什么时候用 server + client？
- ✅ 生产环境批量转换
- ✅ 需要转换几十上百个数据集
- ✅ 有多台机器可以并行处理
- ✅ 需要任务状态跟踪和管理
- ✅ 需要自动重试失败的任务
- ✅ 需要集中管理转换流程

---

## 📊 性能对比

| 场景 | convert2lerobot.py | server + client |
|------|-------------------|-----------------|
| 1个数据集 | 100% (基准) | ~100% (略慢，有通信开销) |
| 10个数据集 (串行) | 1000% 时间 | 100% 时间 (10个 client) |
| 100个数据集 (串行) | 10000% 时间 | ~1000% 时间 (10个 client) |

**结论**：单个数据集转换两者性能相当，但大规模批量转换时分布式模式优势明显。

---

## ✅ Episode Source Mapping 支持

两种模式现在都支持生成 `episode_source_mapping.json`：

```bash
# 单机模式
python convert2lerobot.py ...
# ✅ 生成: outputs/dataset/episode_source_mapping.json

# 分布式模式
python server.py ... & python client.py ...
# ✅ 生成: /mnt/nas/robocoin-datasets/dataset/episode_source_mapping.json
```

映射文件包含每个 episode 与其源文件的对应关系，便于追溯和调试。

---

## 🎯 总结

- **convert2lerobot.py**: 简单、直接、适合单次转换和测试
- **server + client**: 强大、可扩展、适合生产环境和批量转换

选择哪个取决于你的具体需求！
