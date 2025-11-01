# 场景注释 (Scene Annotation) 脚本

本目录包含用于处理机器人数据集场景注释的脚本工具。场景注释功能从数据集的JSON文件中提取场景描述，并生成相应的嵌入向量用于后续的语义搜索和分析。

## 📁 文件结构

```
scene_annotation/
├── README.md                      # 本文档
├── scene_annotation.py            # 本地处理脚本
├── scene_annotation_client.py     # 客户端脚本
├── scene_annotation_server.py     # 服务器脚本
└── test_scene_annotation.py       # 测试脚本
```

## 🚀 快速开始

### 1. 本地处理模式

适用于单机处理数据集的场景注释：

```bash
# 基本用法
python scene_annotation.py --db_file_path ./db/datasets_new.db --data_folder /path/to/dataset

# 处理包含多个数据集的文件夹
python scene_annotation.py --db_file_path ./db/datasets_new.db --data_folder /path/to/datasets_root

# 启用详细日志
python scene_annotation.py --db_file_path ./db/datasets_new.db --data_folder /path/to/dataset --log_level DEBUG

# 指定日志文件目录
python scene_annotation.py --db_file_path ./db/datasets_new.db --data_folder /path/to/dataset --log_dir ./logs
```

### 2. 分布式处理模式

适用于多机器协作处理大量数据集：

#### 启动服务器

```bash
# 基本启动
python scene_annotation_server.py --db_file_path ./db/datasets_new.db

# 指定端口和主机
python scene_annotation_server.py --db_file_path ./db/datasets_new.db --host 0.0.0.0 --port 8769

# 启用日志文件
python scene_annotation_server.py --db_file_path ./db/datasets_new.db --log_dir ./logs
```

#### 启动客户端

```bash
# 连接到本地服务器
python scene_annotation_client.py --host 127.0.0.1 --port 8769

# 连接到远程服务器
python scene_annotation_client.py --host 192.168.1.100 --port 8769

# 设置心跳间隔和日志
python scene_annotation_client.py --host 127.0.0.1 --port 8769 --heartbeat-interval 30 --log_dir ./logs
```

### 3. 测试功能

```bash
# 测试本地处理功能
python test_scene_annotation.py local

# 测试真实数据处理
python test_scene_annotation.py real

# 测试服务器客户端
python test_scene_annotation.py server

# 运行所有测试
python test_scene_annotation.py all
```

## 📋 详细说明

### 场景注释处理流程

1. **数据读取**: 从指定文件夹中读取 `episode_*.json` 文件
2. **描述提取**: 从JSON文件中提取 `description` 字段
3. **嵌入生成**: 使用预训练模型生成场景描述的嵌入向量
4. **数据库更新**: 将嵌入向量存储到数据库中
5. **状态管理**: 更新数据集的处理状态

### 输入数据格式

JSON文件应包含以下结构：

```json
{
  "description": "机器人抓取红色方块并放置到指定位置",
  "other_fields": "..."
}
```

### 数据库要求

- 数据库中应存在对应的数据集记录
- 数据集的转换状态必须为 `COMPLETED`
- 系统会自动管理场景注释的处理状态

## ⚙️ 参数说明

### scene_annotation.py

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--db_file_path` | str | ✅ | - | 数据库文件路径 |
| `--data_folder` | str | ✅ | - | 数据集文件夹路径 |
| `--json_file_path` | str | ❌ | `episode_*.json` | JSON文件路径模式 |
| `--log_level` | str | ❌ | `INFO` | 日志级别 (DEBUG/INFO/WARNING/ERROR) |
| `--log_dir` | str | ❌ | - | 日志文件保存目录 |

### scene_annotation_server.py

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--db_file_path` | str | ✅ | - | 数据库文件路径 |
| `--host` | str | ❌ | `0.0.0.0` | 服务器主机地址 |
| `--port` | int | ❌ | `8769` | 服务器端口 |
| `--log_level` | str | ❌ | `INFO` | 日志级别 |
| `--log_dir` | str | ❌ | - | 日志文件保存目录 |

### scene_annotation_client.py

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--host` | str | ❌ | `127.0.0.1` | 服务器主机地址 |
| `--port` | int | ❌ | `8769` | 服务器端口 |
| `--heartbeat-interval` | float | ❌ | `10.0` | 客户端心跳间隔（秒） |
| `--log_level` | str | ❌ | `INFO` | 日志级别 |
| `--log_dir` | str | ❌ | - | 日志文件保存目录 |

## 🔧 使用场景

### 场景1: 单个数据集处理

```bash
# 处理单个数据集
python scene_annotation.py \
    --db_file_path /mnt/nas/database/datasets_new.db \
    --data_folder /mnt/nas/datasets/robot_dataset_001
```

### 场景2: 批量数据集处理

```bash
# 处理包含多个数据集的根目录
python scene_annotation.py \
    --db_file_path /mnt/nas/database/datasets_new.db \
    --data_folder /mnt/nas/datasets/
```

### 场景3: 分布式处理

```bash
# 在服务器上启动
python scene_annotation_server.py \
    --db_file_path /mnt/nas/database/datasets_new.db \
    --host 0.0.0.0 \
    --port 8769 \
    --log_dir /var/log/scene_annotation

# 在多个客户端机器上启动
python scene_annotation_client.py \
    --host server.example.com \
    --port 8769 \
    --log_dir ./logs
```

## 🐛 故障排除

### 常见问题

1. **数据库文件不存在**
   ```
   错误: 数据库文件不存在: /path/to/database.db
   ```
   - 检查数据库文件路径是否正确
   - 确保有读取权限

2. **数据文件夹不存在**
   ```
   错误: 数据文件夹不存在: /path/to/dataset
   ```
   - 检查数据集路径是否正确
   - 确保文件夹存在且有读取权限

3. **没有找到JSON文件**
   ```
   数据集 xxx 中没有找到JSON文件，跳过
   ```
   - 检查数据集文件夹中是否包含 `episode_*.json` 文件
   - 确认JSON文件格式正确

4. **连接服务器失败**
   ```
   客户端运行失败: Connection refused
   ```
   - 确保服务器已启动
   - 检查主机地址和端口是否正确
   - 检查网络连接和防火墙设置

### 调试技巧

1. **启用详细日志**
   ```bash
   python scene_annotation.py --log_level DEBUG --data_folder /path/to/dataset --db_file_path /path/to/db
   ```

2. **使用测试脚本**
   ```bash
   python test_scene_annotation.py local --verbose
   ```

3. **检查数据库状态**
   - 使用数据库工具查看数据集记录
   - 确认转换状态为 `COMPLETED`

## 📊 性能优化

### 本地处理优化

- 使用SSD存储提高I/O性能
- 确保有足够的内存处理大型数据集
- 考虑使用多进程处理（未来版本支持）

### 分布式处理优化

- 根据网络带宽调整心跳间隔
- 在高性能机器上部署服务器
- 使用多个客户端并行处理

## 🔗 相关文档

- [场景注释核心模块文档](../../src/robocoin_dataset/annotation/scene_annotation/)
- [数据库模型文档](../../src/robocoin_dataset/database/)
- [分布式计算框架文档](../../src/robocoin_dataset/distribution_computation/)

## 📝 更新日志

- **v1.0.0**: 初始版本，支持本地和分布式场景注释处理
- 支持从JSON文件提取场景描述
- 支持嵌入向量生成和存储
- 提供完整的测试套件

## 🤝 贡献

如果您发现问题或有改进建议，请：

1. 查看现有的issue
2. 创建新的issue描述问题
3. 提交pull request

## 📄 许可证

本项目遵循项目根目录的许可证条款。