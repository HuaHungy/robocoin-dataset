# 更新MMK2数据集数据库 - 操作指南

**目标**: 将 `storage_peaches_and_pears` 数据集的 `device_model_version` 更新为 `5d_arms`

---

## 📋 准备工作

### 1. 确认新配置已创建 ✅
```bash
ls -lh scripts/format_converters/tolerobot/configs/converter_config_discover_robotics_aitbot_mmk2_5d_arms.yaml
```

### 2. 确认factory配置已更新 ✅
```bash
grep -A 3 "version: 5d_arms" scripts/format_converters/tolerobot/configs/converter_factory_config.yaml
```

---

## 🗄️ 更新数据库

### 方法1: 使用SQL文件（推荐）

```bash
cd /home/liu/program/robocoin-dataset

# 1. 查看当前状态
sqlite3 db/datasets.db < scripts/db/update_mmk2_version.sql

# 2. 确认输出，应该看到 storage_peaches_and_pears 数据集

# 3. 手动执行UPDATE（修改SQL文件，取消注释UPDATE语句）
# 编辑 scripts/db/update_mmk2_version.sql，取消注释UPDATE部分
```

### 方法2: 直接使用SQLite命令

```bash
sqlite3 db/datasets.db

# 在SQLite提示符下执行：

-- 查看当前数据
SELECT dataset_uuid, dataset_name, device_model_version
FROM dmv_annotation
WHERE device_model = 'discover_robotics_aitbot_mmk2'
  AND dataset_name LIKE '%storage_peaches_and_pears%';

-- 记下 dataset_uuid（例如：abc-123-def）

-- 更新版本
UPDATE dmv_annotation
SET device_model_version = '5d_arms'
WHERE device_model = 'discover_robotics_aitbot_mmk2'
  AND dataset_name LIKE '%storage_peaches_and_pears%';

-- 验证更新
SELECT dataset_uuid, dataset_name, device_model_version
FROM dmv_annotation
WHERE device_model = 'discover_robotics_aitbot_mmk2'
  AND dataset_name LIKE '%storage_peaches_and_pears%';

-- 退出
.exit
```

### 方法3: 使用Python脚本

```python
import sqlite3
from pathlib import Path

db_path = Path("db/datasets.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 查看当前状态
cursor.execute("""
    SELECT dataset_uuid, dataset_name, device_model_version
    FROM dmv_annotation
    WHERE device_model = 'discover_robotics_aitbot_mmk2'
      AND dataset_name LIKE '%storage_peaches_and_pears%'
""")

print("更新前:")
for row in cursor.fetchall():
    print(f"  UUID: {row[0]}")
    print(f"  Name: {row[1]}")
    print(f"  Version: {row[2]}")

# 更新版本
cursor.execute("""
    UPDATE dmv_annotation
    SET device_model_version = '5d_arms'
    WHERE device_model = 'discover_robotics_aitbot_mmk2'
      AND dataset_name LIKE '%storage_peaches_and_pears%'
""")

conn.commit()

# 验证更新
cursor.execute("""
    SELECT dataset_uuid, dataset_name, device_model_version
    FROM dmv_annotation
    WHERE device_model = 'discover_robotics_aitbot_mmk2'
      AND dataset_name LIKE '%storage_peaches_and_pears%'
""")

print("\n更新后:")
for row in cursor.fetchall():
    print(f"  UUID: {row[0]}")
    print(f"  Name: {row[1]}")
    print(f"  Version: {row[2]}")

conn.close()
print("\n✅ 更新完成！")
```

---

## 🧹 清除之前的转换记录（可选）

如果之前转换失败，需要清除记录才能重新转换：

```sql
-- 查看是否有转换记录
SELECT convert_status, err_message
FROM lerobot_format_convert_test
WHERE dataset_uuid IN (
    SELECT dataset_uuid FROM dmv_annotation
    WHERE device_model = 'discover_robotics_aitbot_mmk2'
      AND dataset_name LIKE '%storage_peaches_and_pears%'
);

-- 如果状态是FAILED或PROCESSING，删除记录
DELETE FROM lerobot_format_convert_test
WHERE dataset_uuid IN (
    SELECT dataset_uuid FROM dmv_annotation
    WHERE device_model = 'discover_robotics_aitbot_mmk2'
      AND dataset_name LIKE '%storage_peaches_and_pears%'
);
```

---

## ✅ 验证更新

### 检查配置能否正确加载

```bash
cd /home/liu/program/robocoin-dataset

python3 -c "
import yaml
from pathlib import Path

# 加载factory配置
factory_config_path = Path('scripts/format_converters/tolerobot/configs/converter_factory_config.yaml')
with open(factory_config_path) as f:
    factory_config = yaml.safe_load(f)

# 检查5d_arms版本
mmk2_configs = factory_config['discover_robotics_aitbot_mmk2']
for config in mmk2_configs:
    if config['version'] == '5d_arms':
        print('✅ 找到5d_arms版本配置:')
        print(f\"   描述: {config['verison_description']}\")
        print(f\"   配置文件: {config['converter_config_path']}\")
        
        # 尝试加载配置文件
        config_path = Path('scripts/format_converters/tolerobot/configs') / config['converter_config_path']
        with open(config_path) as cf:
            converter_config = yaml.safe_load(cf)
        
        # 检查action维度
        actions = converter_config['features']['action']['sub_action']
        total_dims = 0
        for action in actions:
            names = action['names']
            total_dims += len(names)
        
        print(f\"   Action总维度: {total_dims}D\")
        print('✅ 配置加载成功！')
        break
"
```

---

## 🚀 重新转换

更新数据库后，重新运行转换：

### Test模式验证

```bash
python scripts/format_converters/tolerobot/server.py \
    --db-file=db/datasets.db \
    --host=0.0.0.0 --port=8769 \
    --is-test \
    --specific-device-model discover_robotics_aitbot_mmk2
```

### 正式转换

```bash
python scripts/format_converters/tolerobot/server.py \
    --db-file=db/datasets.db \
    --host=0.0.0.0 --port=8769
```

---

## 📊 预期结果

转换应该成功，不再出现维度不匹配错误：

```
✅ Converting Dataset: 100%
📊 Total: 34, Converted: 34, Skipped: 0
✅ Task completed successfully
```

---

## ❓ 问题排查

### 如果仍然失败

1. **检查数据库更新是否生效**
   ```sql
   SELECT device_model_version FROM dmv_annotation
   WHERE dataset_name LIKE '%storage_peaches_and_pears%';
   ```
   应该显示 `5d_arms`

2. **检查转换记录是否清除**
   ```sql
   SELECT convert_status FROM lerobot_format_convert_test
   WHERE dataset_uuid = 'your-uuid';
   ```
   不应该有PROCESSING或COMPLETED记录

3. **检查配置文件路径**
   ```bash
   ls -lh scripts/format_converters/tolerobot/configs/converter_config_discover_robotics_aitbot_mmk2_5d_arms.yaml
   ```

---

**更新完数据库后，就可以重新转换了！** 🎉

