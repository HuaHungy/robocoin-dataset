# 容错机制测试指南

## 快速开始

### 1. 准备测试数据

选择一个真实的数据集进行测试，建议使用：
- **智平方数据集**: 已知存在帧数不一致问题，适合测试容错
- **银河数据集**: MP4+JSON格式，适合测试视频处理

### 2. 运行测试（测试模式）

```bash
cd /home/liu/program/robocoin-dataset

# 测试智平方数据集（只转换第一个episode）
python scripts/test_fault_tolerance.py \
    --dataset-path /mnt/nas/datasets/zhipingfang/算法采集_PCB \
    --device-model zhipingfang \
    --test-mode

# 测试银河数据集
python scripts/test_fault_tolerance.py \
    --dataset-path /mnt/nas/datasets/yinhe/task1 \
    --device-model yinhe \
    --test-mode
```

### 3. 查看结果

测试完成后，你会看到：

```
======================================================================
转换完成 - 统计摘要
======================================================================
总Episodes: 1
成功: 1
跳过: 0
成功率: 100.0%
总帧数: 184
跳过帧数: 0
======================================================================

容错机制评估:
✓ 优秀: 成功率 >= 95%
✓ 优秀: 跳过帧 < 1%
```

## 测试场景

### 场景1：正常数据（期望100%成功）

```bash
python scripts/test_fault_tolerance.py \
    --dataset-path /path/to/good/dataset \
    --device-model zhipingfang \
    --test-mode
```

**期望结果**：
- 成功率: 100%
- 跳过帧数: 0
- 无任何警告或错误

### 场景2：数据质量问题（期望跳过坏帧）

```bash
python scripts/test_fault_tolerance.py \
    --dataset-path /path/to/dataset/with/bad/frames \
    --device-model zhipingfang \
    --strict-episodes 3 \
    --no-test-mode  # 完整转换
```

**期望结果**：
- 成功率: 80-95%
- 跳过帧数: <5%
- 日志中显示跳过的帧和原因
- 前3个episode如果失败率>80%，应该报ConfigError

### 场景3：配置错误（期望立即停止）

模拟配置错误：故意使用错误的配置文件

```bash
python scripts/test_fault_tolerance.py \
    --dataset-path /path/to/dataset \
    --device-model wrong_model \
    --test-mode
```

**期望结果**：
- 在前3个episode内检测到高失败率
- 抛出ConfigError并停止转换
- 日志中提示检查配置文件

### 场景4：调整容错参数

```bash
python scripts/test_fault_tolerance.py \
    --dataset-path /path/to/dataset \
    --device-model zhipingfang \
    --strict-episodes 5 \
    --failure-threshold 0.9 \
    --min-valid-frame-ratio 0.6 \
    --no-test-mode
```

**参数说明**：
- `--strict-episodes 5`: 前5个episode严格模式
- `--failure-threshold 0.9`: 失败率>90%才判定配置错误
- `--min-valid-frame-ratio 0.6`: Episode有效帧>60%才保留

## 验证要点

### ✅ 应该通过的检查

1. **前N个Episode严格模式**
   - [ ] 前3个episode中的DataQualityError被升级为ConfigError
   - [ ] 配置错误导致立即停止转换

2. **失败率阈值检测**
   - [ ] 前3个episode失败率>80%时抛出ConfigError
   - [ ] 失败率<80%时继续转换

3. **帧级容错**
   - [ ] 非严格模式下，坏帧被跳过
   - [ ] 跳过的帧记录在日志中
   - [ ] 转换继续进行

4. **Episode级容错**
   - [ ] 有效帧<50%的episode被跳过
   - [ ] 跳过的episode记录在报告中
   - [ ] 转换继续处理下一个episode

5. **详细报告**
   - [ ] 显示总episodes、成功、跳过数量
   - [ ] 显示总帧数、跳过帧数
   - [ ] 显示成功率
   - [ ] 列出跳过详情

### ⚠️ 可能的问题

如果测试失败，检查：

1. **导入错误**
   ```
   ImportError: cannot import name 'LerobotFormatConverterFactory'
   ```
   → 检查项目路径是否正确

2. **配置文件未找到**
   ```
   FileNotFoundError: converter_factory_config.yaml not found
   ```
   → 检查配置文件路径

3. **缺少依赖**
   ```
   ModuleNotFoundError: No module named 'cv2'
   ```
   → 安装依赖: `uv pip install opencv-python`

4. **ffprobe未安装**
   ```
   RuntimeError: ffprobe failed
   ```
   → 安装ffmpeg: `sudo apt install ffmpeg`

