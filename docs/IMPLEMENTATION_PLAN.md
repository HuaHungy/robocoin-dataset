# 实施计划 - 20-30万Episodes转换

**日期**: 2025-10-21  
**目标**: 10天内完成20-30万episodes转换，零报错返工  
**状态**: 规划完成，待执行

---

## 📊 数据集概况

### 基本信息
- **总数据集**: 500个数据集（数据库中的条目）
- **总Episodes**: 20-30万
- **数据量**: 几百TB
- **存储位置**: `/mnt/nas/synnas/`（多路径）
- **转换资源**: 4台机器（内存待确认）

### 优先处理的Device Models
按优先级排序：
1. **discover_robotics_aitbot_mmk2** (多个版本)
2. **yinhe**
3. **realman_rmc_aidal** (default + mcap版本)
4. **agilex** (cobot系列)
5. **leju** (leju_robot + leju_waibu)
6. **ruantong** (多个版本) ⚠️ 需要`save_original_data_paths`
7. **zhipingfang** (多个arm配置版本)
8. **galaxea** (r1_lite系列)

---

## ⏱️ 性能目标与计算

### 时间分配
- **总时间**: 10天
- **准备阶段**: 5天（Schema Discovery + 配置修复 + 性能优化）
- **转换阶段**: 5天（实际转换）

### 转换速度要求
```
假设: 30万episodes / 5天转换 / 4台机器 = 15,000 episodes/天/机器

每台机器配置:
- 8个Clients并行 = 1,875 episodes/天/client
- 24小时运行 = 78 episodes/小时/client
- 约 46秒/episode/client

🎯 目标: 优化到 30-60秒/episode
```

### 性能优化关键指标
| 优化项 | 当前预估 | 目标 | 提升 |
|--------|---------|------|------|
| 视频读取 | 20-30秒 | 3-5秒 | 6-10x |
| H5文件I/O | 5-10秒 | 2-3秒 | 2-3x |
| 数据写入 | 5秒 | 3秒 | 1.5x |
| **单episode总时间** | **~40秒** | **~10秒** | **4x** |

**实际估算（优化后）**:
- 30万episodes × 10秒 = 3,000,000秒 = 833小时
- 4台机器 × 8 clients = 32并行
- 833小时 / 32 = **26小时 ≈ 1.1天** ✅

**加上余量（数据质量问题、重试等）**: 3-5天 ✅ 符合目标

---

## 🎯 核心策略

### 1. 零报错返工策略
- ✅ **Schema Discovery全覆盖**: 检查所有优先device_model的所有版本
- ✅ **配置文件100%修复**: 不允许有配置错误进入转换阶段
- ✅ **全程容错模式**: 遇到数据问题自动跳过episode
- ✅ **详细Mapping记录**: 所有跳过的episodes都记录原因

### 2. 性能优化优先
- 🔥 **视频延迟加载**: 必须实施（最大瓶颈）
- 🔥 **H5文件句柄缓存**: 必须实施（简单高效）
- 🔥 **ffprobe帧数获取**: 已完成 ✅
- 💡 **监控工具**: 实时追踪转换速度和问题

### 3. 优先级管理
- **Phase 1**: 优先转换mmk2, yinhe, realman（数量最多或最重要）
- **Phase 2**: 转换agilex, leju
- **Phase 3**: 转换ruantong（需要额外的原始路径mapping）
- **Phase 4**: 转换zhipingfang, galaxea

---

## 📅 详细实施计划（14天）

### Week 1: 准备阶段（Day 1-7）

#### Day 1-2: Schema Discovery实现
- [ ] 实现H5 schema发现
- [ ] 实现JSON schema发现
- [ ] 实现MCAP schema发现
- [ ] 实现MMK2 BSON schema发现
- [ ] 实现video metadata提取

**输出**: 
- `scripts/dataset_schema_discovery/` 工具集
- 支持从数据库批量抽取数据集进行schema分析

#### Day 3-4: Schema Discovery执行
- [ ] 从数据库查询所有优先device_model的数据集
- [ ] 按device_model分组
- [ ] 每个device_model抽样5-10个数据集进行schema分析
- [ ] 生成schema报告

**输出**:
- `outputs/discovered_schemas/<device_model>_<version>_schema.yaml`
- `outputs/schema_analysis_report.md`（汇总报告）

#### Day 5: 配置文件诊断
- [ ] 实现配置诊断工具
- [ ] 对比discovered_schema vs converter_config
- [ ] 生成修复建议（缺失字段、冗余字段、命名不规范）
- [ ] 标记device_model_annotation错误

**输出**:
- `outputs/config_diagnosis/<device_model>_diagnosis.yaml`
- 优先级排序的修复任务列表

#### Day 6: 配置文件修复
- [ ] 修复top优先级的配置文件
- [ ] 重点：mmk2, yinhe, realman, agilex, leju
- [ ] 为ruantong的配置文件添加 `save_original_data_paths: true`
- [ ] 验证修复结果

**输出**:
- 更新后的converter_config文件
- 修复验证报告

#### Day 7: 性能优化实施
- [ ] 实现视频延迟加载（MP4+JSON, H5+MP4, Leju Waibu converters）
- [ ] 实现H5文件句柄缓存
- [ ] 创建性能监控脚本
- [ ] 小规模测试验证优化效果

