# 数据库迁移文档 - 添加Episode统计字段

**日期**: 2025-10-27  
**迁移版本**: v1.1  
**影响表**: `lerobot_format_convert`, `lerobot_format_convert_test`

---

## 🐛 问题描述

### 错误信息
```
sqlite3.OperationalError: no such column: lerobot_format_convert_test.total_episodes
```

### 根本原因
在代码中添加了3个新字段（`total_episodes`, `converted_episodes`, `skipped_episodes`），但现有数据库表结构还是旧的。SQLAlchemy只会在**创建新表**时应用模型定义，**不会自动修改现有表**。

---

## 📊 迁移内容

### 需要添加的字段

**两个表都需要添加以下3个字段**：

| 字段名 | 类型 | 允许NULL | 默认值 | 说明 |
|--------|------|----------|--------|------|
| `total_episodes` | INTEGER | YES | NULL | 总episode数 |
| `converted_episodes` | INTEGER | YES | NULL | 成功转换的episode数 |
| `skipped_episodes` | INTEGER | YES | NULL | 跳过的episode数 |

### 影响的表
1. `lerobot_format_convert` - 正式转换记录表
2. `lerobot_format_convert_test` - 测试转换记录表

---

## 🚀 快速执行（推荐）

### 方法1: 使用自动化脚本（最简单）

```bash
# 1. 停止Server
Ctrl+C

# 2. 在Server机器上执行
cd ~/robocoin-dataset
./db/migrations/run_migration.sh db/datasets.db

# 3. 重启Server
python scripts/format_converters/tolerobot/server.py \
    --db-file=db/datasets.db \
    --host=172.16.13.140 --port=8769 \
    --is-test --auto-reencode
```

**脚本功能**：
- ✅ 自动创建带时间戳的数据库备份
- ✅ 执行迁移SQL
- ✅ 验证迁移结果
- ✅ 迁移失败时自动回滚

---

## 📝 手动迁移步骤

如果自动脚本无法执行，可以手动迁移：

### 步骤1: 停止Server
```bash
# 在Server终端按 Ctrl+C
```

### 步骤2: 备份数据库
```bash
cd ~/robocoin-dataset
cp db/datasets.db db/datasets.db.backup_$(date +%Y%m%d_%H%M%S)
```

### 步骤3: 执行迁移SQL

**选项A: 使用SQL文件**
```bash
sqlite3 db/datasets.db < db/migrations/add_episode_statistics_fields.sql
```

**选项B: 直接执行SQL命令**
```bash
sqlite3 db/datasets.db <<EOF
-- 为 lerobot_format_convert_test 表添加字段
ALTER TABLE lerobot_format_convert_test ADD COLUMN total_episodes INTEGER DEFAULT NULL;
ALTER TABLE lerobot_format_convert_test ADD COLUMN converted_episodes INTEGER DEFAULT NULL;
ALTER TABLE lerobot_format_convert_test ADD COLUMN skipped_episodes INTEGER DEFAULT NULL;

-- 为 lerobot_format_convert 表添加字段
ALTER TABLE lerobot_format_convert ADD COLUMN total_episodes INTEGER DEFAULT NULL;
ALTER TABLE lerobot_format_convert ADD COLUMN converted_episodes INTEGER DEFAULT NULL;
ALTER TABLE lerobot_format_convert ADD COLUMN skipped_episodes INTEGER DEFAULT NULL;
EOF
```

### 步骤4: 验证迁移
```bash
# 查看表结构
sqlite3 db/datasets.db "PRAGMA table_info(lerobot_format_convert_test);"

# 应该看到新增的3个字段（输出最后3行）：
# 11|total_episodes|INTEGER|0||0
# 12|converted_episodes|INTEGER|0||0
# 13|skipped_episodes|INTEGER|0||0
```

### 步骤5: 重启Server
```bash
python scripts/format_converters/tolerobot/server.py \
    --db-file=db/datasets.db \
    --host=172.16.13.140 --port=8769 \
    --is-test --auto-reencode
```

---

## 🔍 验证迁移成功

