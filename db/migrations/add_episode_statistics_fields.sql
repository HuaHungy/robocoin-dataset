-- 数据库迁移脚本：添加episode统计字段
-- 日期: 2025-10-27
-- 目的: 为 lerobot_format_convert 和 lerobot_format_convert_test 表添加统计字段

-- ============================================================================
-- 1. 为 lerobot_format_convert_test 表添加字段
-- ============================================================================

-- 添加 total_episodes 字段
ALTER TABLE lerobot_format_convert_test 
ADD COLUMN total_episodes INTEGER DEFAULT NULL;

-- 添加 converted_episodes 字段
ALTER TABLE lerobot_format_convert_test 
ADD COLUMN converted_episodes INTEGER DEFAULT NULL;

-- 添加 skipped_episodes 字段
ALTER TABLE lerobot_format_convert_test 
ADD COLUMN skipped_episodes INTEGER DEFAULT NULL;

-- ============================================================================
-- 2. 为 lerobot_format_convert 表添加字段
-- ============================================================================

-- 添加 total_episodes 字段
ALTER TABLE lerobot_format_convert 
ADD COLUMN total_episodes INTEGER DEFAULT NULL;

-- 添加 converted_episodes 字段
ALTER TABLE lerobot_format_convert 
ADD COLUMN converted_episodes INTEGER DEFAULT NULL;

-- 添加 skipped_episodes 字段
ALTER TABLE lerobot_format_convert 
ADD COLUMN skipped_episodes INTEGER DEFAULT NULL;

-- ============================================================================
-- 验证迁移
-- ============================================================================

-- 验证 lerobot_format_convert_test 表结构
SELECT sql FROM sqlite_master WHERE type='table' AND name='lerobot_format_convert_test';

-- 验证 lerobot_format_convert 表结构
SELECT sql FROM sqlite_master WHERE type='table' AND name='lerobot_format_convert';

-- ============================================================================
-- 完成
-- ============================================================================

-- 迁移完成！
-- 
-- 验证方法：
-- SELECT total_episodes, converted_episodes, skipped_episodes 
-- FROM lerobot_format_convert_test 
-- LIMIT 5;

