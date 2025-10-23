#!/usr/bin/env python3
"""
简化的软通容错测试脚本 - 直接测试实际数据
"""

import logging
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
src_dir = project_root / 'src'
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import yaml
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5_jpg import (
    LerobotFormatConverterH5Jpg,
)


def setup_logger() -> logging.Logger:
    """设置日志器"""
    logger = logging.Logger('test', level=logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def main():
    logger = setup_logger()
    
    # 使用实际数据
    dataset_path = project_root / 'data' / 'ruantong_a2d:default_version'
    if not dataset_path.exists():
        logger.error(f"❌ 数据集不存在: {dataset_path}")
        return 1
    
    # 加载配置
    config_path = project_root / 'scripts' / 'format_converters' / 'tolerobot' / 'configs' / 'converter_config_ruantong.yaml'
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    logger.info("="*80)
    logger.info("🧪 测试软通容错机制 - 使用实际数据")
    logger.info("="*80)
    logger.info(f"📁 数据集路径: {dataset_path}")
    logger.info(f"📝 配置文件: {config_path.name}")
    
    try:
        # 创建converter
        logger.info("\n🔧 创建converter...")
        converter = LerobotFormatConverterH5Jpg(
            dataset_path=str(dataset_path),
            output_path=str(project_root / 'outputs' / 'test_ruantong_fault_tolerance'),
            converter_config=config,
            repo_id="test/ruantong_fault_tolerance",
            device_model="ruantong_a2d",
            logger=logger
        )
        
        logger.info("✅ Converter创建成功")
        
        # 检查相机配置
        final_cameras = [
            img['cam_name'] 
            for img in converter.converter_config['features']['observation']['images']
        ]
        logger.info(f"\n📷 最终相机列表 ({len(final_cameras)}个):")
        for cam in final_cameras:
            required_mark = "✅ (必需)" if cam in converter.required_cameras else "🔶 (可选)"
            logger.info(f"   {required_mark} {cam}")
        
        # 获取第一个任务
        task_paths = list(converter.path_task_dict.keys())
        if not task_paths:
            logger.error("❌ 没有找到任何任务")
            return 1
        
        task_path = task_paths[0]
        task_name = converter.path_task_dict[task_path]
        logger.info(f"\n📋 测试任务: {task_name}")
        logger.info(f"   路径: {task_path}")
        
        # 准备缓冲区
        ep_idx = 0
        images_buffer = converter._prepare_episode_images_buffer(task_path, ep_idx)
        
        # 获取episode帧数
        num_frames = converter._get_episode_frames_num(task_path, ep_idx)
        logger.info(f"\n📊 Episode {ep_idx} 帧数: {num_frames}")
        
        # 读取前5帧测试
        logger.info(f"\n📸 读取前5帧进行测试:")
        for frame_idx in range(min(num_frames, 5)):
            logger.info(f"\n   Frame {frame_idx}:")
            
            for img_config in converter.converter_config['features']['observation']['images']:
                cam_name = img_config['cam_name']
                args_dict = img_config['args'].copy()
                args_dict['cam_name'] = cam_name
                
                try:
                    img_array = converter._get_frame_image(
                        task_path, ep_idx, frame_idx, args_dict, images_buffer
                    )
                    logger.info(f"      ✅ {cam_name}: {img_array.shape}")
                except FileNotFoundError as e:
                    logger.warning(f"      ⚠️  {cam_name}: 图像缺失 - {str(e)[:100]}")
                except Exception as e:
                    logger.error(f"      ❌ {cam_name}: 错误 - {type(e).__name__}: {e}")
        
        logger.info("\n✅ 测试完成")
        return 0
    
    except Exception as e:
        logger.error(f"\n❌ 测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

