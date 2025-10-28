# CRITICAL - 立即需要执行的修复

## 问题汇总

### 1️⃣ galaxea - 视频文件读取失败

**错误**: 
```
Failed to read frame 0 from .../3942_cam_high.mp4
```

**原因**：
- 视频文件损坏
- 视频编码格式不支持
- 文件权限问题

**解决方案**：
```bash
# 检查文件是否存在
ls -lh /mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train/open_and_close_nightstand_door/3942/3942_cam_high.mp4

# 尝试用ffprobe检查视频
ffprobe /mnt/nas/.../3942_cam_high.mp4

# 如果文件损坏，需要重新采集或修复
```

**临时方案**：跳过galaxea数据集，稍后修复

---

### 2️⃣ leju_waibu - 等待数据结构确认

**状态**：等待用户提供数据结构

---

### 3️⃣ yinhe - cmd_body_joint错误（配置未更新）

**错误**：
```
JSON path: 'cmd_body_joint'
JSON data length: 0
```

**原因**：**Client端代码/配置没有更新！**

我们已经修改了配置文件删除cmd_body_joint，但Client还在用旧配置。

**解决方案**：

#### Step 1: 在所有Client机器上更新代码

```bash
# 每台Client机器
cd ~/robocoin-dataset
git pull origin feat/test

# 验证配置文件已更新
grep -A 5 "sub_action:" scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml | head -10

# 应该看到 "# 🆕 Body joints已删除" 的注释
```

#### Step 2: 停止所有clients并重启

```bash
# Ctrl+C 停止
# 然后重启
python scripts/format_converters/tolerobot/multi_client.py \
    --host 172.16.13.140 --port 8769 --num-clients 4
```

#### Step 3: 重置yinhe的失败任务

```bash
# Server机器
sqlite3 db/datasets.db

-- 重置yinhe的PROCESSING任务
UPDATE lerobot_format_convert_test 
SET convert_status = 'PENDING', err_message = NULL
WHERE device_model = 'yinhe' 
  AND convert_status = 'PROCESSING';

.quit
```

---

### 4️⃣ mmk2/所有数据集 - 状态管理问题

**错误**：
```
FileExistsError: [Errno 17] File exists: '.../discover_robotics_aitbot_mmk2_...'
```

**状态异常**：
- `convert_status = PROCESSING`
- `err_message` 有内容

**根本原因**：**数据库迁移未执行！**

缺少`total_episodes`, `converted_episodes`, `skipped_episodes`字段，导致：
1. Server收到FAILED消息
2. 尝试调用`upsert_leformat_convert(..., total_episodes=None, ...)`
3. **查询语句失败**（SELECT ... total_episodes ... - 字段不存在）
4. **状态更新失败**
5. 任务卡在PROCESSING

**CRITICAL解决方案**：

#### Step 1: 立即执行数据库迁移（Server机器）

```bash
# ⚠️ 这是最关键的步骤！
cd ~/robocoin-dataset

# 停止Server (Ctrl+C)

# 执行迁移
./db/migrations/run_migration.sh db/datasets.db

# 验证迁移成功
sqlite3 db/datasets.db ".schema lerobot_format_convert_test" | grep -E "(total_episodes|converted_episodes|skipped_episodes)"

# 应该看到这三个字段
```

#### Step 2: 重置所有卡在PROCESSING的任务

```bash
# Server机器
sqlite3 db/datasets.db

-- 查看有多少任务卡在PROCESSING
SELECT COUNT(*) FROM lerobot_format_convert_test WHERE convert_status = 'PROCESSING';

-- 重置这些任务（清除错误信息）
UPDATE lerobot_format_convert_test 
SET convert_status = 'PENDING', err_message = NULL
WHERE convert_status = 'PROCESSING';

-- 验证
SELECT convert_status, COUNT(*) FROM lerobot_format_convert_test GROUP BY convert_status;

.quit
```

#### Step 3: 清理已存在的mmk2目录（如果需要重新转换）

```bash
# Server机器或有权限的机器
# ⚠️ 小心执行，确认目录正确

# 查看哪些mmk2目录已存在
ls -ld /mnt/nas/synnas/docker2/robocoin-datasets*/discover_robotics_aitbot_mmk2*

# 如果确定要重新转换，删除或重命名
# 方案A: 重命名（保留备份）
mv /mnt/nas/.../discover_robotics_aitbot_mmk2_store_pomegranates_and_mangoes \
   /mnt/nas/.../discover_robotics_aitbot_mmk2_store_pomegranates_and_mangoes.old

# 方案B: 删除（谨慎！）
# rm -rf /mnt/nas/.../discover_robotics_aitbot_mmk2_store_pomegranates_and_mangoes
```

#### Step 4: 重启Server

```bash
# Server机器
cd ~/robocoin-dataset

# 启动Server（确认参数正确）
python scripts/format_converters/tolerobot/server.py \
    --db-file=db/datasets.db \
    --host=172.16.13.140 \
    --port=8769 \
    --is-test \  # ← 如果是test模式
    --auto-reencode
```

