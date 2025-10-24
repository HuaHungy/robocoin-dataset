# 系统架构全面理解

## 1. 关键数据文件结构

### 1.1 数据集目录中的YAML文件

在每个数据集目录中，有以下关键文件（用于定位路径和存储元信息）:

```
dataset_root/
├── device_model_annotation.yaml  # 设备型号标注（手动或自动标注）
├── local_dataset_info.yaml       # 数据集本地信息
├── local_task_info.yaml          # 任务信息（任务描述、episode列表等）
└── dataset_uuid.yaml             # 数据集唯一标识符
```

**作用**:
- `device_model_annotation.yaml`: 
  - 存储 `device_model` (如 "zhipingfang", "realman_rmc_aidal")
  - 存储 `device_model_version` (如 "dual_arm_no_pose", "default_version")
  - **决定使用哪个转换器配置**
  
- `local_task_info.yaml`:
  - 存储任务描述 (task descriptions)
  - 存储任务-episode的映射关系
  - 在某些转换器中被读取（如 MCAP, Leju Waibu）
  
- `local_dataset_info.yaml`:
  - 存储数据集基本信息
  - 包含场景类型、物体等元数据
  
- `dataset_uuid.yaml`:
  - 存储全局唯一的 dataset_uuid
  - 用于数据库关联

### 1.2 项目配置文件

```
scripts/format_converters/tolerobot/configs/
├── converter_factory_config.yaml       # 工厂配置（设备型号→转换器映射）
├── converter_config_zhipingfang.yaml   # 各设备的转换配置
├── converter_config_realman_rmc_aidal.yaml  # ✅ 规范示例
└── ... (其他设备型号配置)
```

## 2. 数据库表结构

### 2.1 核心表

#### DatasetDB (datasets)
- 存储数据集基本信息
- **核心字段**: `dataset_uuid` (全局唯一业务标识)
- 其他字段: `dataset_name`, `device_model`, `yaml_file_path`

#### DmvAnnotationDB (device_model_annotation)
- 存储设备型号标注结果
- **关联**: `dataset_uuid` → DatasetDB
- **字段**: 
  - `device_model`: 设备型号 (如 "zhipingfang")
  - `device_model_version`: 版本 (如 "dual_arm_no_pose")
  - `annotation_status`: 标注状态 (PENDING/PROCESSING/COMPLETED/FAILED)
  - `annotatio_file_path`: 标注文件路径

#### LeFormatConvertTestDB (lerobot_format_convert_test)
- **测试转换表**
- 字段:
  - `dataset_uuid`: 关联数据集
  - `convert_status`: 转换状态
  - `convert_path`: 转换输出路径
  - `err_message`: 错误信息
  
#### LeFormatConvertDB (lerobot_format_convert)
- **正式转换表**
- 结构与 TestDB 完全相同
- 用于生产环境转换

### 2.2 数据流向

```
1. 数据集入库 → DatasetDB
                    ↓
2. 设备型号标注 → DmvAnnotationDB (annotation_status: COMPLETED)
                    ↓
3. 测试转换 → LeFormatConvertTestDB (convert_status: COMPLETED)
                    ↓
4. 正式转换 → LeFormatConvertDB (convert_status: COMPLETED)
```

## 3. 转换流程（Server-Client-DB Pipeline）

### 3.1 Test模式流程

```
Server.generate_task_content(is_test=True):
  1. 查询 DmvAnnotationDB: 
     - annotation_status == COMPLETED
     - dataset_uuid NOT IN LeFormatConvertTestDB
     
  2. 读取 DatasetDB.yaml_file_path → dataset_path
  
  3. 从 device_model + device_model_version → 查询 converter_factory_config.yaml
     - 确定: module_path, class_name, converter_config_path
     
  4. 加载 converter_config
  
  5. 构造任务:
     {
       "dataset_uuid": ...,
       "dataset_path": ...,
       "device_model": ...,
       "leformat_path": ...,  # 输出路径
       "converter_config": ...,
       "converter_module_path": ...,
       "converter_class_name": ...,
       "repo_id": ...,
       "is_test": True
     }
     
  6. 插入 LeFormatConvertTestDB (status: PROCESSING)
  
  7. 发送任务给 Client

Client._sync_process_task(task_content):
  1. 创建 LerobotFormatConverter (调用 _prevalidate_files)
  
  2. 执行 converter.convert(is_test=True)
  
  3. 返回结果
  
Server.handle_task_result():
  1. 更新 LeFormatConvertTestDB:
     - 成功: status = COMPLETED
     - 失败: status = FAILED, err_message = ...
```

