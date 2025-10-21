#!/usr/bin/env python3
"""
测试 semaphore 资源泄漏修复

这个脚本用于验证：
1. is_test=True 时不会产生 semaphore 泄漏
2. is_test=False 时正确清理资源
3. 转换完成后没有资源泄漏警告
"""

import gc
import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from robocoin_dataset.utils.logger import setup_logger


def test_converter_resource_cleanup(dataset_path: Path, is_test: bool = True):
    """测试转换器资源清理"""
    
    logger = setup_logger(
        name=f"test_{'test' if is_test else 'full'}_mode",
        log_dir=project_root / "logs",
        level=logging.INFO,
    )
    
    logger.info(f"{'='*60}")
    logger.info(f"Testing converter with is_test={is_test}")
    logger.info(f"Dataset path: {dataset_path}")
    logger.info(f"{'='*60}")
    
    try:
        # 这里需要根据实际情况导入和创建 converter
        # 示例代码（需要根据实际数据集类型调整）:
        
        # from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
        #     LerobotFormatConverterFactory,
        # )
        # 
        # converter = LerobotFormatConverterFactory.create_converter(
        #     dataset_path=dataset_path,
        #     device_model="your_device_model",
        #     output_path=Path("/tmp/test_output"),
        #     converter_config={...},
        #     converter_module_path="...",
        #     converter_class_name="...",
        #     repo_id="test/repo",
        #     logger=logger,
        # )
        # 
        # # 执行转换
        # for task, task_ep_idx, ep_idx in converter.convert(is_test=is_test):
        #     logger.info(f"Converted episode {ep_idx}")
        
        logger.info("✅ Conversion completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Conversion failed: {e}")
        raise
    finally:
        # 强制垃圾回收
        gc.collect()
        logger.info("🔄 Garbage collection completed")
    
    logger.info(f"{'='*60}")
    logger.info("Test finished - check for semaphore leak warnings")
    logger.info(f"{'='*60}\n")


def main():
    """主函数"""
    # 示例：测试 realman MCAP 数据集
    # dataset_path = Path("/home/diy01/dev/robocoin-dataset/data/realman/put_the_soda")
    
    print("\n" + "="*60)
    print("Semaphore Leak Fix Test")
    print("="*60)
    print("\nThis script demonstrates the fix for semaphore resource leaks.")
    print("\nUsage:")
    print("  python scripts/test_semaphore_leak_fix.py")
    print("\nModify the script to:")
    print("  1. Set your dataset_path")
    print("  2. Configure converter parameters")
    print("  3. Run with is_test=True and is_test=False")
    print("\nExpected results:")
    print("  ✅ No semaphore leak warnings after conversion")
    print("  ✅ Test mode completes quickly without processing images")
    print("  ✅ Full mode properly cleans up resources")
    print("\n" + "="*60 + "\n")
    
    # 取消注释并配置以运行实际测试：
    # dataset_path = Path("your/dataset/path")
    # test_converter_resource_cleanup(dataset_path, is_test=True)
    # test_converter_resource_cleanup(dataset_path, is_test=False)


if __name__ == "__main__":
    main()
