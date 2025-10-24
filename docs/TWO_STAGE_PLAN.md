# 两阶段转换Pipeline工作规划

## 📋 总体策略

根据用户要求：
1. **优先级**: 先处理最高优先级version
2. **顺序**: 阶段1（配置） → 阶段2（转换） → 其他version
3. **目标**: 快速完成几十万条episode的转换

---

## 🎯 阶段1: 配置问题解决（Configuration Phase）

**目标**: 确保所有配置文件正确、规范，数据质量问题被识别

### 1.1 最高优先级Device Version ⚡

#### 已完成 ✅
- [x] **Galaxea R1 Lite** (rosbag & h5_mp4_version)
  - ✅ Gripper单位确认（degree）并添加转换
  - ✅ 字段命名规范化
  - ⚠️ 待处理：Chassis position全0、Torso第4关节全0

- [x] **Agilex Cobot Decoupled Magic** (h5_mp4 & h5_mp4_new)
  - ✅ 配置确认
  - ⚠️ 数据质量问题记录（右臂可能无效，但不重要）

#### 待确认的最高优先级Device 🔍

需要确认哪些是"最高优先级version"：
- [ ] **Discover Robotics Aitbot MMK2** (73个数据集)
- [ ] **Yinhe** (5个数据集)
- [ ] **Realman RMC Aidal** (37个数据集)
- [ ] **Leju** (6个数据集)
- [ ] **Ruantong** (25个数据集)
- [ ] **Zhipingfang** (16个数据集)

### 1.2 配置验证工具运行 🔍

对每个最高优先级device：

1. **Schema Discovery & Validation**
   ```bash
   # 运行配置验证工具
   cd scripts/config_validation
   ./run_validation.sh --device-model <device_model> --num-samples 2
   ```

2. **检查项目**:
   - [ ] 字段维度匹配
   - [ ] 字段命名规范（参考`realman_rmc_aidal`）
   - [ ] 单位标注正确（`_rad`, `_m`, `_deg`等）
   - [ ] 数据质量问题识别（全0、常量、异常值）

3. **输出产物**:
   - 配置验证报告（每个device一份）
   - 数据质量问题清单
   - 建议的配置修正

### 1.3 配置文件修正 ✏️

根据验证报告，修正每个config文件：

**标准检查清单**:
- [ ] 字段命名：使用语义化名称（`joint_1_rad`而非`qpos_0`）
- [ ] 单位后缀：`_rad`, `_m`, `_deg`, `_m_s`, `_rad_s`等
- [ ] 单位转换：必要时添加`convert_func`（如`degree2rad`, `mm2m`）
- [ ] 数据范围：`range_from`和`range_to`正确
- [ ] 数据质量：标注已知问题字段（注释说明）

**修正流程**:
1. 阅读验证报告
2. 对比实际数据和配置
3. 修改配置文件
4. 添加注释说明
5. 重新验证

### 1.4 数据质量问题文档化 📄

为每个发现问题的device创建文档：

**模板**: `docs/<DEVICE>_DATA_ISSUES.md`

**内容**:
- 数据质量问题详细描述
- 影响范围（所有数据集？部分数据集？）
- 建议的处理方式（跳过？警告？修正？）
- 是否影响训练

---

## 🚀 阶段2: 正式转换问题解决（Conversion Phase）

**目标**: 实现稳定、高效、可追溯的大规模转换

### 2.1 Episode级容错机制 🛡️

#### 实现要求：
```python
# 在converter中实现episode级别跳过
try:
    convert_episode(ep_idx)
except CriticalDataError as e:
    # 数据质量问题 → 跳过此episode
    logger.warning(f"Skipping episode {ep_idx}: {e}")
    skipped_episodes.append(ep_idx)
    continue  # 继续下一个episode
except ConfigError as e:
    # 配置错误 → 停止转换
    raise
```

#### 关键点：
- [ ] 区分`ConfigError`（停止）和`CriticalDataError`（跳过）
- [ ] 跳过episode后，保持LeRobot格式连续性
- [ ] 记录所有跳过的episode
- [ ] 生成`skipped_episodes.json`

### 2.2 Episode Source Mapping 🗺️

#### Mapping文件1: `episode_source_mapping.json`

**作用**: 追溯LeRobot episode到原始数据

```json
{
  "0": {
    "original_episode_idx": 0,
    "original_episode_id": "episode_0",
    "source_dataset": "task_1"
  },
  "1": {
    "original_episode_idx": 2,  // 跳过了episode_1
    "original_episode_id": "episode_2",
    "source_dataset": "task_1"
  }
}
```

**实现位置**: `meta/episode_source_mapping.json`

#### Mapping文件2: `original_data_paths.json`（特定device）

**作用**: 记录原始文件的绝对路径

```json
{
  "0": {
    "h5_file": "/mnt/nas/data/task1/episode_0/data.hdf5",
    "videos": [
      "/mnt/nas/data/task1/episode_0/cam_high.mp4",
      "/mnt/nas/data/task1/episode_0/cam_left.mp4"
    ]
  }
}
```

**何时生成**:
- 在converter config中添加`generate_path_mapping: true`
- 只对需要的device生成

### 2.3 分布式系统异常处理 🔄

#### 数据库状态管理

