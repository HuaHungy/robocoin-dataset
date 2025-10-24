#!/usr/bin/env python3
"""
软通(Ruantong) H5+JPG 容错机制测试脚本

测试场景：
1. 测试必需相机缺失：验证是否正确跳过episode
2. 测试可选相机第0帧缺失：验证是否从配置中移除
3. 测试可选相机某帧缺失：验证是否复制上一帧
4. 测试正常场景：验证所有相机正常工作
"""

import argparse
import logging
import shutil
import sys
import tempfile
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
src_dir = project_root / 'src'
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import h5py
import numpy as np
from PIL import Image

from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5_jpg import (
    LerobotFormatConverterH5Jpg,
)


def setup_logger(name: str) -> logging.Logger:
    """设置日志器"""
    logger = logging.Logger(name, level=logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def create_test_dataset(
    dataset_dir: Path,
    scenario: str,
    logger: logging.Logger
) -> None:
    """创建测试数据集
    
    参数:
        dataset_dir: 数据集根目录
        scenario: 测试场景
            - 'normal': 正常场景（所有相机都存在）
            - 'missing_required': 缺失必需相机（cam_high_rgb）
            - 'missing_optional_frame0': 可选相机第0帧就缺失
            - 'missing_optional_frame5': 可选相机第5帧缺失
        logger: 日志器
    """
    logger.info(f"📁 创建测试数据集 - 场景: {scenario}")
    
    # 创建任务目录
    task_dir = dataset_dir / "test_task"
    task_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建 local_task_info.yaml
    task_info_content = """task_name: test_fault_tolerance
description: 软通容错机制测试任务
"""
    (task_dir / "local_task_info.yaml").write_text(task_info_content)
    
    # 创建 episode 目录
    episode_dir = task_dir / "episode_0"
    episode_dir.mkdir(exist_ok=True)
    
    # 创建 H5 文件
    h5_file = episode_dir / "aligned_joints.h5"
    num_frames = 10
    
    with h5py.File(h5_file, 'w') as f:
        # 创建 state 数据
        state_data = np.random.rand(num_frames, 41).astype(np.float32)
        f.create_dataset('state', data=state_data)
        
        # 创建 action 数据
        action_data = np.random.rand(num_frames, 20).astype(np.float32)
        f.create_dataset('action', data=action_data)
    
    logger.info(f"   ✅ 创建H5文件: {num_frames} 帧")
    
    # 创建图像目录和图像
    camera_dir = episode_dir / "camera"
    
    # 定义所有相机
    all_cameras = [
        'cam_high_rgb',  # 必需
        'cam_left_wrist_rgb',  # 必需
        'cam_right_wrist_rgb',  # 必需
        'cam_high_center_fisheye_rgb',  # 可选
        'cam_back_left_fisheye_rgb',  # 可选
    ]
    
    required_cameras = ['cam_high_rgb', 'cam_left_wrist_rgb', 'cam_right_wrist_rgb']
    
    # 创建图像（640x480 RGB）
    def create_dummy_image(cam_name: str, frame_idx: int) -> Image.Image:
        """创建测试图像（带颜色编码）"""
        img_array = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # 添加标识（左上角文字区域设为特定颜色）
        if 'high' in cam_name:
            img_array[:50, :50] = [255, 0, 0]  # 红色
        elif 'left' in cam_name:
            img_array[:50, :50] = [0, 255, 0]  # 绿色
        elif 'right' in cam_name:
            img_array[:50, :50] = [0, 0, 255]  # 蓝色
        else:
            img_array[:50, :50] = [255, 255, 0]  # 黄色
        
        return Image.fromarray(img_array)
    
    # 根据场景创建不同的图像集合
    for frame_idx in range(num_frames):
        frame_dir = camera_dir / str(frame_idx)
        frame_dir.mkdir(parents=True, exist_ok=True)
        
        for cam_name in all_cameras:
            # 根据场景决定是否创建该图像
            skip_image = False
            
            if scenario == 'missing_required':
                # 场景1：缺失必需相机（cam_high_rgb）
                if cam_name == 'cam_high_rgb':
                    skip_image = True
            
            elif scenario == 'missing_optional_frame0':
                # 场景2：可选相机第0帧就缺失
                if cam_name == 'cam_high_center_fisheye_rgb' and frame_idx == 0:
                    skip_image = True
            
            elif scenario == 'missing_optional_frame5':
                # 场景3：可选相机第5帧缺失
                if cam_name == 'cam_back_left_fisheye_rgb' and frame_idx == 5:
                    skip_image = True
            
            # 'normal': 所有图像都创建
            
            if not skip_image:
                img = create_dummy_image(cam_name, frame_idx)
                img_path = frame_dir / f"{cam_name}.jpg"
                img.save(img_path)
        
        logger.info(f"   ✅ 创建第 {frame_idx} 帧图像")
    
    # 创建 meta_info.json (可选)
    meta_info_content = """{
  "task": "test_fault_tolerance",
  "num_frames": 10,
  "fps": 30
}
"""
    (episode_dir / "meta_info.json").write_text(meta_info_content)
    
    # 创建 local_dataset_info.yaml
    dataset_info_content = """task_descriptions:
  - test_fault_tolerance
"""
    (dataset_dir / "local_dataset_info.yaml").write_text(dataset_info_content)
    
    logger.info(f"✅ 测试数据集创建完成: {dataset_dir}")


def create_test_config(scenario: str) -> dict:
    """创建测试配置
    
    参数:
        scenario: 测试场景
    """
    config = {
        'fps': 30,
        'features': {
            'observation': {
                'images': [
                    # 必需相机
                    {
                        'cam_name': 'cam_high_rgb',
                        'args': {
                            'file_type': 'jpg',
                            'h5_path': 'camera/{frame_idx}/cam_high_rgb.jpg'
                        }
                    },
                    {
                        'cam_name': 'cam_left_wrist_rgb',
                        'args': {
                            'file_type': 'jpg',
                            'h5_path': 'camera/{frame_idx}/cam_left_wrist_rgb.jpg'
                        }
                    },
                    {
                        'cam_name': 'cam_right_wrist_rgb',
                        'args': {
                            'file_type': 'jpg',
                            'h5_path': 'camera/{frame_idx}/cam_right_wrist_rgb.jpg'
                        }
                    },
                    # 可选相机
                    {
                        'cam_name': 'cam_high_center_fisheye_rgb',
                        'args': {
                            'file_type': 'jpg',
                            'h5_path': 'camera/{frame_idx}/cam_high_center_fisheye_rgb.jpg'
                        }
                    },
                    {
                        'cam_name': 'cam_back_left_fisheye_rgb',
                        'args': {
                            'file_type': 'jpg',
                            'h5_path': 'camera/{frame_idx}/cam_back_left_fisheye_rgb.jpg'
                        }
                    },
                ],
                'state': {
                    'sub_state': [
                        {
                            'names': [f'joint_{i}' for i in range(41)],
                            'args': {
                                'h5_path': 'state',
                                'range_from': 0,
                                'range_to': 41
                            },
                            'convert_func': 'to_float32'
                        }
                    ]
                }
            },
            'action': {
                'sub_action': [
                    {
                        'names': [f'action_{i}' for i in range(20)],
                        'args': {
                            'h5_path': 'action',
                            'range_from': 0,
                            'range_to': 20
                        },
                        'convert_func': 'to_float32'
                    }
                ]
            }
        }
    }
    
    return config


def test_scenario(
    scenario: str,
    expected_result: str,
    logger: logging.Logger
) -> bool:
    """测试特定场景
    
    参数:
        scenario: 测试场景名称
        expected_result: 期望结果 ('success', 'error', 'warning')
        logger: 日志器
    
    返回:
        bool: 测试是否通过
    """
    logger.info("=" * 80)
    logger.info(f"🧪 测试场景: {scenario}")
    logger.info(f"   期望结果: {expected_result}")
    logger.info("=" * 80)
    
    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        dataset_dir = tmp_path / "dataset"
        output_dir = tmp_path / "output"
        
        # 创建测试数据集
        create_test_dataset(dataset_dir, scenario, logger)
        
        # 创建配置
        config = create_test_config(scenario)
        
        # 创建 converter
        try:
            converter = LerobotFormatConverterH5Jpg(
                dataset_path=str(dataset_dir),
                output_path=str(output_dir),
                converter_config=config,
                repo_id="test/ruantong_fault_tolerance",
                device_model="ruantong_a2d",
                logger=logger
            )
            
            logger.info("✅ Converter 初始化成功")
            
            # 检查可选相机移除
            final_cameras = [
                img['cam_name'] 
                for img in converter.converter_config['features']['observation']['images']
            ]
            logger.info(f"📋 最终相机列表: {final_cameras}")
            
        except Exception as e:
            if expected_result == 'error':
                logger.info(f"✅ 测试通过 - 正确抛出错误: {type(e).__name__}")
                logger.info(f"   错误信息: {str(e)[:200]}...")
                return True
            else:
                logger.error(f"❌ 测试失败 - 初始化时抛出了意外错误: {e}")
                return False
        
        # 尝试读取第一个episode的第一帧
        try:
            logger.info("📖 尝试读取测试数据...")
            
            task_paths = list(converter.path_task_dict.keys())
            if not task_paths:
                raise RuntimeError("没有找到任何任务")
            
            task_path = task_paths[0]
            ep_idx = 0
            
            # 准备缓冲区
            images_buffer = converter._prepare_episode_images_buffer(task_path, ep_idx)
            
            # 读取所有帧
            num_frames = converter._get_episode_frames_num(task_path, ep_idx)
            logger.info(f"   Episode 帧数: {num_frames}")
            
            for frame_idx in range(min(num_frames, 6)):  # 只测试前6帧
                logger.info(f"\n   📸 读取第 {frame_idx} 帧:")
                
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
                        logger.warning(f"      ⚠️  {cam_name}: 图像缺失")
                        if expected_result == 'error':
                            logger.info(f"✅ 测试通过 - 正确抛出错误: {type(e).__name__}")
                            return True
                        raise
            
            if expected_result == 'success' or expected_result == 'warning':
                logger.info(f"\n✅ 测试通过 - 成功读取所有数据")
                return True
            else:
                logger.error(f"\n❌ 测试失败 - 期望错误但成功执行")
                return False
        
        except Exception as e:
            if expected_result == 'error':
                logger.info(f"✅ 测试通过 - 正确抛出错误: {type(e).__name__}")
                logger.info(f"   错误信息: {str(e)[:200]}...")
                return True
            else:
                logger.error(f"❌ 测试失败 - 抛出了意外错误: {e}")
                import traceback
                traceback.print_exc()
                return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='软通容错机制测试')
    parser.add_argument(
        '--scenario',
        choices=['normal', 'missing_required', 'missing_optional_frame0', 'missing_optional_frame5', 'all'],
        default='all',
        help='测试场景'
    )
    
    args = parser.parse_args()
    
    logger = setup_logger('test_ruantong')
    
    # 定义测试用例
    test_cases = [
        ('normal', 'success', '正常场景：所有相机都存在'),
        ('missing_required', 'error', '缺失必需相机：应该在预验证阶段报错'),
        ('missing_optional_frame0', 'success', '可选相机第0帧缺失：应该从配置中移除'),
        ('missing_optional_frame5', 'success', '可选相机第5帧缺失：应该复制上一帧'),
    ]
    
    # 运行测试
    if args.scenario == 'all':
        scenarios_to_test = test_cases
    else:
        scenarios_to_test = [tc for tc in test_cases if tc[0] == args.scenario]
    
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "软通(Ruantong)容错机制测试" + " " * 30 + "║")
    print("╚" + "═" * 78 + "╝")
    print()
    
    results = []
    for scenario, expected, description in scenarios_to_test:
        logger.info(f"\n📝 {description}")
        passed = test_scenario(scenario, expected, logger)
        results.append((scenario, passed))
        print()
    
    # 汇总结果
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 30 + "测试结果汇总" + " " * 34 + "║")
    print("╠" + "═" * 78 + "╣")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for scenario, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        scenario_desc = next(desc for s, _, desc in test_cases if s == scenario)
        print(f"║  {status}  {scenario_desc:<64}  ║")
    
    print("╠" + "═" * 78 + "╣")
    print(f"║  总计: {passed_count}/{total_count} 通过" + " " * (64 - len(f"总计: {passed_count}/{total_count} 通过")) + "║")
    print("╚" + "═" * 78 + "╝")
    print()
    
    return 0 if passed_count == total_count else 1


if __name__ == '__main__':
    sys.exit(main())

