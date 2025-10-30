# 场景标注任务指南

## 概述

场景标注任务用于对数据集进行场景级别的标注，支持单机运行和C/S模式。本系统基于DatasetDB大表结构，集成了RoboCoin-scene-annotator第三方库进行自动化场景标注处理。

## 核心特性

- **自动化场景标注**: 集成RoboCoin-scene-annotator，支持开放词汇目标检测和场景描述生成
- **多种运行模式**: 支持单机运行和分布式C/S架构
- **统一数据管理**: 基于DatasetDB统一管理标注任务和结果
- **灵活配置**: 支持多种检测器和语言模型配置
- **结果格式化**: 自动转换标注结果为parquet和jsonl格式

## 快速开始

### 单机运行

```bash
python scripts/annotation/scene_annotation/scene_annotation.py \
    --db_file_path ./db/datasets_new.db \
    --output_dir ./output/scene_annotations \
    --log_level INFO
```

### C/S模式

#### 启动服务器

```bash
python scripts/annotation/scene_annotation/scene_annotation_server.py \
    --db_file_path ./db/datasets_new.db \
    --output_dir ./output/scene_annotations \
    --host 0.0.0.0 \
    --port 8770 \
    --log_dir ./logs/scene_annotation_server
```

#### 启动客户端

```bash
python scripts/annotation/scene_annotation/scene_annotation_client.py \
    --host 127.0.0.1 \
    --port 8770 \
    --heartbeat-interval 10.0 \
    --log_dir ./logs/scene_annotation_client
```

## 环境设置

### 1. RoboCoin-scene-annotator依赖

RoboCoin-scene-annotator已经集成在项目的`third_parties`目录中。如需重新安装或更新：

```bash
# 进入third_parties目录
cd third_parties/RoboCoin-scene-annotator

# 安装Grounding DINO依赖
cd third_party/GroundingDINO
pip install -e .
cd ../..

# 安装其他依赖
pip install -r requirements.txt

# 下载预训练权重
mkdir -p weights
cd weights
wget -q https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth
cd ..
```

### 2. 语言模型设置（可选）

如需使用本地语言模型，安装Ollama：

```bash
# Linux安装
curl -fsSL https://ollama.com/install.sh | sh

# 启动Ollama服务
ollama serve

# 下载模型（在另一个终端）
ollama pull deepseek-r1:8b
```

### 3. 项目结构
```
robocoin-dataset/
├── third_parties/
│   └── RoboCoin-scene-annotator/
│       ├── scripts/
│       │   ├── run_pipeline.py
│       │   ├── detect.py
│       │   └── generate.py
│       ├── core/
│       │   ├── detectors/
│       │   └── language_models/
│       ├── configs/
│       └── weights/
├── src/robocoin_dataset/annotation/scene_annotation/
│   └── scene_annotation.py
└── scripts/annotation/scene_annotation/
    ├── scene_annotation.py
    ├── scene_annotation_server.py
    └── scene_annotation_client.py
```

## 参数说明

### 单机运行参数

- `--db_file_path`: 数据库文件路径 (必需)
- `--output_dir`: 输出目录路径 (必需)
- `--log_level`: 日志级别 (默认: INFO)

### 服务器参数

- `--db_file_path`: 数据库文件路径 (必需)
- `--output_dir`: 输出目录路径 (必需)
- `--host`: 服务器监听地址 (默认: 0.0.0.0)
- `--port`: 服务器监听端口 (默认: 8770)
- `--log_dir`: 日志目录 (可选)
- `--heartbeat_interval`: 心跳间隔秒数 (默认: 30.0)
- `--timeout`: 任务超时时间秒数 (默认: 3600)

### 客户端参数

- `--host`: 服务器地址 (默认: 127.0.0.1)
- `--port`: 服务器端口 (默认: 8770)
- `--heartbeat-interval`: 心跳间隔秒数 (默认: 10.0)
- `--log_dir`: 日志目录 (可选)

### RoboCoin-scene-annotator配置

系统会自动配置以下参数：
- `--detector.type`: grounding_dino
- `--detector.device`: cpu (可在代码中修改为cuda)
- `--detector.box_threshold`: 0.3
- `--detector.text_threshold`: 0.25
- `--language_model.type`: ollama
- `--language_model.model`: deepseek-r1:8b

## 工作流程

### 1. 任务同步
- 系统从DatasetDB中查询状态为`COMPLETED`的数据集（已完成格式转换）
- 为这些数据集创建场景标注任务记录
- 任务初始状态设置为`PENDING`

### 2. 任务分配（C/S模式）
- 客户端连接服务器并请求任务
- 服务器分配状态为`PENDING`的任务给客户端
- 任务状态更新为`PROCESSING`

### 3. 场景标注处理
- 系统调用RoboCoin-scene-annotator进行场景标注：
  1. **提示词提取**: 从任务描述中提取物体列表
  2. **首帧提取**: 从视频中提取首帧图像
  3. **目标检测**: 使用Grounding DINO进行开放词汇目标检测
  4. **场景描述**: 使用语言模型生成场景描述
- 结果转换为统一格式并保存为parquet和jsonl文件

### 4. 结果保存
- 标注结果保存到指定输出目录：
  - `parquet/{dataset_uuid}_scene_annotations.parquet`
  - `jsonl/{dataset_uuid}_scene_annotations.jsonl`
- 更新DatasetDB中的任务状态为`COMPLETED`或`FAILED`
- 记录错误信息（如果处理失败）

