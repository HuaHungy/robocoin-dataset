-- 修复 lerobot_format_convert 表中 device_model 和 device_model_version 为 NULL 的记录
-- 从 device_model_annotation 表回填数据
--
-- 使用方法:
--   sqlite3 db/datasets.db < fix_null_device_model.sql
--
-- 或者在 sqlite3 交互模式中:
--   sqlite3 db/datasets.db
--   .read fix_null_device_model.sql

-- 1. 统计修复前的 NULL 记录数
.print "=== 修复前统计 ==="
.print ""
.print "lerobot_format_convert 表中 device_model 为 NULL 的记录数:"
SELECT COUNT(*) as null_count 
FROM lerobot_format_convert 
WHERE device_model IS NULL;

.print ""
.print "lerobot_format_convert_test 表中 device_model 为 NULL 的记录数:"
SELECT COUNT(*) as null_count 
FROM lerobot_format_convert_test 
WHERE device_model IS NULL;

-- 2. 显示一些示例 NULL 记录（修复前）
.print ""
.print "=== 修复前示例记录（前5条）==="
.mode column
.headers on
SELECT 
    dataset_uuid,
    device_model,
    device_model_version,
    convert_status,
    substr(updated_at, 1, 19) as updated_at
FROM lerobot_format_convert
WHERE device_model IS NULL
LIMIT 5;

.print ""
.print "=== 开始修复 ==="

-- 3. 修复 lerobot_format_convert 表
UPDATE lerobot_format_convert
SET 
    device_model = (
        SELECT device_model 
        FROM device_model_annotation 
        WHERE device_model_annotation.dataset_uuid = lerobot_format_convert.dataset_uuid
    ),
    device_model_version = (
        SELECT device_model_version 
        FROM device_model_annotation 
        WHERE device_model_annotation.dataset_uuid = lerobot_format_convert.dataset_uuid
    )
WHERE device_model IS NULL
  AND EXISTS (
      SELECT 1 
      FROM device_model_annotation 
      WHERE device_model_annotation.dataset_uuid = lerobot_format_convert.dataset_uuid
  );

.print "✅ lerobot_format_convert 表修复完成"
.print ""

-- 4. 修复 lerobot_format_convert_test 表
UPDATE lerobot_format_convert_test
SET 
    device_model = (
        SELECT device_model 
        FROM device_model_annotation 
        WHERE device_model_annotation.dataset_uuid = lerobot_format_convert_test.dataset_uuid
    ),
    device_model_version = (
        SELECT device_model_version 
        FROM device_model_annotation 
        WHERE device_model_annotation.dataset_uuid = lerobot_format_convert_test.dataset_uuid
    )
WHERE device_model IS NULL
  AND EXISTS (
      SELECT 1 
      FROM device_model_annotation 
      WHERE device_model_annotation.dataset_uuid = lerobot_format_convert_test.dataset_uuid
  );

.print "✅ lerobot_format_convert_test 表修复完成"
.print ""

-- 5. 统计修复后的 NULL 记录数
.print "=== 修复后统计 ==="
.print ""
.print "lerobot_format_convert 表中 device_model 为 NULL 的记录数:"
SELECT COUNT(*) as null_count 
FROM lerobot_format_convert 
WHERE device_model IS NULL;

.print ""
.print "lerobot_format_convert_test 表中 device_model 为 NULL 的记录数:"
SELECT COUNT(*) as null_count 
FROM lerobot_format_convert_test 
WHERE device_model IS NULL;

-- 6. 显示一些修复后的记录
.print ""
.print "=== 修复后示例记录（前5条）==="
SELECT 
    dataset_uuid,
    device_model,
    device_model_version,
    convert_status,
    substr(updated_at, 1, 19) as updated_at
FROM lerobot_format_convert
WHERE device_model IS NOT NULL
ORDER BY updated_at DESC
LIMIT 5;

-- 7. 按 device_model 统计转换情况
.print ""
.print "=== 按设备型号统计转换情况 ==="
SELECT 
    device_model,
    device_model_version,
    convert_status,
    COUNT(*) as count
FROM lerobot_format_convert
WHERE device_model IS NOT NULL
GROUP BY device_model, device_model_version, convert_status
ORDER BY device_model, device_model_version, convert_status;

.print ""
.print "=== 修复完成 ==="
.print ""
.print "提示："
.print "1. 如果修复后仍有 NULL 记录，说明这些记录在 device_model_annotation 表中不存在对应的映射"
.print "2. 这些记录可能需要手动处理或删除"
.print "3. 修复完成后，建议重启 server 和 clients 确保使用最新代码"

