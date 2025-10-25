#!/bin/bash
# 快速运行容错机制测试

cd "$(dirname "$0")/.."

python scripts/test_fault_tolerance.py \
    --dataset-path /mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条/算法采集_PCB/ \
    --device-model zhipingfang \
    --test-mode \
    "$@"

