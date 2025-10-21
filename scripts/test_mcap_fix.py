#!/usr/bin/env python3
"""测试 MCAP test 模式的资源泄漏修复"""

import logging
import sys
import warnings
from pathlib import Path

import yaml

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverterFactory,
)
from robocoin_dataset.utils.logger import setup_logger


def test_realman_mcap_test_mode() -> bool:
    """测试 realman MCAP 数据集的 test 模式"""
    
    # 设置路径
    project_root = Path(__file__).parent.parent
    dataset_path = project_root / 'data' / 'realman'
    output_path = project_root / 'outputs' / 'test_mcap_fix'
    
    # 加载配置文件
    with open(dataset_path / 'device_model_annotation.yaml') as f:
        device_model_anno = yaml.safe_load(f)
    
    # realman 的 converter 配置路径（硬编码）
    converter_config_path = project_root / 'scripts' / 'format_converters' / 'tolerobot' / 'configs' / 'converter_config_realman_rmc_aidal_mcap.yaml'
    
    if not converter_config_path.exists():
        print(f'❌ Converter 配置文件不存在: {converter_config_path}')
        return False
    
    with open(converter_config_path) as f:
        converter_config = yaml.safe_load(f)
    
    # 设置 logger
    logger = setup_logger('mcap_test', project_root / 'logs', level=logging.INFO)
    
    print('='*70)
    print('🧪 测试 MCAP Test 模式资源泄漏修复')
    print('='*70)
    print(f'📂 数据集: {dataset_path}')
    print(f'📝 配置文件: {converter_config_path.name}')
    print(f'🎯 输出路径: {output_path}')
    print('='*70)
    
    # 创建 converter
    try:
        converter = LerobotFormatConverterFactory.create_converter(
            dataset_path=dataset_path,
            device_model=device_model_anno.get('device_model', 'realman_robot'),
            output_path=output_path,
            converter_config=converter_config,
            converter_module_path='robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_mcap',
            converter_class_name='LerobotFormatConverterRealmanRmcAidalMcap',
            repo_id='test/realman_mcap',
            logger=logger,
        )
        
        print('✅ Converter 创建成功')
        print()
        print('🚀 开始 test 模式转换（应该只解析 10 帧）...')
        print()
        
        # 运行 test 模式
        episode_count = 0
        for task, task_ep_idx, ep_idx in converter.convert(is_test=True):
            episode_count += 1
            print(f'   ✅ Episode {ep_idx}: task={task}, task_ep={task_ep_idx}')
        
        print()
        print(f'✅ Test 模式完成！处理了 {episode_count} 个 episode')
        print()
        print('🔍 检查是否有资源泄漏警告...')
        print('   如果没有看到 "leaked semaphore objects" 警告，说明修复成功！')
        print('='*70)
        
        return True
        
    except Exception as e:
        print(f'❌ 测试失败: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    # 启用资源追踪警告
    warnings.filterwarnings('default', category=ResourceWarning)
    
    success = test_realman_mcap_test_mode()
    sys.exit(0 if success else 1)
