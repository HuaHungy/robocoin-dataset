# subtask标注数据处理流程全脚本：
## case1： baai团队的子任务标注数据处理全流程
``` bash
python -m scripts.annotation.subtask_annotation_pipeline_baai \
    --db_file ./db/datasets.db \
    --json_src_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/files-to-process \
    --passed_json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/passed-files \
    --impassed_json_dst_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/impassed-files \
    --video_download_dir /mnt/nas/synnas/docker2/robocoin-datasets-subtask-annotations/download-videos 
```