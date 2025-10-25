# 重构问题总结

**日期**: 2025-10-21  
**状态**: 讨论阶段

---

## 📋 目录

1. [原始需求](#原始需求)
2. [容错机制设计](#容错机制设计)
3. [LeRobot格式兼容性](#lerobot格式兼容性)
4. [分布式系统问题](#分布式系统问题)
5. [待解决问题](#待解决问题)
6. [已完成工作](#已完成工作)

---

## 原始需求

### 用户提出的三大核心问题

#### 1. 帧数不一致问题
**现状**:
- `docs/`文件夹中有很多关于帧数不对的问题记录
- 之前使用`scripts/dataset_statistics/`中的预检测脚本

**需求**:
- 不要再加检测脚本
- 在正式转换时直接跳过有问题的数据
- 但要避免配置文件错误导致整个数据集无法转换

**引申问题**: 
- 如果配置文件写错（字段不存在），会导致全部报错，一个数据都转不了

#### 2. 配置文件错误
**现状**:
- 有些数据集的配置文件写错了
- 有些字段没被识别
- 很多数据已经用错误配置转换过

**需求**:
- 重新读所有数据集的数据
- 补充逻辑和配置
- 这是一个大工程

#### 3. MP4读取内存溢出
**现状**:
- 转换器会加载整个视频到内存
- 导致OOM（Out of Memory）错误

**用户洞察**:
- "主要我们为啥要读就是因为要对齐视频帧数和其他数据的帧数"
- 不需要加载全部数据，只需要验证帧数

---

## 容错机制设计

### 问题演变

#### 初始设计（❌ 错误）
**帧级容错** - 跳过单个坏帧，继续转换同一episode

```python
for frame_idx in range(total_frames):
    try:
        process_frame(frame_idx)
    except DataQualityError:
        skipped_frames += 1
        continue  # ⚠️ 问题：破坏时序连续性
```

**问题**:
1. **时序对齐破坏**: observation[i] 和 action[i+offset] 错位
2. **机器学习不可用**: 跳帧导致状态转移不连续
3. **难以追溯**: LeRobot索引和原始数据的映射复杂

#### 修正后设计（✅ 正确）
**Episode级容错** - 任何单帧错误都跳过整个episode

```python
for frame_idx in range(total_frames):
    try:
        process_frame(frame_idx)
    except DataQualityError:
        # 升级为CriticalDataError
        raise CriticalDataError("跳过整个episode")  # ✅ 保证连续性
```

**原因**:
- 保持帧索引连续（0,1,2,3,...）
- 保证observation-action时序对齐
- LeRobot格式要求episode内数据完整

### 严格模式设计

#### 目的
在前N个episodes中快速发现配置错误

#### 机制
```python
if global_ep_idx < strict_episodes:  # 前3个episode
    is_strict = True
    
    # 遇到DataQualityError时
    if is_strict:
        raise ConfigError("可能是配置错误")  # 停止转换
    else:
        raise CriticalDataError("跳过episode")  # 继续转换
```

#### 参数
- `strict_episodes`: 严格模式的episode数量（默认3）
- `failure_threshold`: 失败率阈值（默认80%）
- `min_valid_frame_ratio`: 最小有效帧比例（已废弃，因为不支持跳帧）

---

## LeRobot格式兼容性

### 问题1: 跳过episode后索引是否连续？

**担忧**: 如果跳过某些episodes，LeRobot的文件编号会不连续吗？

**答案**: ✅ 完全不会有问题

#### LeRobot的索引管理

```python
# LeRobot内部逻辑
class LeRobotDataset:
    def __init__(self):
        self.episode_index = 0  # 内部计数器
    
    def add_frame(frame, task):
        frame['episode_index'] = self.episode_index
    
    def save_episode():
        # 保存episode
        self.episode_index += 1  # 只在保存时才+1
```

#### 实际结果

**原始数据**: 5个episodes (0,1,2,3,4)  
**跳过**: episode 1和3  

**LeRobot输出**:
```
meta/
├── episodes.jsonl          # 3行（只有成功的episodes）
│   {"episode_index": 0, ...}  # 原始episode 0
│   {"episode_index": 1, ...}  # 原始episode 2
│   {"episode_index": 2, ...}  # 原始episode 4
├── info.json
│   {"total_episodes": 3}  # 正确！
└── tasks.jsonl

videos/chunk-000/camera/
├── episode_000000.mp4      # 原始episode 0
├── episode_000001.mp4      # 原始episode 2
└── episode_000002.mp4      # 原始episode 4

data/chunk-000/
└── episode_data.parquet
    # episode_index: 0,1,2（连续！）
```

**关键点**:
- ✅ LeRobot只知道我们保存了3个episodes
- ✅ 所有索引连续（0,1,2）
- ✅ 所有文件一致
- ✅ 元数据正确

### 问题2: 如何追溯到原始数据？

**解决方案**: episode_source_mapping.json

```json
{
  "dataset_info": {...},
  "episodes": [
    {
      "lerobot_episode_index": 0,
      "original_task_episode_index": 0,
      "source_files": {...}
    },
    {
      "lerobot_episode_index": 1,
      "original_task_episode_index": 2,  // 跳过了1
      "source_files": {...}
    },
    {
      "lerobot_episode_index": 2,
      "original_task_episode_index": 4,  // 跳过了3
      "source_files": {...}
    }
  ]
}
```

**状态**: 
- 文档已完成 ✅
- 部分转换器已实现 ⚠️
- 需要验证是否自动生成 ⚠️

---

## 分布式系统问题

### 架构概述

```
[Server] ←→ [Client 0]
         ←→ [Client 1]
         ←→ [Client 2]
         ...
         ←→ [Client 7]
         
[Database]
  └── LeFormatConvertDB
      ├── dataset_uuid
      ├── convert_status: PENDING/PROCESSING/COMPLETED/FAILED
      └── error_message
```

### 数据库状态流转

```
PENDING → PROCESSING → COMPLETED/FAILED
  ↑           ↑              ↑
  |           |              |
入库      分配任务时      收到结果时
```

### 问题1: 异常处理链路

#### 层级1: 转换器层 (lerobot_format_converter.py)

```python
def convert():
    for episode in episodes:
        try:
            convert_episode(...)
        except CriticalDataError:
            # ✅ 捕获，跳过episode，继续转换
            logger.warning("跳过episode")
            continue
            
        except ConfigError:
            # ❌ 向上传播
            logger.error("配置错误")
            raise
```

#### 层级2: 客户端任务处理 (client.py)

```python
def _sync_process_task(task_content):
    try:
        converter = create_converter(...)
        for episode in converter.convert():  # ConfigError在这里抛出
            ...
        return {}  # 成功
        
    except Exception as e:
        # ❌ 捕获所有异常
        raise RuntimeError(f"convert failed") from e
```

#### 层级3: 任务客户端 (task_client.py)

```python
async def process_task(task_data):
    try:
        result = await _sync_process_task(task_data)
        return {"status": "TASK_SUCCESS"}
        
    except Exception:
        # ❌ 捕获所有异常
        return {
            "status": "TASK_FAILED",
            "error_msg": traceback
        }
```

#### 层级4: 服务器 (server.py)

```python
def handle_task_result(task_content, task_result):
    if task_result["status"] == "TASK_SUCCESS":
        convert_status = TaskStatus.COMPLETED  # ✅
    else:
        convert_status = TaskStatus.FAILED     # ❌
    
    # 更新数据库
    update_database(convert_status)
```

### 问题2: 各种异常的处理结果

| 异常类型 | 严格模式 | 非严格模式 | 数据库状态 | 影响 |
|---------|---------|-----------|-----------|------|
| **CriticalDataError** | 升级为ConfigError → FAILED | 跳过episode → COMPLETED | COMPLETED | ⚠️ 严格模式过严 |
| **ConfigError** | 向上抛出 → FAILED | - | FAILED | ❌ 整个任务失败 |
| **其他Exception** | 向上抛出 → FAILED | 向上抛出 → FAILED | FAILED | ✅ 合理 |

### 问题3: PROCESSING状态永久卡住的情况

**关键问题**: 服务器分配任务时立即设置PROCESSING，但客户端可能在返回结果前崩溃/断线

| 场景 | 原因 | 数据库状态 | 是否恢复 |
|------|------|-----------|----------|
| **客户端进程崩溃** | OOM/段错误 → 进程终止 | PROCESSING | ❌ 永久卡住 |
| **网络断开** | 客户端无法提交结果 | PROCESSING | ❌ 永久卡住 |
| **心跳超时** | 服务器认为掉线并断开连接 | PROCESSING | ❌ 永久卡住 |
| **Ctrl+C中断** | 用户手动终止客户端 | PROCESSING | ❌ 永久卡住 |
| **服务器重启** | 所有客户端连接断开 | PROCESSING | ❌ 永久卡住 |
| **机器断电/重启** | 所有进程终止 | PROCESSING | ❌ 永久卡住 |
| **转换时间过长** | 超过心跳超时时间 | PROCESSING | ❌ 永久卡住 |

**示例**:
```python
# 服务器 (server.py:267)
item = get_pending_task()
upsert_leformat_convert(
    ds_uuid=item.uuid,
    convert_status=TaskStatus.PROCESSING  # ⚠️ 立即设置！
)
send_task_to_client(item)  # 发送给客户端

# 如果客户端此时崩溃...
# → 数据库永远是PROCESSING状态
# → 没有机制自动重置或重试
```

### 问题4: Multi-Client的影响

**Multi-Client**: 启动多个独立进程，每个进程运行一个客户端

```python
# multi_client.py
for i in range(8):  # 启动8个客户端
    proc = multiprocessing.Process(target=run_client)
    proc.start()
```

**风险**:
- 如果某个客户端进程崩溃，它正在处理的任务会卡在PROCESSING
- 其他7个客户端继续正常工作，不受影响
- 没有机制检测和恢复卡住的任务

### 问题5: 严格模式在分布式环境下的矛盾

**矛盾**:
- **初衷**: 快速发现配置错误，避免浪费时间
- **问题**: 在分布式环境下，任务FAILED需要重新入库，非常麻烦
- **更大的问题**: 即使只有1个episode有问题，前面已转换的episodes也会丢失

**场景**:
```
100个episodes的数据集
Episode 0-1: ✅ 成功转换
Episode 2: ❌ 某帧读取失败
       → 严格模式 → ConfigError
       → client捕获 → TASK_FAILED
       → 数据库: FAILED
       → Episode 0-1的转换结果丢失 😫
       → 需要重新入库、重新分配 😫😫
```

---

## 待解决问题

### 🔴 高优先级

#### 1. 严格模式是否应该导致任务FAILED？

**选项A**: 保持现状
- 优点: 快速失败，节省时间
- 缺点: 分布式环境下需要重新入库

**选项B**: 严格模式只记录警告，不停止转换
- 优点: 不会导致任务失败
- 缺点: 可能浪费时间转换配置错误的数据集

**选项C**: 分离验证和转换
- 第一阶段: 严格验证（可选）
- 第二阶段: 实际转换（允许跳过）

#### 2. PROCESSING状态卡住问题

**需要**:
- 任务超时机制（24小时后自动重置？）
- 心跳/进度上报机制
- 手动重置工具
- 检测和报警机制

#### 3. 内存溢出问题

**现状**: 
- `frame_count_utils.py`已创建 ✅
- 使用ffprobe获取视频帧数（不加载到内存）✅
- 但视频转换器仍然加载全部视频到内存 ❌

**需要**:
- 重构视频转换器，实现延迟加载
- Buffer只存路径，按需读取帧
- 估算内存节省: 18GB → <2GB

### 🟡 中优先级

#### 4. 配置诊断工具

**需要**:
- 自动发现数据集schema
- 对比配置与实际数据
- 生成配置修正建议

#### 5. Episode Source Mapping

**需要验证**:
- 是否自动生成？
- 所有转换器是否实现？
- 查询工具是否可用？

### 🟢 低优先级

#### 6. 预检测脚本处理

**用户要求**: 不再使用`scripts/dataset_statistics/`中的预检测脚本

**建议**: 
- 移动到`scripts/dataset_statistics/archived/`
- 保留代码作为参考
- 用新的容错机制替代

---

## 已完成工作

### ✅ P0: 核心基础设施

1. **异常类体系** (`exceptions.py`)
   - ConfigError: 配置错误 → 停止转换
   - DataQualityError: 数据质量问题 → Episode级容错
   - CriticalDataError: 严重数据错误 → 跳过整个episode
   - FrameCountMismatchError: 帧数不匹配

2. **帧数工具** (`frame_count_utils.py`)
   - `get_video_frame_count()`: 使用ffprobe，快速，不占内存
   - `get_h5_frame_count()`: 读取H5 shape
   - `get_json_frame_count()`: 读取JSON长度
   - `get_mcap_frame_count()`: 读取MCAP消息数
   - `align_frame_counts()`: 统一对齐策略

3. **容错机制** (`lerobot_format_converter.py`)
   - Episode级容错逻辑
   - 严格模式（前N个episodes）
   - 失败率阈值检测
   - 详细转换报告

### ✅ P1: 测试和文档

4. **测试脚本** (`test_fault_tolerance.py`)
   - 支持测试模式和完整转换
   - 详细的结果报告和评估
   - 已通过智平方数据集测试（100%成功率）

5. **文档**
   - `CONVERTER_REFACTOR_GUIDE.md`: 重构指南
   - `EPISODE_LEVEL_FAULT_TOLERANCE.md`: Episode级容错设计
   - `FAULT_TOLERANCE_FRAME_INDEX_ANALYSIS.md`: 索引兼容性分析
   - `TESTING_FAULT_TOLERANCE.md`: 测试指南

### ✅ P2: 向后兼容

6. **工厂方法智能参数传递**
   - 使用`inspect.signature`检查子类参数
   - 只向支持容错的转换器传递新参数
   - 保证与旧转换器兼容

---

## 决策点

以下问题需要讨论和决策：

### 🎯 决策1: 严格模式的处理方式

**当前**: 抛出ConfigError → TASK_FAILED  
**问题**: 分布式环境下需要重新入库

**选项**:
- [ ] A. 保持现状（快速失败）
- [ ] B. 降级为警告（继续转换）
- [ ] C. 分离验证阶段
- [ ] D. 其他方案

### 🎯 决策2: PROCESSING卡住的处理

**问题**: 客户端崩溃导致任务永久卡在PROCESSING

**选项**:
- [ ] A. 添加任务超时机制
- [ ] B. 添加心跳/进度上报
- [ ] C. 手动重置工具
- [ ] D. 组合方案
- [ ] E. 暂不处理

### 🎯 决策3: 下一步工作优先级

**选项**:
- [ ] A. 解决严格模式问题
- [ ] B. 实施视频延迟加载
- [ ] C. 解决PROCESSING卡住问题
- [ ] D. 开发配置诊断工具
- [ ] E. 其他

---

## 附录

### 关键代码位置

- 容错机制: `src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py:692-954`
- 异常定义: `src/robocoin_dataset/format_converter/tolerobot/exceptions.py`
- 帧数工具: `src/robocoin_dataset/format_converter/tolerobot/frame_count_utils.py`
- 客户端: `src/robocoin_dataset/format_converter/tolerobot/client.py`
- 服务器: `src/robocoin_dataset/format_converter/tolerobot/server.py`
- 任务客户端: `src/robocoin_dataset/distribution_computation/task_client.py`
- Multi-Client: `scripts/format_converters/tolerobot/multi_client.py`

### 数据库相关

- 模型定义: `src/robocoin_dataset/database/models.py`
- 服务: `src/robocoin_dataset/database/services/leformat_converter.py`

---

**最后更新**: 2025-10-21  
**维护者**: Refactoring Team

