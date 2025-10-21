# 智平方帧数不一致 - Multi-Client 架构下的自动修复

## 🏗️ 架构说明

你们使用的是**分布式客户端-服务器架构**：

```
multi_client.py (启动8个进程)
  ├─ client_0 → server → converter → 自动修复 ✅
  ├─ client_1 → server → converter → 自动修复 ✅
  ├─ client_2 → server → converter → 自动修复 ✅
  ...
  └─ client_7 → server → converter → 自动修复 ✅
```

## ✅ 修复在 Multi-Client 下的工作方式

### 1. 服务器端分配任务
```python
# server.py 分配数据集给客户端
task = {
    "dataset_path": "/mnt/.../公共服务",
    "device_model": "zhipingfang",
    ...
}
→ 发送给 client_3
```

### 2. 客户端处理任务
```python
# client.py 接收任务并转换
total_episodes = 1000  # 包含34个问题文件
converted_count = 0

for task, ep_idx in converter.convert():
    # converter 内部：
    # - Episode 495: 检测到帧数不一致
    # - 自动移动到 error/
    # - 跳过（不 yield）
    # - Episode 496: 正常转换 → yield
    
    converted_count += 1  # 实际：966

# 完成后
skipped_count = 1000 - 966 = 34
logger.warning("跳过 34 个 episodes（已移动到 error/）")
```

### 3. 日志输出
```
INFO - converter_log_dir: ./outputs/leformat_converter/log
Converting Dataset: 966/1000 episodes

WARNING - 📊 Conversion completed with some episodes skipped:
   Total episodes found: 1000
   Successfully converted: 966
   Skipped (data quality issues): 34
   ✅ Check error/ directories for skipped files
```

## 🎯 关键优势

### 对比修复前：
```
修复前：
client_3: ❌ Episode 495 失败
          ❌ RuntimeError: convert dataset failed
          ❌ 任务失败，通知 server
          ⏸️  client_3 停止工作

结果：8个客户端中，1个失败，效率降低12.5%
```

### 修复后：
```
修复后：
client_3: ⚠️  Episode 495 帧数不一致
          📦 自动移动到 error/
          ⏭️  跳过
          ✅ 继续处理 Episode 496-1000
          ✅ 任务成功完成

结果：8个客户端全部正常工作，效率100%
```

## 📊 实际使用示例

### 启动服务器
```bash
cd /home/diy01/dev/robocoin-dataset

python scripts/format_converters/tolerobot/server.py \
  --host=0.0.0.0 \
  --port=8765 \
  --db-file=db/dataset.db \
  --convert-root-path=/mnt/nas/robocoin_datasets \
  --log-path=logs/server.log
```

### 启动多个客户端
```bash
# 启动 8 个客户端进程
python scripts/format_converters/tolerobot/multi_client.py \
  --host=172.16.18.160 \
  --port=8765 \
  --num-clients=8 \
  --heartbeat-interval=10.0 \
  --log-path=./outputs/leformat_converter/log
```

### 预期行为
```
Client 0: Converting Dataset: 1234/1234 episodes ✅ (0 skipped)
Client 1: Converting Dataset: 1180/1200 episodes ✅ (20 skipped)
Client 2: Converting Dataset: 966/1000 episodes ✅ (34 skipped)
Client 3: Converting Dataset: 1456/1456 episodes ✅ (0 skipped)
Client 4: Converting Dataset: 890/920 episodes ✅ (30 skipped)
Client 5: Converting Dataset: 1100/1100 episodes ✅ (0 skipped)
Client 6: Converting Dataset: 1050/1080 episodes ✅ (30 skipped)
Client 7: Converting Dataset: 1300/1300 episodes ✅ (0 skipped)

总计: 8176 成功转换, 114 跳过（已移动到 error/）
```

## 🔍 检查跳过的文件

### 查看某个数据集的 error 目录
```bash
# 查看公共服务数据集的问题文件
find /mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/公共服务 \
  -name "error" -type d -exec sh -c '
    error_dir="$1"
    parent=$(dirname "$error_dir")
    count=$(ls -1 "$error_dir" 2>/dev/null | wc -l)
    if [ "$count" -gt 0 ]; then
      echo "$(basename "$parent"): $count 个问题文件"
      ls -lh "$error_dir" | head -5
    fi
  ' sh {} \;
```