### 3.2 正式转换流程

```
Server.generate_task_content(is_test=False):
  1. 查询数据集:
     - DmvAnnotationDB.annotation_status == COMPLETED
     - LeFormatConvertTestDB.convert_status == COMPLETED  ✅ 测试已通过
     - dataset_uuid NOT IN LeFormatConvertDB  ✅ 正式转换未开始
     
  2. 构造任务（同 Test模式，但 is_test=False）
  
  3. 插入 LeFormatConvertDB (status: PROCESSING)
  
  4. 发送任务

Client: 同上，但 converter.convert(is_test=False)

Server: 更新 LeFormatConvertDB
```

## 4. _prevalidate_files 的作用

在每个转换器的 `__init__` 中被调用，职责:

1. **验证数据集文件结构**
   - 检查必需的文件/目录是否存在
   - 检查文件格式是否正确

2. **early failure** 机制
   - 在转换开始前发现问题
   - 避免转换到一半才失败
   - 提供清晰的错误信息

3. **各转换器的实现差异**
   - MP4+JSON: 检查 mp4 和 json 文件对应关系
   - H5: 检查 h5 文件内部结构
   - MCAP/Rosbag: 检查 bag/mcap 文件和 topic
   - 等等

## 5. 当前配置文件的问题

### 5.1 字段不全或命名不规范

很多配置文件缺少必要字段或字段命名不一致，导致:
- 转换时找不到数据 → `DataQualityError`
- 配置错误 → `ConfigError`
- 大量数据集无法正确转换

### 5.2 缺乏统一的字段命名规范

训练所需的核心数据:
- **手臂**: `arm_joint_*_rad`, `eef_pos_*_m`, `eef_rot_euler_*_rad`
- **末端执行器**: `gripper_open` (二指), `hand_joint_*` (灵巧手)
- **移动**: `leg_joint_*_rad` / `base_vel_*_m_s`

当前问题:
- 有的配置用 `right_joint_1`，有的用 `right_arm_joint_1`
- 有的用角度，有的用弧度
- 有的缺少必要字段（如 eef pose）

### 5.3 量纲不统一

- 期望: 全部使用 **rad** (弧度) 和 **m** (米)
- 现状: 有的数据集用度、毫米等
- 需要通过 `convert_func` 转换

### 5.4 配置文件与实际数据不匹配

- 配置文件写了某个字段，但数据中不存在
- 数据中有某个字段，但配置文件没写
- 导致：要么转换失败，要么丢失有价值的数据

## 6. device_model_annotation.yaml 的确认问题

### 6.1 为什么重要？

`device_model_annotation.yaml` 决定了：
- 使用哪个转换器
- 使用哪个配置文件
- 如何解析数据

**如果标注错误 → 使用错误的转换器 → 整个数据集转换失败**

### 6.2 与其他YAML的关系

虽然 `device_model_annotation.yaml`, `local_task_info.yaml`, `local_dataset_info.yaml` 之间**没有直接关联**，但:

1. **按数据集分析** (一次处理一个 dataset_uuid):
   - 优点: 清晰、简单
   - 缺点: 耗时（数据集数量多时）

2. **按任务批量分析** (一次处理多个同类型任务):
   - 优点: 高效
   - 缺点: 需要更复杂的逻辑

## 7. 重构工作流程建议

### 7.1 第一阶段: 自动发现数据集格式

