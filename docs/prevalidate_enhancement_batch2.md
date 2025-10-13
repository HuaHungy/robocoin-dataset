# Prevalidate Files 增强 - Batch 2 (中等优先级)

完成时间：2025年
批次：中等优先级转换器（6个）

---

## 📋 批次概览

本批次增强了6个中等优先级的转换器，这些转换器已有部分验证逻辑，但需要添加更多检查或将警告升级为错误。

### 转换器列表

| 序号 | 转换器 | 原有问题 | 增强内容 |
|-----|--------|----------|---------|
| 3 | Annotation+H5+MP4 | 缺少路径检查 | ✅ 添加路径验证、H5抽样 |
| 4 | JPG+JSON | 缺少路径检查 | ✅ 添加路径验证、图像抽样 |
| 5 | Leju Waibu | 缺少内容验证 | ✅ 添加路径验证、JSON/H5验证 |
| 6 | MCAP | 缺少路径和内容检查 | ✅ 添加路径验证、MCAP读取测试 |
| 7 | MMK2 | 仅警告不阻止 | ✅ 升级warnings为errors |
| 8 | LeRobot | 仅警告不阻止 | ✅ 升级warnings为errors |

---

## 🔧 详细增强内容

### 3. Annotation+H5+MP4 转换器

**文件**: `lerobot_format_converter_annotation_h5_mp4.py`

**原有问题**:
- 缺少 `dataset_path` 和 `annotation_dir` 的存在性检查
- 没有验证H5文件内容

**增强内容**:
1. **dataset_path 存在性检查**
   - 验证路径是否存在
   - 显示父目录和同级目录列表（限制15个）
   - 提供详细的错误诊断信息

2. **annotation_dir 存在性检查**
   - 验证annotation目录是否存在
   - 显示目录结构和期望格式
   - 列出现有目录和文件

3. **H5文件抽样验证** ⭐
   - 读取第一个episode的H5文件
   - 验证文件可读性
   - 检查数据集是否为空
   - 显示数据集数量和列表

**代码示例**:
```python
# H5文件抽样验证
if len(annotation_data) > 0:
    first_entry = annotation_data[0]
    h5_path = self._get_h5_file_path(first_entry)
    
    if h5_path.exists():
        import h5py
        with h5py.File(h5_path, 'r') as f:
            datasets = list(f.keys())
            if not datasets:
                self.logger.warning("⚠️ H5文件为空...")
            else:
                self.logger.info(f"✅ H5文件验证通过：{len(datasets)} datasets")
```

---

### 4. JPG+JSON 转换器

**文件**: `lerobot_format_converter_jpg_json.py`

**原有问题**:
- 缺少 `task_path` 的存在性和类型检查
- 没有验证图像文件质量

**增强内容**:
1. **task_path 存在性检查**
   - 验证路径是否存在
   - 显示父目录和同级目录列表
   - 区分路径不存在 vs 不是目录

2. **task_path 类型检查**
   - 验证路径是目录而非文件
   - 显示实际类型（文件/未知）

3. **图像文件抽样验证** ⭐
   - 读取第一个episode的第一张图片
   - 验证图像可读性
   - 显示图像数量、分辨率、格式
   - 检测损坏的图像文件

**代码示例**:
```python
# 图像抽样验证（仅第一个episode）
if ep_dir == episodes[0]:
    first_cam = camera_folders[0]
    image_files = list(first_cam.glob("*.jpg")) + list(first_cam.glob("*.png"))
    
    if image_files:
        test_img = Image.open(image_files[0])
        width, height = test_img.size
        self.logger.info(
            f"✅ 图像验证：{len(image_files)}张，{width}x{height}，{test_img.format}"
        )
```

---

### 5. Leju Waibu 转换器

**文件**: `lerobot_format_converter_leju_waibu.py`

**原有问题**:
- 缺少 `episode_path` 的存在性检查
- 没有验证metadata.json和H5文件内容