### 验证1: 查看表结构
```bash
sqlite3 db/datasets.db "PRAGMA table_info(lerobot_format_convert_test);"
```

**预期输出**（最后3行）：
```
11|total_episodes|INTEGER|0||0
12|converted_episodes|INTEGER|0||0
13|skipped_episodes|INTEGER|0||0
```

### 验证2: 查询数据
```bash
sqlite3 db/datasets.db "SELECT total_episodes, converted_episodes, skipped_episodes FROM lerobot_format_convert_test LIMIT 5;"
```

**预期输出**：
- 已存在的记录：所有字段为空（NULL）
- 新转换的记录：字段有值

### 验证3: 检查Server日志
启动Server后，观察日志：
- ✅ 无 "no such column" 错误
- ✅ 可以正常分配任务
- ✅ Client连接成功

### 验证4: 完成一个任务后检查
```bash
sqlite3 db/datasets.db "
SELECT 
    dataset_uuid,
    convert_status,
    total_episodes,
    converted_episodes,
    skipped_episodes,
    updated_at
FROM lerobot_format_convert_test
WHERE total_episodes IS NOT NULL
ORDER BY updated_at DESC
LIMIT 5;
"
```

**预期结果**：新完成的任务应该有统计信息

---

## ⚠️ 常见问题

### Q1: 迁移会丢失数据吗？
**A**: 不会。`ALTER TABLE ADD COLUMN` 是安全操作，只添加新列，不影响现有数据。

### Q2: 已存在的记录会有统计信息吗？
**A**: 不会。已存在的记录这3个字段为`NULL`，只有新转换的任务才会填充这些字段。

### Q3: 需要重启Clients吗？
**A**: 不需要。只需重启Server。Clients会自动重新连接。

### Q4: 如果迁移失败怎么办？
**A**: 
1. 如果使用自动脚本，会自动回滚到备份
2. 如果手动迁移，恢复备份：
   ```bash
   cp db/datasets.db.backup_XXXXXX db/datasets.db
   ```

### Q5: 可以在Server运行时迁移吗？
**A**: **不推荐**。虽然SQLite支持，但可能导致：
- Server报错
- 数据不一致
- 迁移失败

**建议**: 停止Server后再迁移。

---

## 📚 相关文件

- **迁移SQL**: `db/migrations/add_episode_statistics_fields.sql`
- **执行脚本**: `db/migrations/run_migration.sh`
- **代码变更**: `docs/ALL_ISSUES_FIXED_20251026.md`
- **模型定义**: `src/robocoin_dataset/database/models.py`

---

## 🔄 回滚方案

如果迁移后发现问题，可以回滚：

### 方法1: 恢复备份（推荐）
```bash
# 停止Server
Ctrl+C

# 恢复备份（使用之前创建的备份文件）
cp db/datasets.db.backup_YYYYMMDD_HHMMSS db/datasets.db

# 重启Server
```

### 方法2: 删除字段（不推荐）
SQLite不支持直接删除列，需要重建表：
```sql
-- 不推荐，复杂且有风险
-- 参考：https://www.sqlite.org/lang_altertable.html
```

---

## 📈 迁移历史

| 日期 | 版本 | 描述 | 影响表 |
|------|------|------|--------|
| 2025-10-27 | v1.1 | 添加episode统计字段 | lerobot_format_convert, lerobot_format_convert_test |
| 2025-10-26 | v1.0 | 添加device_model字段 | lerobot_format_convert, lerobot_format_convert_test |

---

## ✅ 检查清单

迁移完成后，确认以下项目：

- [ ] 停止Server
- [ ] 创建数据库备份
- [ ] 执行迁移SQL
- [ ] 验证表结构（PRAGMA table_info）
- [ ] 验证无SQL错误
- [ ] 重启Server
- [ ] 无"no such column"错误
- [ ] Clients正常连接
- [ ] 完成一个测试任务
- [ ] 检查统计字段有值
- [ ] 保留备份文件（至少7天）

---

**迁移状态**: 准备就绪，等待执行  
**下一步**: 在Server机器上执行迁移脚本