**输出**:
- 优化后的转换器代码
- 性能测试报告（优化前后对比）

---

### Week 2: 转换阶段（Day 8-14）

#### Day 8: 小规模测试
- [ ] 选择代表性数据集（每个优先device_model各1-2个）
- [ ] 填充Test数据库
- [ ] 启动Server（Test模式）
- [ ] 启动4台机器 × 8 clients = 32并行
- [ ] 监控转换速度和问题

**成功标准**:
- 转换速度 < 60秒/episode
- 跳过率 < 5%
- 无配置错误

#### Day 9: 问题修复与调优
- [ ] 分析Day 8的失败案例
- [ ] 修复发现的配置问题
- [ ] 调整Client数量（根据机器资源）
- [ ] 优化慢速转换器

#### Day 10-12: Phase 1 大规模转换
- [ ] 转换mmk2, yinhe, realman数据集
- [ ] 实时监控进度
- [ ] 处理异常情况

#### Day 13: Phase 2-3 转换
- [ ] 转换agilex, leju数据集
- [ ] 转换ruantong数据集（生成原始路径mapping）

#### Day 14: Phase 4 + 收尾
- [ ] 转换zhipingfang, galaxea数据集
- [ ] 验证转换结果
- [ ] 生成最终报告

---

## 🔧 关键技术实现

### 1. 简化的容错机制（无严格模式）

```python
class LerobotFormatConverter:
    def __init__(self, ...):
        # 删除 strict_episodes, failure_threshold
        self._conversion_stats = {
            'total_episodes': 0,
            'successful_episodes': 0,
            'skipped_episodes': 0,
            'skip_details': []
        }
    
    def convert(self, is_test: bool = False):
        """全程容错模式"""
        for episode in all_episodes:
            try:
                convert_episode(episode)
                self._conversion_stats['successful_episodes'] += 1
                
            except CriticalDataError as e:
                # 数据问题 → 跳过episode
                self._conversion_stats['skipped_episodes'] += 1
                self._conversion_stats['skip_details'].append({
                    'episode': episode,
                    'reason': str(e)
                })
                logger.warning(f"跳过episode {episode}: {e}")
                continue
                
            except ConfigError as e:
                # 不应该出现！配置修复阶段应该已解决
                logger.error(f"配置错误: {e}")
                raise  # 停止转换，需要人工介入
```

### 2. Mapping文件生成

```python
# episode_source_mapping.json - 所有转换器必须生成
{
  "dataset_info": {...},
  "episodes": [
    {
      "lerobot_episode_index": 0,
      "original_task": "pick_and_place",
      "original_task_episode_index": 0,
      "original_source_name": "episode_0.h5",  # 新增字段
      "frames_count": 107
    }
  ],
  "skipped_episodes_details": [...]
}

# original_data_paths.json - 仅ruantong生成
# 在converter_config_ruantong*.yaml中添加:
# save_original_data_paths: true
```

### 3. 性能监控

```python
# scripts/monitoring/conversion_monitor.py
def monitor_conversion():
    while True:
        stats = query_database_stats()
        
        print(f"""
        转换进度:
        - 总任务: {stats.total}
        - 已完成: {stats.completed}
        - 进行中: {stats.processing}
        - 失败: {stats.failed}
        - 完成率: {stats.completed/stats.total*100:.1f}%
        
        性能指标:
        - 平均速度: {stats.avg_speed} episodes/小时
        - 预计剩余时间: {stats.eta}
        - 当前最慢Client: {stats.slowest_client}
        """)
        
        time.sleep(60)
```

---

## 📋 检查清单

### 开工前必须完成
- [ ] Schema Discovery工具完成并测试
- [ ] 所有优先device_model的配置文件已修复
- [ ] 性能优化已实施并验证
- [ ] ruantong的converter_config已添加 `save_original_data_paths: true`
- [ ] 监控工具已就绪
- [ ] 4台机器环境已准备（Python环境、依赖、权限）

### 转换阶段检查
- [ ] 每天监控转换速度（应 > 2万episodes/天）
- [ ] 每天检查失败任务（应 < 1%）
- [ ] 每天验证跳过率（应 < 5%）
- [ ] 实时响应异常情况

---

## 🚨 风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|----------|
| 配置文件修复不完整 | 中 | 高 | Schema Discovery全覆盖，人工复核 |
| 性能优化不达标 | 低 | 高 | 提前测试验证，准备Plan B（增加机器） |
| 机器资源不足（内存） | 中 | 中 | 视频延迟加载必须实施，监控内存使用 |
| 数据质量问题超预期 | 中 | 低 | 容错机制自动处理，记录到mapping |
| 网络/存储故障 | 低 | 中 | 多台机器分散风险，数据库记录进度 |

---

## 📊 成功指标

### 转换质量
- ✅ 配置错误: 0
- ✅ 转换失败率: < 1%
- ✅ Episode跳过率: < 5%
- ✅ Mapping文件完整性: 100%

### 转换速度
- ✅ 总耗时: ≤ 10天
- ✅ 平均速度: ≥ 2万episodes/天
- ✅ 单episode时间: < 60秒

### 数据完整性
- ✅ 所有成功转换的episodes都有完整数据
- ✅ 所有跳过的episodes都有记录和原因
- ✅ ruantong的所有episodes都有原始路径mapping

---

**下一步**: 实施Schema Discovery工具（Day 1-2）

