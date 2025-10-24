#!/bin/bash
# MCAP安全测试脚本 - 只处理前10帧

cd /home/liu/program/robocoin-dataset

echo "╔══════════════════════════════════════════════════════════════════════════╗"
echo "║       🧪 MCAP安全测试（is_test模式 - 只处理10帧）                        ║"
echo "╚══════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "MCAP文件信息："
ls -lh data/realman_rmc_aidal:mcap_version/GroceryStore_Restrocking_Fallen_20251012_104159_192_168_10_124/*.mcap
echo ""
echo "开始测试转换（10帧）..."
echo ""

PYTHONPATH=/home/liu/program/robocoin-dataset/src:$PYTHONPATH \
python scripts/format_converters/tolerobot/convert2lerobot.py \
  --dataset_path data/realman_rmc_aidal:mcap_version \
  --output_path outputs/mcap_test_safe \
  --device_model realman_rmc_aidal \
  --device_model_version mcap_version \
  --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
  --repo_id test/realman_mcap_safe \
  --log_dir outputs/conversion_logs \
  --image_writer_processes 2 \
  --image_writer_threads 2 \
  --video_backend pyav \
  --is-test

echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo "测试完成！"