**问题**: 客户端异常时，数据库状态可能卡在`PROCESSING`

**解决方案**:

1. **心跳机制**:
   ```python
   # 客户端定期更新心跳
   update_task_heartbeat(task_id, timestamp)
   
   # 服务端检测超时
   if task.last_heartbeat < now - TIMEOUT:
       task.status = FAILED
   ```

2. **任务超时自动重置**:
   ```python
   # 服务端定期检查
   for task in get_processing_tasks():
       if task.processing_time > MAX_TIME:
           task.status = FAILED
           task.error_message = "Timeout"
   ```

3. **客户端优雅退出**:
   ```python
   # 捕获所有异常，更新数据库
   try:
       convert()
   except Exception as e:
       db.update_status(FAILED, error=str(e))
       raise
   finally:
       db.close()
   ```

### 2.4 性能优化应用 ⚡

#### 已完成的优化：
- [x] H5+MP4: LazyVideoReader (内存减少96%)
- [x] H5+MP4: H5FileCache (速度提升10倍)
- [x] H5+MP4: Episode定位优化 (10-100倍加速)

#### 待应用：
- [ ] MP4+JSON: LazyVideoReader
- [ ] Leju Waibu: LazyVideoReader
- [ ] 其他converter: 根据需要应用

#### 性能监控：
- [ ] 创建性能监控工具
  - 记录每个episode转换时间
  - 记录内存峰值
  - 生成性能报告

### 2.5 测试转换流程 🧪

在正式大规模转换前：

1. **小规模测试**（每个device 2-5个episode）
   ```bash
   python scripts/gen_info.py --device <device> --is-test
   ```
   - 验证配置正确
   - 验证转换质量
   - 验证性能优化效果

2. **中规模测试**（每个device 50-100个episode）
   ```bash
   python scripts/gen_info.py --device <device> --max-episodes 100
   ```
   - 验证容错机制
   - 验证mapping文件生成
   - 验证数据库状态管理

3. **正式转换**
   ```bash
   # 服务端
   python scripts/server.py
   
   # 客户端（多台机器）
   python scripts/client.py --num-workers 8
   ```

---

## 📅 时间规划

### 阶段1（配置）- 预计1-2周

| 任务 | 时间 | 优先级 |
|------|------|--------|
| 确认最高优先级device列表 | 0.5天 | P0 |
| 运行配置验证工具（所有最高优先级） | 1-2天 | P0 |
| 修正配置文件 | 3-5天 | P0 |
| 文档化数据质量问题 | 1-2天 | P1 |
| 二次验证 | 1天 | P0 |

### 阶段2（转换）- 预计2-3周

| 任务 | 时间 | 优先级 |
|------|------|--------|
| 实现Episode级容错 | 2-3天 | P0 |
| 实现Mapping文件生成 | 1-2天 | P0 |
| 优化分布式异常处理 | 2-3天 | P0 |
| 性能优化应用 | 2-3天 | P1 |
| 小规模测试 | 1-2天 | P0 |
| 中规模测试 | 2-3天 | P0 |
| 正式转换（监控） | 1-2周 | P0 |

---

## 🎯 里程碑

### Milestone 1: 配置验证完成 ✅
- [ ] 所有最高优先级device配置验证通过
- [ ] 数据质量问题文档化
- [ ] 配置文件符合规范

### Milestone 2: 容错机制实现 🛡️
- [ ] Episode级跳过逻辑
- [ ] Mapping文件生成
- [ ] 小规模测试通过

### Milestone 3: 分布式稳定性 🔄
- [ ] 心跳机制
- [ ] 超时处理
- [ ] 中规模测试通过

### Milestone 4: 正式转换启动 🚀
- [ ] 性能优化应用
- [ ] 监控系统就绪
- [ ] 开始大规模转换

---

## 📊 成功标准

### 阶段1成功标准：
1. ✅ 所有最高优先级device配置验证报告生成
2. ✅ 所有配置文件字段命名规范化
3. ✅ 所有必要的单位转换已添加
4. ✅ 数据质量问题已识别并文档化

### 阶段2成功标准：
1. ✅ 转换成功率 > 95%（允许5%数据质量问题导致跳过）
2. ✅ 所有转换的episode可追溯到原始数据
3. ✅ 数据库状态准确（无卡住的任务）
4. ✅ 性能达标（内存<1GB，速度>10 episodes/分钟）

---

## 🔗 相关文档

- 配置验证工具: `scripts/config_validation/README.md`
- 性能优化总结: `docs/CONVERTER_OPT_PROGRESS.md`
- Galaxea配置修正: `docs/GALAXEA_GRIPPER_COMPARISON.md`
- H5+MP4数据问题: `docs/H5_MP4_DATA_ISSUES.md`

---

## ❓ 待确认问题

1. **最高优先级device列表**: 需要用户提供具体的device+version列表
2. **Chassis和Torso问题**: Galaxea的chassis position全0和torso第4关节全0是否需要处理
3. **转换目标数量**: 具体有多少episode需要转换（几十万条的准确数字）
4. **时间要求**: 期望多久完成转换

---

**📌 下一步立即行动**:
1. 用户确认最高优先级device列表
2. 运行配置验证工具批量分析
3. 根据报告修正配置文件

