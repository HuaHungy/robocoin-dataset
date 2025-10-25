# Schema Discovery 工具实施完成报告

**日期**: 2025-10-21  
**状态**: ✅ 工具开发完成，待实际数据集测试

---

## 📦 已交付内容

### 核心工具模块（9个）

所有工具位于 `scripts/dataset_schema_discovery/` 目录：

1. **`h5_schema_discoverer.py`** - H5/HDF5文件Schema发现器
   - 递归解析H5文件结构
   - 提取数据类型、形状、统计信息
   - 支持多episode一致性检查

2. **`json_schema_discoverer.py`** - JSON文件Schema发现器
   - 递归解析JSON结构
   - 检测字段类型和嵌套关系
   - 支持批量文件分析

3. **`mcap_schema_discoverer.py`** - MCAP文件Schema发现器
   - 解析ROS2 MCAP格式
   - 提取topics和消息类型
   - 统计消息数量

4. **`mmk2_schema_discoverer.py`** - MMK2 BSON文件Schema发现器
   - 解析BSON格式数据
   - 提取文档结构
   - 支持多记录分析

5. **`video_metadata_extractor.py`** - 视频元数据提取器
   - 使用ffprobe提取元数据（优先）
   - OpenCV作为备用方案
   - 按摄像头分组分析
   - 提取分辨率、帧率、编码格式、帧数

6. **`dataset_schema_discoverer.py`** - 统一数据集Schema发现器
   - 自动检测数据格式
   - 集成所有单独的发现器
   - 读取device_model_annotation.yaml
   - 生成完整的schema JSON

7. **`database_query_tool.py`** - 数据库查询工具
   - 查询device_model对应的数据集
   - 支持采样策略（first/random/recent）
   - 统计device_model分布
   - 获取优先级models信息

8. **`schema_config_comparator.py`** - Schema vs Config对比工具
   - 对比discovered schema与converter config
   - 诊断配置问题（缺失字段、多余字段、类型不匹配）
   - 生成修复建议
   - 严重程度分类（ok/warning/error）

9. **`batch_schema_discovery.py`** - 批量Schema Discovery主程序
   - 从数据库批量查询优先级device_model
   - 并行分析多个数据集
   - 生成汇总报告
   - 保存所有schema和诊断结果

### 辅助文件（3个）

10. **`README.md`** - 完整使用文档
    - 快速开始指南
    - 工具模块说明
    - 输出格式说明
    - 典型工作流程
    - 故障排除

11. **`run_batch_discovery.sh`** - 快速启动脚本
    - 自动设置路径
    - 一键运行批量分析
    - 输出日志和结果

12. **`test_schema_tools.py`** - 工具测试脚本
    - 模块导入测试
    - 依赖项检查
    - 基本功能验证

---

## 🎯 功能特性

### 1. 全格式支持
- ✅ H5/HDF5
- ✅ JSON
- ✅ MCAP (ROS2)
- ✅ BSON (MMK2)
- ✅ 视频 (MP4/AVI/MOV)
- ⚠️  Rosbag (可通过rosbags库扩展)

### 2. 智能诊断
- **配置错误检测**: 字段缺失、多余、路径错误
- **数据一致性检查**: episode间schema差异
- **相机配置验证**: 视频数据与config匹配
- **修复建议生成**: 自动提供修复方案

### 3. 批量处理
- **数据库集成**: 从数据库批量查询数据集
- **采样策略**: 灵活的数据集和episode采样
- **并行分析**: 支持多数据集并行处理
- **进度追踪**: 详细的执行日志

### 4. 详细报告
- **Schema JSON**: 完整的数据结构描述
- **Diagnosis JSON**: 详细的诊断结果
- **Overall Report**: 总体分析摘要
- **Execution Log**: 执行过程日志

---

## 📋 下一步操作

### 阶段1: 环境准备（1小时）

#### 1.1 确认依赖安装

```bash
cd /home/liu/program/robocoin-dataset

# 检查当前环境
python --version
which python

# 如果使用虚拟环境
source .venv/bin/activate  # 或使用conda activate

# 安装项目依赖（如果未安装）
pip install -e .
# 或使用uv
uv pip install -e .

# 验证关键依赖
python -c "import h5py; import yaml; import sqlalchemy; print('✓ 核心依赖已安装')"

# 可选依赖（用于特定格式）
pip install mcap pymongo  # MCAP和BSON支持
```

