#!/bin/bash
# Script to recursively clean all .log files in /logs/dataloader

LOG_DIR="/home/rogerspyke/projects/robocoin-dataset/logs/dataloader"

if [ ! -d "$LOG_DIR" ]; then
    echo "Error: Directory $LOG_DIR does not exist"
    exit 1
fi

echo "Cleaning .log files in $LOG_DIR..."
find "$LOG_DIR" -type f -name "*.log" -print -delete

echo "Done! All .log files have been removed."