### 统计所有跳过的文件
```bash
# 统计智平方所有数据集的问题文件总数
find /mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条 \
  -name "error" -type d -exec sh -c '
    ls -1 "$1" 2>/dev/null | wc -l
  ' sh {} \; | awk '{sum+=$1} END {print "总计:", sum, "个问题文件"}'
```

## 📝 日志位置

### 服务器日志
```bash
tail -f logs/server.log
```

### 客户端日志
```bash
# 查看 client_0 的日志
tail -f ./outputs/leformat_converter/log/client_0.log

# 查看所有客户端的 warning
grep -r "Skipped" ./outputs/leformat_converter/log/
```

### Converter 日志
```bash
# 查看转换详情
tail -f ./outputs/leformat_converter/log/<dataset_name>.log

# 查看自动移动的文件
grep "自动移动问题文件" ./outputs/leformat_converter/log/*.log
```

## ⚠️ 注意事项

### 1. 进度条显示
tqdm 进度条可能显示 `966/1000`，但这是**正常的**：
- 1000：总文件数（包括问题文件）
- 966：成功转换的文件数
- 34：被跳过的文件数（已移动到 error/）

### 2. 任务状态
客户端会报告任务**成功完成**，即使有文件被跳过：
```python
# 任务返回 success，不是 failure
return {}  # 成功
```

### 3. 问题文件处理
被跳过的文件会：
- ✅ 移动到 `<task_path>/error/` 目录
- ✅ 记录在 converter 日志中
- ✅ 不影响其他文件的转换
- ⚠️  需要后续人工分析或重新采集

### 4. 并发安全性
多个客户端同时处理不同数据集时：
- ✅ 每个客户端处理独立的数据集
- ✅ error/ 目录按数据集隔离
- ✅ 不会有文件冲突

## 🎁 额外功能

### 统计报告
客户端完成后会在日志中输出统计：
```
WARNING - 📊 Conversion completed with some episodes skipped:
   Total episodes found: 1000
   Successfully converted: 966
   Skipped (data quality issues): 34
   ✅ Check error/ directories for skipped files
```

### 自动恢复
如果客户端崩溃重启：
- ✅ error/ 目录中的文件会被识别
- ✅ 不会重复处理已移动的文件
- ✅ 继续处理剩余的正常文件

## 🚀 最佳实践

### 1. 预检查（可选）
虽然不是必需的，但可以提前知道有多少问题文件：
```bash
python scripts/dataset_statistics/zhipingfang_preconversion_validator_v2.py \
  --dataset-path "/mnt/.../公共服务" \
  --workers 16
```

### 2. 正常运行
直接启动 multi_client，让系统自动处理：
```bash
python scripts/format_converters/tolerobot/multi_client.py \
  --host=172.16.18.160 \
  --port=8765 \
  --num-clients=8
```

### 3. 监控日志
定期检查 warning 日志：
```bash
# 查看跳过的文件数量
grep "Skipped.*episodes" ./outputs/leformat_converter/log/*.log | \
  awk -F'Skipped \\(' '{print $2}' | \
  awk -F' ' '{sum+=$1} END {print "总跳过:", sum, "个episodes"}'
```

### 4. 事后分析
转换完成后，分析 error/ 目录中的文件：
```bash
# 生成问题文件清单
find /mnt/.../智平方 -name "error" -type d -exec sh -c '
  for file in "$1"/*; do
    echo "$file"
  done
' sh {} \; > error_files_list.txt
```

## 🎉 总结

修复在 **multi_client 分布式架构**下完全正常工作：

1. ✅ **8个客户端同时工作**，互不干扰
2. ✅ **遇到问题自动处理**，不需要人工干预
3. ✅ **任务不会失败**，效率100%
4. ✅ **详细日志记录**，便于追踪和分析
5. ✅ **问题文件隔离**，不影响正常数据

现在可以放心启动 multi_client 进行大规模转换了！