#### 1.2 配置数据库路径

编辑 `scripts/dataset_schema_discovery/run_batch_discovery.sh`:

```bash
# 修改这行为实际的数据库路径
DATABASE_PATH="/mnt/nas/synnas/database/robocoin.db"
```

#### 1.3 运行测试

```bash
cd scripts/dataset_schema_discovery
python test_schema_tools.py
```

**预期输出**:
```
✅ 所有测试通过！工具已准备就绪。
```

---

### 阶段2: 小规模测试（2小时）

#### 2.1 单个数据集测试

选择一个已知的数据集进行测试：

```bash
# 示例：分析一个zhipingfang数据集
python dataset_schema_discoverer.py \
    /mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/算法采集_PCB \
    --device-model zhipingfang \
    --num-episodes 3 \
    --output test_schema.json \
    --verbose
```

**检查**:
- `test_schema.json` 是否生成
- 是否正确检测到H5和视频文件
- schema结构是否合理

#### 2.2 Schema vs Config对比测试

```bash
python schema_config_comparator.py \
    test_schema.json \
    ../format_converters/tolerobot/configs/converter_config_zhipingfang_dual_arm_no_pose.yaml \
    --output test_diagnosis.json
```

**检查**:
- 是否识别出配置问题
- 建议是否合理

---

### 阶段3: 批量分析（1-2天）

#### 3.1 运行批量Schema Discovery

```bash
cd scripts/dataset_schema_discovery
./run_batch_discovery.sh 5 5
```

参数说明:
- 第一个`5`: 每个device_model采样5个数据集
- 第二个`5`: 每个数据集采样5个episodes

#### 3.2 监控进度

打开另一个终端：

```bash
# 查看实时日志
tail -f outputs/schema_discovery_*/execution.log

# 统计已完成的schema文件
watch -n 10 'ls outputs/schema_discovery_*/schemas/ | wc -l'
```

#### 3.3 预期运行时间

假设每个device_model 5个数据集，每个数据集5个episodes:

- **MMK2**: 5数据集 × 5episodes × 3秒 ≈ 75秒
- **Yinhe**: 类似
- **Realman**: 类似
- **Agilex**: 类似
- **Leju**: 类似
- **Ruantong**: 类似
- **Zhipingfang**: 类似
- **Galaxea**: 类似

**总计**: 约 10分钟（8个models × 75秒）

如果某些数据集路径不存在或读取失败，会自动跳过。

---

### 阶段4: 分析结果（半天）

#### 4.1 查看总体报告

```bash
cat outputs/schema_discovery_*/overall_report.json | jq '.summary'
```

**关键指标**:
- `total_models_analyzed`: 成功分析的device_model数量
- `total_datasets_analyzed`: 成功分析的数据集数量
- `total_errors`: 发现的配置错误总数
- `total_warnings`: 发现的警告总数

#### 4.2 分析每个Device Model

```bash
# 查看MMK2的诊断
ls outputs/schema_discovery_*/diagnoses/discover_robotics_aitbot_mmk2_*

# 统计每个model的错误数
for model in mmk2 yinhe realman agilex leju ruantong zhipingfang galaxea; do
    echo "=== $model ==="
    grep -h '"severity": "error"' outputs/schema_discovery_*/diagnoses/${model}_* 2>/dev/null | wc -l
done
```

#### 4.3 识别常见问题

```bash
# 提取所有issues的category
jq -r '.issues[]? | .category' outputs/schema_discovery_*/diagnoses/*.json | sort | uniq -c | sort -rn

# 查看具体的缺失字段
jq -r '.issues[]? | select(.category=="observation_state") | .message' \
    outputs/schema_discovery_*/diagnoses/*.json
```

#### 4.4 生成修复任务列表

基于诊断结果，创建配置文件修复的优先级列表：

1. **P0 - 阻塞性错误**: 字段完全不存在，会导致转换100%失败
2. **P1 - 部分影响**: 字段在部分数据集中缺失
3. **P2 - 警告**: 未配置的可选字段

---

## 🔧 配置修复流程

### 方法1: 手动修复（推荐用于第一批）

对于每个发现的配置问题：

1. **查看discovered schema**:
   ```bash
   cat outputs/schema_discovery_*/schemas/mmk2_dataset1_schema.json | jq '.data_formats.h5.structure'
   ```