## 输出格式

场景标注结果保存为两种格式：

### Parquet格式
结构化数据，便于数据分析和处理：

| 字段 | 类型 | 描述 |
|------|------|------|
| dataset_uuid | string | 数据集唯一标识符 |
| episode_id | string | 剧集标识符 |
| timestamp | string | 时间戳 |
| objects | list | 检测到的物体列表 |
| scene_description | string | 场景描述 |
| actions | list | 动作列表 |
| scene_type | string | 场景类型 |

### JSONL格式
每行一个JSON对象，便于流式处理：

```json
{
  "dataset_uuid": "example_dataset_uuid",
  "episode_id": "episode_000001",
  "timestamp": "2024-01-01T00:00:00Z",
  "objects": [
    {
      "name": "cup",
      "bbox": [100, 100, 200, 200],
      "confidence": 0.95
    },
    {
      "name": "table", 
      "bbox": [50, 150, 300, 250],
      "confidence": 0.88
    }
  ],
  "scene_description": "A kitchen scene with a cup on a table",
  "actions": ["pick", "place"],
  "scene_type": "kitchen"
}
```

### 目录结构
```
output_dir/
├── parquet/
│   └── {dataset_uuid}_scene_annotations.parquet
└── jsonl/
    └── {dataset_uuid}_scene_annotations.jsonl
```

## 监控和日志

### 服务器日志
- 客户端连接/断开
- 任务分配情况
- 任务完成状态

### 客户端日志
- 服务器连接状态
- 任务处理进度
- 标注结果统计

## 故障处理

### 常见问题

1. **客户端连接失败**
   - 检查服务器是否启动
   - 验证网络连接和端口

2. **RoboCoin-scene-annotator路径错误**
   - 确认路径存在且可访问
   - 检查依赖是否正确安装

3. **任务处理失败**
   - 查看客户端日志获取详细错误信息
   - 检查数据集路径和格式

### 任务恢复

如果客户端异常断开，服务器会自动将正在处理的任务重置为PENDING状态，其他客户端可以重新处理。

## 性能优化

### 多客户端部署
- 可以启动多个客户端并行处理任务
- 每个客户端可以指定不同的设备型号过滤器
- 服务器自动负载均衡

### 资源配置
- 根据硬件配置调整客户端数量
- 监控内存和CPU使用情况
- 适当调整心跳间隔

## 示例用法

### 单机运行示例

```bash
# 基本用法
python scripts/annotation/scene_annotation/scene_annotation.py \
    --db_file_path ./db/datasets_new.db \
    --output_dir ./output/scene_annotations

# 带详细日志
python scripts/annotation/scene_annotation/scene_annotation.py \
    --db_file_path ./db/datasets_new.db \
    --output_dir ./output/scene_annotations \
    --log_level DEBUG
```

### C/S模式示例

#### 1. 启动服务器
```bash
python scripts/annotation/scene_annotation/scene_annotation_server.py \
    --db_file_path ./db/datasets_new.db \
    --output_dir ./output/scene_annotations \
    --host 0.0.0.0 \
    --port 8770 \
    --log_dir ./logs/scene_annotation_server \
    --heartbeat_interval 30.0 \
    --timeout 3600
```

#### 2. 启动客户端（可启动多个）
```bash
# 客户端1
python scripts/annotation/scene_annotation/scene_annotation_client.py \
    --host 127.0.0.1 \
    --port 8770 \
    --heartbeat-interval 10.0 \
    --log_dir ./logs/scene_annotation_client1

# 客户端2（并行处理）
python scripts/annotation/scene_annotation/scene_annotation_client.py \
    --host 127.0.0.1 \
    --port 8770 \
    --heartbeat-interval 10.0 \
    --log_dir ./logs/scene_annotation_client2
```

### 检查处理结果

```bash
# 查看输出目录
ls -la ./output/scene_annotations/

# 查看parquet文件
python -c "import pandas as pd; df = pd.read_parquet('./output/scene_annotations/parquet/example_dataset_scene_annotations.parquet'); print(df.head())"

# 查看jsonl文件
head -n 5 ./output/scene_annotations/jsonl/example_dataset_scene_annotations.jsonl
```

## 注意事项

### 环境要求
1. **GPU内存**: 推荐至少12GB VRAM用于Grounding DINO检测器
2. **磁盘空间**: 确保有足够空间存储标注结果和临时文件
3. **网络连接**: 首次运行需要下载预训练模型权重

### 配置建议
1. **设备选择**: 可在代码中将`detector.device`从`cpu`改为`cuda`以提升性能
2. **语言模型**: 如无本地Ollama，系统会回退到模拟数据生成
3. **超时设置**: 根据数据集大小调整`timeout`参数

### 运行注意事项
1. **依赖检查**: 确保RoboCoin-scene-annotator及其依赖正确安装
2. **权限设置**: 确保输出目录有写入权限
3. **进程监控**: 监控任务处理进度，及时处理异常情况
4. **日志管理**: 定期清理日志文件避免磁盘空间不足
5. **网络稳定**: C/S模式下保持网络连接稳定

### 故障排除
1. **检测器加载失败**: 检查权重文件是否存在和完整
2. **语言模型连接失败**: 确认Ollama服务是否启动
3. **任务处理超时**: 增加timeout参数或检查数据集大小
4. **内存不足**: 减少并行客户端数量或使用CPU模式