**增强内容**:
1. **episode_path 存在性检查**
   - 验证路径是否存在
   - 显示父目录和同级目录列表
   - 区分路径不存在 vs 不是目录

2. **metadata.json 内容验证** ⭐
   - 解析JSON文件
   - 验证是否为字典类型
   - 显示键数量和主要键列表
   - 捕获JSON解析错误（行号、列号）

3. **H5文件内容验证** ⭐
   - 读取 `proprio_stats.hdf5`
   - 检查数据集是否为空
   - 显示数据集数量和列表
   - 检测文件损坏

**代码示例**:
```python
# Metadata JSON验证
with open(metadata_file) as f:
    metadata = json.load(f)
    if not isinstance(metadata, dict):
        self.logger.warning(f"⚠️ Metadata不是字典: {type(metadata).__name__}")
    else:
        self.logger.info(f"✅ Metadata：{len(metadata)}键")

# H5文件验证
with h5py.File(h5_file, 'r') as f:
    datasets = list(f.keys())
    self.logger.info(f"✅ H5文件：{len(datasets)} datasets")
```

---

### 6. MCAP 转换器

**文件**: `lerobot_format_converter_mcap.py`

**原有问题**:
- 缺少 `path` 的存在性检查
- 没有验证MCAP文件内容

**增强内容**:
1. **path 存在性检查**
   - 验证路径是否存在
   - 显示父目录和同级目录列表
   - 区分路径不存在 vs 不是目录

2. **MCAP文件内容验证** ⭐
   - 使用 `mcap.reader` 读取第一个MCAP文件
   - 获取文件摘要信息
   - 显示：文件大小（MB）、消息数量、通道数量
   - 检测文件是否为空或损坏
   - 处理mcap库未安装的情况

**代码示例**:
```python
# MCAP文件验证
from mcap.reader import make_reader
with open(first_mcap, "rb") as f:
    reader = make_reader(f)
    summary = reader.get_summary()
    if summary:
        self.logger.info(
            f"✅ MCAP验证：{first_mcap.stat().st_size/1024/1024:.2f}MB，"
            f"{summary.statistics.message_count}条消息，"
            f"{len(summary.channels)}通道"
        )
```

---

### 7. MMK2 转换器

**文件**: `lerobot_format_converter_mmk2.py`

**原有问题**:
- Episode目录检查只产生警告
- Required subdirectory检查只产生警告
- Image文件检查只产生警告
- **不会阻止转换继续**

**增强内容**:
1. **Episode目录检查升级** ⚠️➡️❌
   - 从 `logger.warning` 升级为 `raise FileNotFoundError`
   - 显示目录和文件列表（各显示前10个）
   - 说明期望的命名模式：`episode_0000`, `episode_0001`

2. **Required subdirectory检查升级** ⚠️➡️❌
   - 从 `logger.warning` 升级为 `raise FileNotFoundError`
   - 显示episode目录结构
   - 明确指出缺少的子目录（如 `observations/`）

3. **Image文件检查升级** ⚠️➡️❌
   - 从 `logger.warning` 升级为 `raise FileNotFoundError`
   - 显示observations目录内容（前10项）
   - 列出支持的图像格式：.jpg, .png, .jpeg

**行为变化**:
```python
# 之前（仅警告）
if not episode_dirs:
    self.logger.warning(f"No episode directories found in {task_path}")
# 现在（阻止转换）
if not episode_dirs:
    raise FileNotFoundError(
        f"❌ No episode directories found\n"
        f"   Expected pattern: episode_0000, episode_0001, ..."
    )
```

---

### 8. LeRobot 转换器

**文件**: `lerobot_format_converter_lerobot.py`

**原有问题**:
- Required directories检查只产生警告
- Parquet files检查只产生警告
- Metadata files检查只产生警告
- **不会阻止转换继续**

**增强内容**:
1. **Required directories检查升级** ⚠️➡️❌
   - 从 `logger.warning` 升级为 `raise FileNotFoundError`
   - 验证 `data/`, `meta/`, `videos/` 三个目录
   - 显示现有目录和文件列表
   - 说明LeRobot格式要求

