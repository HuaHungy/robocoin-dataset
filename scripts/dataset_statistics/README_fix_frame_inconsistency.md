# H5 帧数不一致问题 - 自动修复方案

## 问题描述

智平方数据集中部分 H5 文件存在帧数不一致问题：
- 不同传感器的数据长度不同（例如：164帧 vs 165帧）
- 这是数据采集时的问题
- 导致转换任务失败

## 解决方案

### 方案1: 自动修复脚本（推荐）

使用 `fix_frame_inconsistency.py` 自动检测并移动有问题的文件：

```bash
# 1. 先DRY RUN 测试（不实际移动）
python scripts/dataset_statistics/fix_frame_inconsistency.py \
  "/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/公共服务" \
  --dry-run

# 2. 查看结果后，实际执行移动
python scripts/dataset_statistics/fix_frame_inconsistency.py \
  "/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/公共服务"

# 3. 使用配置文件指定检查的路径（更快）
python scripts/dataset_statistics/fix_frame_inconsistency.py \
  "/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/公共服务" \
  --config scripts/format_converters/tolerobot/configs/converter_config_zhipingfang.yaml

# 4. 并行处理所有任务目录
for task_dir in /mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/*/; do
  echo "处理: $task_dir"
  python scripts/dataset_statistics/fix_frame_inconsistency.py "$task_dir"
done
```

### 方案2: 手动移动单个文件

根据错误信息中的命令：

```bash
mkdir -p '/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/公共服务/task_27_补采-公共服务1-药盒-医药框-Bot2-0029/error'
mv '/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/公共服务/task_27_补采-公共服务1-药盒-医药框-Bot2-0029/converted_0501.h5' '/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/公共服务/task_27_补采-公共服务1-药盒-医药框-Bot2-0029/error/'
```

### 方案3: 批量处理所有数据集

```bash
# 处理所有智平方数据集
cd /home/diy01/dev/robocoin-dataset

for dataset_dir in /mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/*/; do
  dataset_name=$(basename "$dataset_dir")
  echo "========================================="
  echo "处理数据集: $dataset_name"
  echo "========================================="
  
  python scripts/dataset_statistics/fix_frame_inconsistency.py \
    "$dataset_dir" \
    --config scripts/format_converters/tolerobot/configs/converter_config_zhipingfang.yaml \
    --workers 16
  
  echo ""
done
```

## 脚本参数说明

```
python scripts/dataset_statistics/fix_frame_inconsistency.py <数据集路径> [选项]

必需参数:
  dataset_path          数据集根目录路径

可选参数:
  --config PATH         Converter 配置文件（指定要检查的路径，更快）
  --dry-run            只检测不移动文件（测试用）
  --max-files N        最多检查 N 个文件（测试用）
  --workers N          并行处理的工作进程数（默认8）
```

## 输出说明

脚本会显示：
1. ✅ 帧数一致的文件数
2. ❌ 帧数不一致的文件列表（含详细帧数信息）
3. ⚠️  处理错误的文件
4. 移动操作结果

示例输出：
```
======================================================================
H5 文件帧数一致性检查与修复
======================================================================
📁 数据集: /mnt/nas/.../公共服务
🔧 模式: 实际移动文件

🔍 扫描 H5 文件...
   找到 1234 个 H5 文件

⚙️  检查帧数一致性...
   进度: 1234/1234

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
     165 帧: observations/effector/right/position
     165 帧: observations/timestamp
  ✅ 已移动: converted_0501.h5 -> error/

... (更多文件)

======================================================================
移动结果
======================================================================
✅ 成功移动: 34 个文件

======================================================================
✅ 完成
======================================================================
```

## 注意事项

1. **备份重要数据**：虽然只是移动到 error/ 子目录，但建议先用 `--dry-run` 测试
2. **检查配置文件**：使用 `--config` 可以加快检查速度
3. **并行处理**：大数据集可以增加 `--workers` 数量（注意不要超过 CPU 核心数）
4. **空间检查**：确保有足够的磁盘空间（移动是同一文件系统内操作，几乎不占用额外空间）

## 后续处理

移动到 error/ 目录后：
1. Converter 会自动跳过这些文件
2. 可以稍后分析 error/ 目录中的文件
3. 如需修复，可以使用数据修复工具（未实现）
4. 或者重新采集这些 episodes 的数据

## 检查移动结果

```bash
# 查看某个任务的 error 目录
ls -lh "/mnt/nas/.../task_27.../error/"

# 统计所有 error 文件
find "/mnt/nas/.../公共服务" -name "error" -type d -exec sh -c 'echo "{}"; ls -1 "{}" | wc -l' \;
```
