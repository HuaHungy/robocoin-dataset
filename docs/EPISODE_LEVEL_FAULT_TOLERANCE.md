# Episode级容错机制设计文档

**创建日期**: 2025-10-21  
**设计原则**: 保持时序数据完整性

## 核心设计决策

### ✅ 我们做什么

**跳过整个episode**

- 如果episode中任何一帧出现问题，跳过整个episode
- 确保转换后的数据集中每个episode的帧索引都是连续的（0, 1, 2, 3, ...）
- 保证observation-action的时序对齐关系

### ❌ 我们不做什么

**不跳过单帧**

- 绝不允许跳过单个帧并继续转换同一episode的其他帧
- 避免帧索引不连续（如：0, 1, 3, 4, 6, ...）
- 避免时序对齐破坏

## 为什么不能跳过单帧？

### 问题1：时序对齐破坏

```python
# 配置中有 timeline_offset = 1
# 表示 action[t] 对应于 observation[t+1]

# 原始数据（10帧）
frame_idx:     0    1    2    3    4    5    6    7    8    9
observation:   O0   O1   O2   O3   O4   O5   O6   O7   O8   O9
action:        A0   A1   A2   A3   A4   A5   A6   A7   A8   A9
对应关系:      O0→A1, O1→A2, O2→A3, ...

# 如果跳过第2帧（❌ 错误做法）
LeRobot索引:   0    1    2    3    4    5    6    7    8
observation:   O0   O1   O3   O4   O5   O6   O7   O8   O9
action:        A0   A1   A3   A4   A5   A6   A7   A8   A9
对应关系:      O0→A1 ✓, O1→A3 ✗, O3→A4 ✗, ...
              # 从第2帧开始，所有对应关系都错了！
```

### 问题2：机器学习训练问题

- **连续性依赖**：许多策略学习算法假设时间步是连续的
- **状态转移**：跳帧会导致状态转移不连续（s[t] → s[t+2]，缺少s[t+1]）
- **轨迹完整性**：机器人演示轨迹必须是完整的，中间缺帧无法学习正确的行为

### 问题3：数据追溯困难

```python
# 如果需要追溯LeRobot中的某个episode到原始数据
lerobot_frame_2 对应原始哪一帧？

# 连续索引（✓）
lerobot_idx: 0, 1, 2, 3, 4
original_idx: 0, 1, 2, 3, 4  # 一一对应

# 跳过单帧（✗）
lerobot_idx: 0, 1, 2, 3, 4
original_idx: 0, 1, 3, 4, 5  # 需要额外的映射表，容易出错
```

## 实现机制

### 严格模式（前N个episode）

```python
# 前3个episode（可配置）
for frame_idx in range(total_frames):
    try:
        lerobot_data = self._get_lerobot_datas(...)
        dataset.add_frame(lerobot_data)
    except DataQualityError as e:
        # 升级为ConfigError，立即停止整个转换
        raise ConfigError(
            f"严格模式下检测到数据问题:\n"
            f"可能是配置错误而非数据问题"
        )
```

**目的**：
- 快速发现配置错误（如字段路径写错）
- 避免错误配置导致整个数据集转换失败

### 非严格模式（后续episode）

```python
for frame_idx in range(total_frames):
    try:
        lerobot_data = self._get_lerobot_datas(...)
        dataset.add_frame(lerobot_data)
    except DataQualityError as e:
        # 升级为CriticalDataError，跳过整个episode
        raise CriticalDataError(
            f"Episode数据质量问题，跳过整个episode\n"
            f"为保持时序连续性，不能跳过单帧"
        )
```

**目的**：
- 容忍个别episode的数据损坏
- 保证成功转换的episode数据质量

## 配置参数

```python
LerobotFormatConverter(
    strict_episodes=3,           # 前3个episode严格模式
    failure_threshold=0.8,       # 前3个episode失败率>80%判定为配置错误
    min_valid_frame_ratio=0.5,   # 废弃，因为不支持跳过单帧，此参数不再使用
)
```

## 转换结果

### 成功的Episode

```yaml
Episode 0:
  frames: [0, 1, 2, 3, ..., 99]  # 连续索引
  status: ✓ 成功
  observation-action对齐: ✓ 正确
```

