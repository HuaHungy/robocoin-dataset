#!/bin/bash
#
# restore_datasets_backup.sh
#
# This script restores all records in the datasets table to their state as backed up
# from /home/rogerspyke/Downloads/datasets_new_backup.db on 2025-11-02
#
# Usage:
#   ./restore_datasets_backup.sh <target_database_path>
#
# Example:
#   ./restore_datasets_backup.sh /path/to/your/database.db

set -e  # Exit on error

# Check if database path is provided
if [ $# -lt 1 ]; then
    echo "Error: Please provide the target database path"
    echo "Usage: $0 <target_database_path>"
    exit 1
fi

TARGET_DB="$1"

# Check if the database file exists
if [ ! -f "$TARGET_DB" ]; then
    echo "Error: Database file '$TARGET_DB' does not exist"
    exit 1
fi

echo "Restoring datasets records to: $TARGET_DB"
echo "Backup source: /home/rogerspyke/Downloads/datasets_new_backup.db"
echo "Backup date: 2025-11-02"
echo ""

# Backup the current database before restoring
BACKUP_FILE="${TARGET_DB}.pre-restore-$(date +%Y%m%d-%H%M%S).bak"
echo "Creating safety backup at: $BACKUP_FILE"
cp "$TARGET_DB" "$BACKUP_FILE"

# Function to restore records
restore_records() {
    local db_path="$1"

    echo "Restoring records..."

    # Use sqlite3 to execute the restoration
    sqlite3 "$db_path" <<'EOF'
-- Begin transaction for atomic operation
BEGIN TRANSACTION;

-- Clear existing records in the datasets table (optional - comment out if you want to keep existing records)
-- DELETE FROM datasets;

-- Insert or replace the backed up record
INSERT OR REPLACE INTO datasets (
    id,
    dataset_name,
    dataset_uuid,
    device_model,
    device_model_version,
    end_effector_type,
    operation_platform_height,
    yaml_file_path,
    data_path,
    convert_path,
    convert_test_status,
    convert_test_version,
    convert_status,
    convert_version_ps,
    convert_version,
    total_episodes,
    converted_episodes,
    skipped_episodes,
    convert_err_msg,
    sa_dpp_status,
    sa_dpp_version_ps,
    sa_dpp_version,
    sa_dpp_err_msg,
    sim_replay_status,
    sim_replay_version_ps,
    sim_replay_version,
    sim_replay_error_msg,
    motion_annotation_status,
    motion_annotation_version_ps,
    motion_annotation_version,
    motion_annotation_err_msg,
    video_hash_status,
    video_hash_version_ps,
    video_hash_version,
    video_hash_err_msg,
    video_match_status,
    video_match_version_ps,
    video_match_version,
    video_match_err_msg,
    video_ori_subtask_annotation_status,
    video_ori_subtask_annotation_version_ps,
    video_ori_subtask_annotation_version,
    video_ori_subtask_annotation_err_msg,
    video_opt_subtask_annotation_status,
    video_opt_subtask_annotation_version_ps,
    video_opt_subtask_annotation_version,
    video_opt_subtask_annotation_err_msg,
    video_embed_subtask_annotation_status,
    video_embed_subtask_annotation_version_ps,
    video_embed_subtask_annotation_version,
    video_embed_subtask_annotation_err_msg,
    scene_annotation_status,
    scene_annotation_version_ps,
    scene_annotation_version,
    scene_annotation_err_msg,
    data_merge_status,
    data_merge_version_ps_sta,
    data_merge_version_ps_sa,
    data_merge_version_ps_ma,
    data_merge_version,
    data_merge_err_msg,
    data_loader_detection_status,
    data_loader_detection_version_ps,
    data_loader_detection_version,
    data_loader_detection_err_msg,
    ms_upload_status,
    ms_upload_version_ps,
    ms_upload_version,
    ms_upload_err_msg,
    huggingface_upload_status,
    huggingface_upload_version_ps,
    huggingface_upload_version,
    huggingface_upload_err_msg,
    dataset_info_sync_status,
    dataset_info_sync_version_ps,
    dataset_info_sync_version,
    dataset_info_sync_err_msg
) VALUES (
    1,
    'only_test',
    '88e35314-80f0-4a2b-a92e-5b0e769483ae',
    'realman_rmc_aidal',
    'two_finger_gripper',
    'two_finger_gripper',
    NULL,
    '/mnt/nas/synnas/docker2/dataset_test_source/basket_storage_peach/local_dataset_info.yaml',
    '/mnt/nas/synnas/docker2/robocoin-datasets-test/realman_rmc_aidal_only_test',
    '/home/rogerspyke/Downloads/realman_rmc_aidal_only_test_fix',
    'COMPLETED',
    1,
    'COMPLETED',
    1,
    1,
    1,
    1,
    1,
    '1',
    'COMPLETED',
    1,
    1,
    'None',
    'COMPLETED',
    1,
    1,
    '1',
    'COMPLETED',
    1,
    1,
    '1',
    'COMPLETED',
    1,
    1,
    '1',
    'COMPLETED',
    1,
    1,
    'None',
    'COMPLETED',
    1,
    1,
    'None',
    'COMPLETED',
    1,
    1,
    NULL,
    'COMPLETED',
    1,
    1,
    NULL,
    'COMPLETED',
    1,
    1,
    NULL,
    'COMPLETED',
    1,
    1,
    1,
    1,
    NULL,
    'PENDING',
    1,
    7,
    'None',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
);

-- Commit the transaction
COMMIT;

-- Display the restored records
.mode column
.headers on
SELECT id, dataset_name, dataset_uuid, device_model, convert_status, data_loader_detection_status FROM datasets;
EOF

    if [ $? -eq 0 ]; then
        echo ""
        echo "✓ Records restored successfully!"
    else
        echo ""
        echo "✗ Error during restoration. Check the error messages above."
        echo "You can restore from the backup at: $BACKUP_FILE"
        return 1
    fi
}

# Execute the restoration
restore_records "$TARGET_DB"

echo ""
echo "Restoration complete!"
echo "Safety backup saved at: $BACKUP_FILE"
echo ""
echo "To verify the restoration, run:"
echo "  sqlite3 $TARGET_DB 'SELECT * FROM datasets;'"