**目标**: 编写工具自动读取所有数据集，发现实际存在的字段

```
scripts/dataset_schema_discovery/
├── discover_h5_schema.py        # 发现H5文件结构
├── discover_json_schema.py      # 发现JSON结构
├── discover_mcap_schema.py      # 发现MCAP/Rosbag topics
├── discover_all.py              # 批量发现所有数据集
└── schema_report.py             # 生成可读报告
```

**输出**: 每个数据集的实际schema
```yaml
# outputs/discovered_schemas/dataset_xxx.yaml
device_model: zhipingfang
device_model_version: dual_arm_no_pose
discovered_fields:
  observations:
    images:
      - cam_high: [480, 640, 3]
      - cam_left_wrist: [480, 640, 3]
    state:
      qpos: [100]  # 发现实际shape
      qvel: [100]
  actions:
    qpos: [100]
```

### 7.2 第二阶段: 配置文件规范化

**目标**: 基于发现的schema，补充/修正配置文件

1. **对比工具**: 比较 `converter_config_*.yaml` vs `discovered_schema`
   - 标记缺失字段
   - 标记多余字段
   - 标记命名不规范字段

2. **交互式补充工具**:
   ```bash
   python scripts/config_fixer.py --device-model zhipingfang --version dual_arm_no_pose
   ```
   - 展示缺失/冗余字段
   - 提供自动补全建议
   - 人工确认

3. **字段映射标准化**:
   - 定义统一命名规范（参考 `converter_config_realman_rmc_aidal.yaml`）
   - 自动重命名不规范字段

### 7.3 第三阶段: device_model_annotation 确认

**目标**: 确保每个数据集的 device_model_annotation.yaml 正确

**策略**: 
1. 读取数据集实际数据
2. 与所有已知的 converter_config 进行匹配
3. 推荐最佳匹配的 device_model + version
4. 人工确认或自动更新

### 7.4 第四阶段: 批量测试

**目标**: 使用 Test Pipeline 验证所有配置

```bash
# 批量插入测试任务
python scripts/fill_test_db.py --device-model all

# 启动服务端（Test模式）
python -m robocoin_dataset.format_converter.tolerobot.server --test

# 启动多个客户端
python scripts/format_converters/tolerobot/multi_client.py --num-clients 8
```

**监控**: 
- 测试成功率
- 失败原因分类
- 自动生成修复建议

### 7.5 第五阶段: 正式转换

启动生产Pipeline，按上述流程正式转换

## 8. 需要编写的工具

### 8.1 Schema Discovery（优先级: 最高）
```python
# scripts/dataset_schema_discovery/discover_all.py
def discover_dataset_schema(dataset_path: Path) -> dict:
    """自动发现数据集的实际结构"""
    pass

def compare_schema_vs_config(schema: dict, config: dict) -> dict:
    """对比实际schema与配置文件"""
    pass
```

### 8.2 Config Validator & Fixer（优先级: 高）
```python
# scripts/config_tools/validate_config.py
def validate_converter_config(config_path: Path) -> List[Issue]:
    """验证配置文件的规范性"""
    pass

# scripts/config_tools/fix_config.py  
def suggest_config_fixes(schema: dict, config: dict) -> dict:
    """基于schema提供配置修复建议"""
    pass
```

### 8.3 Batch Test Manager（优先级: 中）
```python
# scripts/test_manager/fill_test_db.py
def fill_test_db_for_device_model(device_model: str):
    """批量填充测试数据库"""
    pass

# scripts/test_manager/monitor_tests.py
def monitor_test_progress():
    """监控测试进度和结果"""
    pass
```

## 9. 下一步行动

1. ✅ 理解系统架构（当前）
2. 📝 编写 Schema Discovery 工具
3. 📝 运行 Schema Discovery，生成报告
4. 📝 编写 Config Validator
5. 📝 修复所有配置文件
6. 📝 确认所有 device_model_annotation.yaml
7. 📝 批量测试
8. 📝 正式转换
9. 🚀 讨论分布式系统异常处理优化