### 跳过的Episode

```yaml
Episode 5:
  frames: []  # 完全不写入
  status: ✗ 跳过
  reason: "第42帧视频文件损坏"
  impact: 整个episode被跳过
```

### 最终数据集

```python
# 原始数据：100个episodes
# 跳过了5个有问题的episodes
# LeRobot数据集：95个episodes（索引0-94）

每个episode内的帧索引都是连续的：
Episode 0: 帧0-120
Episode 1: 帧0-98
...
Episode 94: 帧0-150

# 每个episode都是完整的、可用的
```

## 转换报告

```python
{
    "total_episodes_attempted": 100,
    "successful_episodes": 95,
    "skipped_episodes": 5,
    "success_rate": 0.95,
    "total_frames_converted": 10450,
    "total_frames_skipped": 0,  # 始终为0，因为不跳过单帧
    "skip_details": [
        {
            "episode": 5,
            "task": "pick_place",
            "reason": "视频帧42损坏",
            "skipped_entire_episode": True
        },
        ...
    ]
}
```

## 与旧代码的区别

### 旧方式（❌ 可能导致问题）

```python
# 某些早期实现可能尝试跳过单帧
skipped_frames = []
for frame_idx in range(total_frames):
    try:
        process_frame(frame_idx)
    except Exception:
        skipped_frames.append(frame_idx)  # 跳过单帧
        continue  # 继续处理下一帧

# 结果：帧索引不连续，时序对齐错误
```

### 新方式（✓ 保证数据完整性）

```python
# Episode级容错
all_frames_ok = True
for frame_idx in range(total_frames):
    try:
        process_frame(frame_idx)
    except DataQualityError:
        # 任何一帧失败，整个episode失败
        raise CriticalDataError("跳过整个episode")

# 结果：要么全转，要么全跳，保证连续性
```

## 常见问题

### Q1: 如果只有最后一帧损坏，前面99帧都正常，是不是很浪费？

**A**: 是的，但这是保证数据质量的必要代价。考虑：
- 机器学习需要完整的轨迹，缺少最后一帧可能导致学习错误的终止策略
- 如果前99帧都正常，最后一帧损坏的概率其实很低
- 严格模式可以快速发现系统性问题

### Q2: 能否在配置中提供选项，让用户选择是否允许跳帧？

**A**: 不建议。这会导致：
- 数据集质量不一致
- 难以追溯和调试
- 容易产生"看起来正常但实际有问题"的数据

如果确实需要，应该在**数据预处理阶段**手动筛选和修复，而不是在转换时自动跳过。

### Q3: 如何降低episode跳过率？

**方法**：
1. **提前验证**：使用 `frame_count_utils.py` 验证帧数一致性
2. **修复数据**：在转换前修复损坏的原始数据
3. **改进配置**：使用配置诊断工具确保配置正确
4. **监控日志**：查看跳过详情，找出问题模式

## 未来可能的改进

### 1. Episode预检测（可选）

```python
def _validate_episode(self, task_path, ep_idx) -> bool:
    """在转换前快速检查episode是否完整
    
    Returns:
        True: episode可以转换
        False: episode有问题，应该跳过
    """
    # 快速检查（不加载全部数据）
    - 文件是否存在
    - 帧数是否对齐
    - 关键字段是否可访问
```

### 2. Episode修复工具（未实现）

```python
# 尝试修复轻微的数据问题
def try_repair_episode(episode_data):
    - 插值缺失的帧
    - 修复元数据错误
    - 重新对齐时间戳
```

但这些都应该是**可选的、显式的**，而不是在转换时自动进行。

## 总结

**核心原则**：宁可少转一些episode，也要保证每个转换的episode都是完整、正确、可用的。

**实现策略**：
1. 严格模式检测配置错误
2. 非严格模式跳过问题episode
3. 绝不跳过单帧
4. 详细的转换报告

**受益**：
- 数据质量高
- 训练稳定
- 易于追溯
- 避免隐藏的错误

---

**维护者**: Refactoring Team  
**最后更新**: 2025-10-21  
**状态**: 已实施并测试