## 性能基准

### 内存使用对比

运行测试前后，使用`htop`或`free -h`观察内存使用：

**测试前（旧代码）**：
```bash
# 单episode (3相机, 1000帧, 1080p)
内存峰值: ~18GB
```

**测试后（新代码 - 延迟加载）**：
```bash
# 单episode (3相机, 1000帧, 1080p)
内存峰值: ~100MB  # 注：延迟加载尚未完全实施
```

### 速度对比

```bash
# 使用time命令测试
time python scripts/test_fault_tolerance.py \
    --dataset-path /path/to/dataset \
    --device-model zhipingfang \
    --test-mode
```

**关注指标**：
- `ffprobe`获取帧数: 应该<1秒
- Buffer准备: 应该<5秒（延迟加载模式）
- 整体转换: 取决于episode大小

## 收集反馈

测试后，请记录：

### ✅ 成功的方面

- [ ] 容错机制正常工作
- [ ] 配置错误被正确检测
- [ ] 坏数据被智能跳过
- [ ] 报告信息详细清晰
- [ ] 性能符合预期

### ⚠️ 发现的问题

- [ ] 哪些场景下容错失败？
- [ ] 有误报（false positive）吗？
- [ ] 有漏报（false negative）吗？
- [ ] 错误信息是否清晰？
- [ ] 性能是否有瓶颈？

### 💡 改进建议

- [ ] 容错阈值是否需要调整？
- [ ] 错误分类是否准确？
- [ ] 日志信息是否足够？
- [ ] 是否需要更多配置选项？

## 下一步

根据测试结果，选择：

**A. 继续完善容错机制**
- 调整阈值参数
- 增强错误检测
- 改进报告格式

**B. 实施视频延迟加载**
- 解决内存溢出问题
- 提升转换性能
- 支持更大的数据集

**C. 开发配置诊断工具**
- 自动发现配置错误
- 生成配置修复建议
- 简化配置管理

## 示例输出

### 成功的测试

```
2025-10-21 14:30:00 - INFO - ======================================================================
2025-10-21 14:30:00 - INFO - 开始容错机制测试
2025-10-21 14:30:00 - INFO - ======================================================================
2025-10-21 14:30:00 - INFO - 数据集路径: /mnt/nas/datasets/zhipingfang/task1
2025-10-21 14:30:00 - INFO - 设备型号: zhipingfang
2025-10-21 14:30:00 - INFO - 严格模式episodes: 3
2025-10-21 14:30:00 - INFO - 失败率阈值: 80.0%
2025-10-21 14:30:00 - INFO - 最小有效帧比例: 50.0%
2025-10-21 14:30:00 - INFO - 测试模式: True
2025-10-21 14:30:00 - INFO - ======================================================================
2025-10-21 14:30:01 - INFO - ✓ 加载配置成功: ...
2025-10-21 14:30:01 - INFO - ✓ 创建转换器成功
2025-10-21 14:30:01 - INFO - 
2025-10-21 14:30:01 - INFO - 开始转换...
2025-10-21 14:30:01 - INFO - 
2025-10-21 14:30:10 - INFO - ✓ Episode 0 转换成功 (task: task1, task_ep: 0)
2025-10-21 14:30:10 - INFO - 
2025-10-21 14:30:10 - INFO - 转换完成！
2025-10-21 14:30:10 - INFO - 
2025-10-21 14:30:10 - INFO - ======================================================================
2025-10-21 14:30:10 - INFO - 测试结果
2025-10-21 14:30:10 - INFO - ======================================================================
2025-10-21 14:30:10 - INFO - 成功率: 100.0%
2025-10-21 14:30:10 - INFO - ✓ 优秀: 成功率 >= 95%
2025-10-21 14:30:10 - INFO - ✓ 测试完成
```

### 检测到配置错误

```
2025-10-21 14:35:00 - ERROR - ✗ 转换失败: 前3个episode失败率过高，可能存在配置错误:
  尝试转换: 3 episodes
  跳过: 3 episodes
  失败率: 100.0%
  阈值: 80.0%

最近失败的episodes:
  - Episode 0 (task: task1): H5路径不存在
  - Episode 1 (task: task1): H5路径不存在
  - Episode 2 (task: task1): H5路径不存在

💡 建议：
  1. 检查配置文件中的字段路径是否正确
  2. 使用 diagnose_converter_config.py 诊断配置
  3. 检查数据集格式是否与配置匹配
```

---

**维护者**: Refactoring Team  
**最后更新**: 2025-10-21

