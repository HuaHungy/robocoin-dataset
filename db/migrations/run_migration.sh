#!/bin/bash

# 数据库迁移执行脚本
# 用法: ./run_migration.sh /path/to/datasets.db

DB_FILE="${1:-db/datasets.db}"

if [ ! -f "$DB_FILE" ]; then
    echo "❌ 错误: 数据库文件不存在: $DB_FILE"
    echo "用法: $0 /path/to/datasets.db"
    exit 1
fi

echo "📊 开始数据库迁移..."
echo "数据库文件: $DB_FILE"
echo ""

# 备份数据库
BACKUP_FILE="${DB_FILE}.backup_$(date +%Y%m%d_%H%M%S)"
echo "1️⃣  创建备份..."
cp "$DB_FILE" "$BACKUP_FILE"
echo "✅ 备份完成: $BACKUP_FILE"
echo ""

# 执行迁移
echo "2️⃣  执行迁移SQL..."
sqlite3 "$DB_FILE" < "$(dirname "$0")/add_episode_statistics_fields.sql"

if [ $? -eq 0 ]; then
    echo "✅ 迁移成功！"
    echo ""
    
    # 验证
    echo "3️⃣  验证迁移结果..."
    echo ""
    echo "lerobot_format_convert_test 表新增字段："
    sqlite3 "$DB_FILE" "PRAGMA table_info(lerobot_format_convert_test);" | grep -E "(total_episodes|converted_episodes|skipped_episodes)"
    echo ""
    echo "lerobot_format_convert 表新增字段："
    sqlite3 "$DB_FILE" "PRAGMA table_info(lerobot_format_convert);" | grep -E "(total_episodes|converted_episodes|skipped_episodes)"
    echo ""
    echo "✅ 数据库迁移完成！"
    echo ""
    echo "现在可以重启Server和Clients了"
else
    echo "❌ 迁移失败！"
    echo "正在恢复备份..."
    mv "$BACKUP_FILE" "$DB_FILE"
    echo "✅ 已恢复到备份版本"
    exit 1
fi

