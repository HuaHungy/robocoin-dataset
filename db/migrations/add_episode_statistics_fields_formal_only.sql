-- 数据库迁移脚本：只为正式转换表添加episode统计字段
-- 日期: 2025-10-27
-- 目的: 只为 lerobot_format_convert 表添加统计字段（不包括测试表）

-- ============================================================================
-- 为 lerobot_format_convert 表添加字段（仅正式转换）
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

-- 验证 lerobot_format_convert 表结构
SELECT sql FROM sqlite_master WHERE type='table' AND name='lerobot_format_convert';

-- ============================================================================
-- 完成
-- ============================================================================

-- 迁移完成！
-- 
-- 注意：lerobot_format_convert_test 表不包含这些字段
-- 测试模式不会记录统计信息