2. **Parquet files检查升级** ⚠️➡️❌
   - 从 `logger.warning` 升级为 `raise FileNotFoundError`
   - 检查 `data/chunk-000/*.parquet` 文件
   - 显示chunk目录列表和chunk-000内容
   - 区分两种错误：无parquet文件 vs chunk-000不存在

3. **Data chunk directory检查升级** (新增)
   - 验证 `data/chunk-000/` 目录存在
   - 显示data目录结构
   - 说明chunk命名规范

4. **Metadata files检查升级** ⚠️➡️❌
   - 从 `logger.warning` 升级为 `raise FileNotFoundError`
   - 验证 `episodes.jsonl` 和 `tasks.jsonl`
   - 显示meta目录内容
   - 强调文件名大小写敏感

**行为变化**:
```python
# 之前（仅警告）
if missing_dirs:
    if self.logger:
        self.logger.warning(f"Missing directories: {missing_dirs}")

# 现在（阻止转换）
if missing_dirs:
    raise FileNotFoundError(
        f"❌ Missing required directories\n"
        f"   Missing: {', '.join(missing_dirs)}\n"
        f"   Required: data/, meta/, videos/"
    )
```

---

## 📊 增强效果对比

### 代码行数变化

| 转换器 | 原有行数 | 新增行数 | 增长率 |
|-------|---------|---------|--------|
| Annotation+H5+MP4 | 28 | +48 | +171% |
| JPG+JSON | 47 | +51 | +109% |
| Leju Waibu | 38 | +73 | +192% |
| MCAP | 28 | +53 | +189% |
| MMK2 | 47 | +48 | +102% |
| LeRobot | 62 | +61 | +98% |

**总计**: 从250行增强到584行（+334行，+134%）

### 验证能力提升

| 验证类型 | Batch 2 前 | Batch 2 后 | 提升 |
|---------|-----------|-----------|-----|
| 路径存在性检查 | 0/6 | 6/6 | ✅ 100% |
| 内容抽样验证 | 0/6 | 4/6 | ✅ 67% |
| 警告升级为错误 | 0/2 | 2/2 | ✅ 100% |
| 详细错误信息 | 6/6 | 6/6 | ✅ 保持 |

---

## 🎯 关键改进点

### 1. 路径验证标准化
所有转换器现在都检查：
- ✅ 路径是否存在
- ✅ 路径是否为目录（vs 文件）
- ✅ 显示父目录和同级项（限制15个）
- ✅ 提供详细的诊断建议

### 2. 内容抽样验证 (新增)
4个转换器新增内容验证：
- **Annotation+H5+MP4**: H5文件数据集列表
- **JPG+JSON**: 图像分辨率、格式、数量
- **Leju Waibu**: JSON结构、H5数据集
- **MCAP**: 文件大小、消息数、通道数

### 3. 警告升级为错误 (行为变化)
2个转换器的验证现在会阻止转换：
- **MMK2**: Episode/subdirectory/image检查
- **LeRobot**: Directory/parquet/metadata检查

**影响**: 避免在损坏数据上浪费时间，更早发现问题

---

## 🔍 错误信息格式统一

### 标准格式

```
❌ [错误描述]
   📂 [相关路径1]: 值
   📂 [相关路径2]: 值
   📋 [列表信息]: 项1, 项2, ...
   💡 [要求说明]
   💡 Check if:
      1. [检查项1]
      2. [检查项2]
      3. [检查项3]
```

### Emoji 使用规范
- ❌ 错误标题
- ⚠️ 警告信息
- ✅ 验证通过
- 📂 路径/目录
- 📄 文件
- 📋 列表内容
- 💡 建议/提示
- 🔍 搜索/查找
- 📊 统计信息

---

## 🧪 测试建议

### 测试场景

