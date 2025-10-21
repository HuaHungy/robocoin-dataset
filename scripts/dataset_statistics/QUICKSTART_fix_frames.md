# 智平方帧数不一致问题 - 快速解决指南

## 🚨 问题现象

转换智平方数据集时报错：
```
ValueError: ❌ H5数据集帧数不一致（数据质量问题）
   observations/arm/right/joints: 164 帧
   observations/arm/right/wrench: 165 帧
```

## ✅ 解决方案（3种方法）

### 方法1: 一键批量处理（最推荐）⭐

```bash
cd /home/diy01/dev/robocoin-dataset
./scripts/dataset_statistics/batch_fix_zhipingfang.sh
```

脚本会：
1. 先询问是否 DRY RUN（推荐选 'y' 测试）
2. 自动扫描所有子数据集
3. 检测帧数不一致的文件
4. 移动到 error/ 目录
5. 显示处理报告

### 方法2: 处理单个数据集

```bash
# 示例：处理"公共服务"数据集
python scripts/dataset_statistics/fix_frame_inconsistency.py \
  "/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/公共服务" \
  --config scripts/format_converters/tolerobot/configs/converter_config_zhipingfang.yaml \
  --workers 16
```

### 方法3: 手动移动单个文件

根据错误信息中的提示命令：
```bash
mkdir -p '<task目录>/error'
mv '<问题文件.h5>' '<task目录>/error/'
```

## 📋 推荐流程

### 步骤1: 测试运行（DRY RUN）

```bash
cd /home/diy01/dev/robocoin-dataset

# 测试单个数据集
python scripts/dataset_statistics/fix_frame_inconsistency.py \
  "/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/公共服务" \
  --dry-run \
  --config scripts/format_converters/tolerobot/configs/converter_config_zhipingfang.yaml
```

查看输出，确认：
- ✅ 检测到的不一致文件是否合理
- ✅ 移动操作是否正确
- ✅ 没有意外的文件被标记

### 步骤2: 实际执行

如果测试结果正常，执行实际移动：

```bash
# 方法A: 使用一键脚本（推荐）
./scripts/dataset_statistics/batch_fix_zhipingfang.sh
# 选择 'n' 跳过 DRY RUN，直接执行

# 方法B: 手动执行单个数据集
python scripts/dataset_statistics/fix_frame_inconsistency.py \
  "/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/公共服务" \
  --config scripts/format_converters/tolerobot/configs/converter_config_zhipingfang.yaml
```

### 步骤3: 验证结果

```bash
# 查看移动到 error 的文件数
find "/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条" \
  -name "error" -type d -exec sh -c '
    error_dir="$1"
    count=$(ls -1 "$error_dir" 2>/dev/null | wc -l)
    if [ "$count" -gt 0 ]; then
        echo "$error_dir: $count 个文件"
    fi
  ' sh {} \;
```

### 步骤4: 重新运行转换

移动问题文件后，重新运行转换任务：
- Converter 会自动跳过 error/ 目录中的文件
- 只处理正常的文件

## 🔍 脚本功能说明

### fix_frame_inconsistency.py

**功能**：检测并移动帧数不一致的 H5 文件

**参数**：
- `dataset_path` (必需): 数据集目录
- `--config`: 配置文件（加快检查速度）
- `--dry-run`: 测试模式（不实际移动）
- `--max-files`: 限制检查文件数（测试用）
- `--workers`: 并行进程数（默认8）

**输出示例**：
```
======================================================================
检查结果
======================================================================
✅ 一致: 1200 个文件
❌ 不一致: 34 个文件
⚠️  错误: 0 个文件

======================================================================
处理 34 个帧数不一致的文件
======================================================================
📁 task_27/converted_0501.h5
   帧数差异:
     164 帧: observations/arm/right/joints
     165 帧: observations/arm/right/wrench
  ✅ 已移动: converted_0501.h5 -> error/
```

### batch_fix_zhipingfang.sh

**功能**：批量处理所有智平方子数据集

**特点**：
- 交互式询问（DRY RUN / 实际执行）
- 自动遍历所有子数据集
- 显示进度和统计
- 安全确认机制

## ⚠️ 注意事项

1. **备份数据**（可选）：
   - 移动操作是可逆的（文件只是移到 error/ 子目录）
   - 如不放心可先 `--dry-run` 测试

2. **磁盘空间**：
   - 移动操作几乎不占用额外空间（同一文件系统内）
   - 确保有足够空间存放日志输出

3. **并行处理**：
   - `--workers` 不要超过 CPU 核心数
   - 大数据集可设置 `--workers 16`

4. **配置文件**：
   - 使用 `--config` 可以加快 10x 速度
   - 只检查配置中指定的路径

## 📊 预期效果

### 修复前：
```
Task lerobot_format_convert_16 failed
ValueError: ❌ H5数据集帧数不一致
RuntimeError: convert dataset /mnt/.../公共服务 failed
```

### 修复后：
```
✅ 移动 34 个有问题的文件到 error/
✅ Converter 成功处理 1200 个正常文件
⚠️  跳过 34 个有问题的文件
```

## 🔧 故障排查

### Q: 脚本运行报错 "ModuleNotFoundError: No module named 'h5py'"

**A**: 安装依赖
```bash
uv pip install h5py pyyaml
```

### Q: 权限错误 "Permission denied"

**A**: 检查文件权限
```bash
# 检查数据集目录权限
ls -ld "/mnt/nas/synnas/docker2/外部数据/智平方/..."

# 如果需要，添加写权限
chmod u+w -R "<数据集目录>"
```

### Q: 脚本运行很慢

**A**: 使用配置文件加速
```bash
# 从 8小时 → 30分钟
--config scripts/format_converters/tolerobot/configs/converter_config_zhipingfang.yaml
```

### Q: 想恢复移动的文件

**A**: 从 error/ 移回
```bash
# 查看 error 目录
ls -lh "<task目录>/error/"

# 移回文件
mv "<task目录>/error/<文件>" "<task目录>/"
```

## 📞 联系支持

如果遇到问题：
1. 查看详细错误日志
2. 检查 README_fix_frame_inconsistency.md 文档
3. 联系数据采集团队报告数据质量问题