---

## 🎯 执行顺序（重要！）

### 阶段1：数据库修复（最优先）

1. ✅ **Server机器**：执行数据库迁移
2. ✅ **Server机器**：重置PROCESSING任务
3. ✅ **Server机器**：重启Server

### 阶段2：Client更新

4. ✅ **所有Client机器**：git pull更新代码
5. ✅ **所有Client机器**：重启clients

### 阶段3：数据修复（可选）

6. ⏸️ **galaxea**：检查视频文件，决定是否跳过
7. ⏸️ **mmk2重复目录**：清理或重命名

---

## 📊 执行后的预期结果

### 数据库状态应该是：

```sql
-- 正常任务
convert_status = 'PENDING'  -- 待处理
convert_status = 'PROCESSING'  -- 正在处理（不应有err_message）
convert_status = 'COMPLETED'  -- 成功完成
convert_status = 'FAILED'  -- 失败（有err_message）

-- 不应该出现的组合：
convert_status = 'PROCESSING' AND err_message IS NOT NULL  -- ❌ Bug!
```

### 任务状态流转应该是：

```
PENDING → PROCESSING → COMPLETED (成功)
                    ↘ FAILED (失败，有err_message)
```

### yinhe应该：

- ✅ 不再报 cmd_body_joint 错误
- ✅ 正常转换
- ✅ 状态正确更新

### 所有失败任务应该：

- ✅ 状态 = FAILED（不是PROCESSING）
- ✅ err_message 有详细错误信息
- ✅ 可以手动重置为PENDING重试

---

## ⚠️ 为什么会出现"PROCESSING + err_message"的组合？

### 正常流程：

```
1. Client开始处理 → Server设置 PROCESSING
2. Client失败 → 返回 TASK_FAILED + err_message
3. Server收到 → 更新为 FAILED + err_message  ✅
```

### 异常流程（数据库迁移未执行）：

```
1. Client开始处理 → Server设置 PROCESSING
2. Client失败 → 返回 TASK_FAILED + err_message
3. Server收到 → 尝试更新...
4. 数据库查询失败 → ❌ SELECT ... total_episodes ... (字段不存在)
5. 更新失败 → 状态停留在 PROCESSING
6. BUT: err_message 可能在另一次尝试中写入了
```

**解决方案**：执行数据库迁移，添加缺失的字段！

---

## 🔍 验证清单

完成所有步骤后，验证：

### [ ] 数据库schema正确

```bash
sqlite3 db/datasets.db ".schema lerobot_format_convert_test" | \
    grep -E "(total_episodes|converted_episodes|skipped_episodes)"
# 应该看到这三个字段
```

### [ ] 没有异常的状态组合

```sql
-- 不应该有 PROCESSING + err_message
SELECT COUNT(*) FROM lerobot_format_convert_test 
WHERE convert_status = 'PROCESSING' AND err_message IS NOT NULL;
-- 应该返回 0
```

### [ ] yinhe配置已更新

```bash
# Client机器
grep "cmd_body_joint" scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml
# 应该只看到注释（"# 🆕 Body joints已删除"），没有实际的配置
```

### [ ] Server和Client都在运行

```bash
# Server机器
ps aux | grep "server.py"

# Client机器
ps aux | grep "multi_client.py"
```

---

## 📝 后续建议

1. **数据质量检查**
   - galaxea: 检查所有视频文件完整性
   - 可能需要重新采集或修复损坏的文件

2. **监控状态异常**
   - 定期查询：`SELECT * FROM ... WHERE convert_status = 'PROCESSING' AND err_message IS NOT NULL`
   - 如果再次出现，说明还有其他问题

3. **日志审查**
   - Server日志：查看是否有database异常
   - Client日志：查看转换失败的详细原因

4. **配置验证**
   - 确保所有Client使用相同版本的配置文件
   - 建议配置文件也存储在数据库中，避免不同步

---

## ❓ 常见问题

**Q: 为什么有的任务COMPLETED但有异常？**

A: 这种情况不应该发生。可能的原因：
- 异常是warning而不是error
- 或者是之前失败，后来重试成功了，但err_message没清空

解决：
```sql
UPDATE lerobot_format_convert_test 
SET err_message = NULL 
WHERE convert_status = 'COMPLETED';
```

**Q: FileExistsError怎么办？**

A: 
1. 如果想重新转换：删除或重命名已存在的目录
2. 如果已经转换成功：检查数据库状态，可能需要手动设置为COMPLETED
3. 未来修复：在创建目录时使用`exist_ok=True`或者先检查目录是否存在

**Q: 数据库迁移会影响正在运行的任务吗？**

A: 
- 需要停止Server再迁移
- Client可以继续运行，但无法提交结果（Server已停止）
- 迁移通常很快（<1秒）

---

**关键点**：数据库迁移是解决所有状态管理问题的根本！必须先执行！