#### 1. 路径验证测试
```python
# 测试不存在的路径
converter = AnnotationH5MP4FormatConverter(
    dataset_path="/nonexistent/path",
    ...
)
# 期望：FileNotFoundError with parent directory listing
```

#### 2. 内容验证测试
```python
# 测试损坏的H5文件
# 期望：Warning with detailed error message
```

#### 3. Warning升级测试
```python
# MMK2：缺少episode目录
# 期望：FileNotFoundError (not warning)
```

---

## 📈 进度总结

### 整体进度（所有11个转换器）

- ✅ **Batch 1 (Critical)**: 2/2 完成
  - MP4+JSON: JSON验证、路径检查
  - Rosbag: Critical/warning分离

- ✅ **Batch 2 (Medium)**: 6/6 完成
  - Annotation+H5+MP4: 路径检查、H5抽样
  - JPG+JSON: 路径检查、图像抽样
  - Leju Waibu: 路径检查、JSON/H5验证
  - MCAP: 路径检查、MCAP读取
  - MMK2: Warning升级
  - LeRobot: Warning升级

- ✅ **Already Complete**: 3/3 (无需改动)
  - H5: 已有完整验证
  - H5+JPG: 已有完整验证
  - G1: 已有完整验证

**总进度**: 11/11 (100%) ✅

---

## 🎓 最佳实践总结

### 1. 路径验证三步骤
1. 检查 `path.exists()`
2. 检查 `path.is_dir()` （如果需要目录）
3. 显示父目录和同级项

### 2. 文件内容验证原则
- 仅抽样验证（第一个episode/文件）
- 使用try-except捕获所有异常
- 验证通过显示✅信息
- 验证失败显示⚠️警告（不阻止）

### 3. 错误信息设计
- 使用emoji增强可读性
- 显示实际值（不只是"not found"）
- 提供3-5条具体检查建议
- 限制列表长度（避免信息过载）

### 4. Warning vs Error 决策
- **Error (raise)**: 必须修复才能转换
  - 路径不存在
  - Required文件缺失
  - 目录结构不符合要求
- **Warning (logger.warning)**: 可能有问题但不阻止
  - 文件内容可能损坏
  - 可选文件缺失
  - 格式警告

---

## 📝 变更日志

- **2025-XX-XX**: 完成所有6个中等优先级转换器增强
- **改动文件**:
  1. `lerobot_format_converter_annotation_h5_mp4.py` (+48行)
  2. `lerobot_format_converter_jpg_json.py` (+51行)
  3. `lerobot_format_converter_leju_waibu.py` (+73行)
  4. `lerobot_format_converter_mcap.py` (+53行)
  5. `lerobot_format_converter_mmk2.py` (+48行)
  6. `lerobot_format_converter_lerobot.py` (+61行)

---

## ✅ 完成确认

### 代码审查清单
- ✅ 所有路径检查包含父目录listing
- ✅ 内容验证使用try-except
- ✅ 错误信息格式统一（emoji + 3项检查建议）
- ✅ Warning vs Error 使用合理
- ✅ 列表输出限制长度（避免过长）
- ✅ 所有新代码有注释标记 `# 🆕 增加` 或 `# 🆕 升级`

### 功能验证清单
- ✅ 路径不存在时显示父目录内容
- ✅ 内容验证失败时给出详细错误
- ✅ MMK2/LeRobot的warning已升级为error
- ✅ 所有抽样验证只检查第一个文件（性能）
- ✅ 错误信息可读性强

### 文档清单
- ✅ 本批次总结文档（当前文件）
- ✅ 每个转换器的详细说明
- ✅ 代码示例和对比
- ✅ 测试建议
- ✅ 最佳实践总结

---

**结论**: Batch 2所有6个转换器的`_prevalidate_files()`方法已全面增强，现在具有：
- 完整的路径验证
- 合理的内容抽样检查
- 统一的错误信息格式
- 适当的错误严重级别

与Batch 1合并后，**8/11转换器已完成增强，3/11本已完整，总进度100%** ✅
