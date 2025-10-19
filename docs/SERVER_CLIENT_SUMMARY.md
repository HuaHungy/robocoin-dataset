# Server vs Convert2Lerobot 关系总结

## 🎯 一句话总结

**`convert2lerobot.py` 是单机直接运行工具，`server.py + client.py` 是分布式任务调度系统，但两者都调用相同的转换核心代码。**

---

## 📊 简单对比

| | convert2lerobot.py | server + client |
|---|---|---|
| **是什么** | 命令行工具 | 分布式系统 |
| **运行方式** | `python convert2lerobot.py --dataset-path ...` | Server 分发任务 → Client 执行 |
| **数据来源** | 命令行参数 | 数据库查询 |
| **适用场景** | 单个数据集、测试调试 | 批量转换、生产环境 |
| **依赖** | 无需数据库、无需服务器 | 需要数据库、WebSocket |
| **并行能力** | ❌ 串行 | ✅ 多客户端并行 |

---

## 🔧 核心代码是相同的！

```python
# 两者都调用同样的转换器
converter = LerobotFormatConverterFactory.create_converter(
    dataset_path=dataset_path,
    device_model=device_model,
    output_path=output_path,
    converter_config=converter_config,
    # ...
)

# 执行转换
for task, task_ep_idx, ep_idx in converter.convert():
    logger.info(f"Converted episode {ep_idx}")

# 保存映射文件 ✅ (两者都已支持)
converter.save_episode_source_mapping()
```

---

## 📋 工作流程对比

### convert2lerobot.py (单机模式)
```
用户运行命令
    ↓
读取命令行参数
    ↓
创建转换器
    ↓
执行转换
    ↓
保存映射文件 ✅
    ↓
完成
```

### server + client (分布式模式)
```
Server 启动 → 从数据库读取待转换任务
    ↓
Client 连接 → 请求任务
    ↓
Server → 分发任务内容（包含所有参数）
    ↓
Client → 创建转换器（和单机模式一样）
    ↓
Client → 执行转换（和单机模式一样）
    ↓
Client → 保存映射文件 ✅（和单机模式一样）
    ↓
Client → 返回结果
    ↓
Server → 更新数据库状态
```

---

## 💡 关键理解

1. **相同的转换核心**：
   - 无论哪种模式，都使用 `LerobotFormatConverter` 系列类
   - 转换逻辑完全一致
   - 输出格式完全相同
   - 映射文件生成逻辑相同 ✅

2. **不同的任务获取方式**：
   - `convert2lerobot.py`: 从命令行参数获取
   - `server + client`: 从数据库查询 + WebSocket 传输

3. **适用场景不同**：
   - 单机：适合开发、测试、单个数据集
   - 分布式：适合生产、批量、多数据集并行

---

## ✅ Episode Source Mapping 已同步

现在两种模式都支持生成 `episode_source_mapping.json`：

```python
# convert2lerobot.py (第 112-115 行) ✅
if not is_test:
    converter.save_episode_source_mapping()

# client.py (第 111-114 行) ✅
if not is_test:
    converter.save_episode_source_mapping()
```

---

## 🚀 快速选择指南

### 用 convert2lerobot.py 当你：
- ✅ 只需要转换一个数据集
- ✅ 正在开发/测试新功能
- ✅ 想要快速验证配置
- ✅ 不想启动服务器和数据库

### 用 server + client 当你：
- ✅ 需要批量转换几十上百个数据集
- ✅ 有多台机器可以并行处理
- ✅ 需要任务状态跟踪
- ✅ 需要自动重试失败任务
- ✅ 在生产环境中运行

---

## 📚 相关文档

- **详细对比**: `docs/SERVER_VS_CONVERT2LEROBOT.md`
- **映射功能**: `docs/episode_source_mapping_example.md`
- **实现总结**: `docs/EPISODE_SOURCE_MAPPING_COMPLETE.md`