2. **对比converter config**:
   ```bash
   cat scripts/format_converters/tolerobot/configs/converter_config_discover_robotics_aitbot_mmk2_*.yaml
   ```

3. **修正config文件**:
   - 删除不存在的字段
   - 添加缺失的必需字段
   - 修正字段路径（如 `observations/qpos` vs `observation/qpos`）

4. **验证修复**:
   ```bash
   python schema_config_comparator.py \
       outputs/schema_discovery_*/schemas/mmk2_dataset1_schema.json \
       scripts/format_converters/tolerobot/configs/converter_config_discover_robotics_aitbot_mmk2_*.yaml
   ```

### 方法2: 半自动修复（未来优化）

可以开发一个配置文件自动修复工具：

```python
# 伪代码
def auto_fix_config(schema, config):
    """基于discovered schema自动修复config"""
    # 删除config中不存在的字段
    # 建议添加schema中存在但config缺失的字段
    # 修正字段路径
    return fixed_config
```

---

## 📊 预期结果

### 成功指标

完成批量Schema Discovery后，应该获得：

1. **Schema文件**: 每个分析的数据集一个
   - 总数: ~40个 (8 models × 5 datasets)
   - 格式: JSON
   - 大小: ~10-100KB/文件

2. **Diagnosis文件**: 每个数据集一个
   - 包含具体的配置问题
   - 修复建议
   - 严重程度分类

3. **Overall Report**: 1个
   - 汇总所有分析结果
   - 按device_model分类统计

4. **配置修复任务清单**:
   - 哪些config需要修改
   - 具体需要修改什么
   - 优先级排序

### 问题预估

基于项目背景，预计会发现：

- **MMK2**: 可能有相机命名不一致问题
- **Yinhe**: 字段路径问题
- **Realman**: MCAP版本可能有schema差异
- **Agilex**: 多版本config可能需要区分
- **Leju**: 外部格式可能有特殊字段
- **Ruantong**: 多个GT版本需要对应正确config
- **Zhipingfang**: arm配置版本众多，需要匹配正确
- **Galaxea**: H5+MP4版本可能有字段差异

---

## 🚨 可能遇到的问题

### 问题1: 数据集路径不存在
**现象**: `WARNING - 数据集路径不存在: /mnt/nas/...`

**原因**: 数据库中的路径可能已过时或不正确

**解决**:
- 跳过（工具会自动跳过）
- 或手动更新数据库中的路径

### 问题2: ffprobe not found
**现象**: `ffprobe failed, fallback to cv2`

**原因**: 系统未安装ffmpeg

**解决**:
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg
```

### 问题3: 内存不足
**现象**: 进程被kill或OOM

**原因**: 分析大数据集时内存不足

**解决**:
- 减少采样数量: `./run_batch_discovery.sh 3 3`
- 或分批运行，手动指定device_model

### 问题4: Schema发现失败
**现象**: 某些数据集的schema为空或报错

**原因**: 
- 数据格式不标准
- 文件损坏
- 未知的数据结构

**解决**:
- 查看详细日志: `outputs/*/execution.log`
- 手动分析该数据集
- 可能需要扩展发现器以支持特殊格式

---

## 📞 后续支持

完成Schema Discovery后，下一步将是：

1. **配置文件修复** (2-3天)
   - 基于诊断结果修复converter config
   - 重点修复优先级device_model

2. **修复验证** (1天)
   - 重新运行schema discovery验证修复
   - 确保所有P0问题已解决

3. **性能优化实施** (2天)
   - 视频延迟加载
   - H5文件句柄缓存

4. **小规模转换测试** (1天)
   - 使用修复后的config测试转换
   - 验证容错机制

---

## ✅ 完成检查清单

- [x] 创建所有Schema Discovery工具模块
- [x] 创建数据库查询工具
- [x] 创建Schema vs Config对比工具
- [x] 创建批量分析主程序
- [x] 创建README文档
- [x] 创建快速启动脚本
- [x] 创建测试脚本
- [ ] 运行测试验证工具可用（需要用户环境）
- [ ] 运行批量Schema Discovery（需要数据库访问）
- [ ] 分析诊断结果
- [ ] 生成配置修复任务清单

---

**工具已准备就绪，等待在实际环境中运行！** 🚀

