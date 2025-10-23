#!/usr/bin/env python3
"""
软通容错机制演示 - 简化版测试
直接创建测试数据并验证容错功能
"""

import h5py
import logging
import numpy as np
import shutil
import sys
import tempfile
from pathlib import Path
from PIL import Image

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
    logger = logging.Logger('demo', level=logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def create_test_image(width=640, height=480, color=(255, 0, 0)):
    """创建测试图像"""
    img_array = np.ones((height, width, 3), dtype=np.uint8)
    img_array[:, :] = color
    return Image.fromarray(img_array)


def test_scenario_1_normal(logger):
    """场景1：所有相机都存在"""
    logger.info("=" * 80)
    logger.info("🧪 场景1：正常场景 - 所有相机都存在")
    logger.info("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        
        # 创建task目录
        task_dir = dataset_dir / "test_task"
        task_dir.mkdir()
        
        # 创建local_task_info.yaml
        (task_dir / "local_task_info.yaml").write_text("task_index: 0\n")
        
        # 创建episode目录
        episode_dir = task_dir / "episode_0"
        episode_dir.mkdir()
        
        # 创建H5文件
        h5_file = episode_dir / "aligned_joints.h5"
        with h5py.File(h5_file, 'w') as f:
            f.create_dataset('state', data=np.random.rand(5, 41).astype(np.float32))
            f.create_dataset('action', data=np.random.rand(5, 20).astype(np.float32))
        
        # 创建所有相机的5帧图像
        cameras = [
            'cam_high_rgb',
            'cam_left_wrist_rgb',
            'cam_right_wrist_rgb',
            'cam_high_center_fisheye_rgb',
            'cam_back_left_fisheye_rgb',
        ]
        
        for frame_idx in range(5):
            frame_dir = episode_dir / "camera" / str(frame_idx)
            frame_dir.mkdir(parents=True)
            
            for cam_name in cameras:
                img = create_test_image(color=(frame_idx * 50, 100, 150))
                img.save(frame_dir / f"{cam_name}.jpg")
        
        # 创建local_dataset_info.yaml
        (dataset_dir / "local_dataset_info.yaml").write_text("task_descriptions:\n  - test\n")
        
        # 创建配置
        config = {
            'fps': 30,
            'features': {
                'observation': {
                    'images': [
                        {'cam_name': c, 'args': {'h5_path': f'camera/{{frame_idx}}/{c}.jpg', 'file_type': 'jpg'}}
                        for c in cameras
                    ],
                    'state': {
                        'sub_state': [{
                            'names': [f'joint_{i}' for i in range(41)],
                            'args': {'h5_path': 'state', 'range_from': 0, 'range_to': 41},
                            'convert_func': 'to_float32'
                        }]
                    }
                },
                'action': {
                    'sub_action': [{
                        'names': [f'action_{i}' for i in range(20)],
                        'args': {'h5_path': 'action', 'range_from': 0, 'range_to': 20},
                        'convert_func': 'to_float32'
                    }]
                }
            }
        }
        
        # 测试
        try:
            converter = LerobotFormatConverterH5Jpg(
                dataset_path=str(dataset_dir),
                output_path=str(tmp_path / "output"),
                converter_config=config,
                repo_id="test/test",
                device_model="ruantong_a2d",
                logger=logger
            )
            
            final_cameras = [img['cam_name'] for img in converter.converter_config['features']['observation']['images']]
            logger.info(f"✅ 成功创建converter，最终相机列表: {final_cameras}")
            
            # 读取第0帧测试
            task_path = list(converter.path_task_dict.keys())[0]
            images_buffer = converter._prepare_episode_images_buffer(task_path, 0)
            
            for cam_name in final_cameras:
                args_dict = {'cam_name': cam_name, 'h5_path': f'camera/{{frame_idx}}/{cam_name}.jpg'}
                img_array = converter._get_frame_image(task_path, 0, 0, args_dict, images_buffer)
                logger.info(f"   ✅ {cam_name}: {img_array.shape}")
            
            logger.info("✅ 场景1测试通过\n")
            return True
            
        except Exception as e:
            logger.error(f"❌ 场景1测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_scenario_2_missing_optional_frame0(logger):
    """场景2：可选相机第0帧就缺失 - 应该从配置中移除"""
    logger.info("=" * 80)
    logger.info("🧪 场景2：可选相机第0帧缺失 - 应该动态移除")
    logger.info("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        
        task_dir = dataset_dir / "test_task"
        task_dir.mkdir()
        (task_dir / "local_task_info.yaml").write_text("task_index: 0\n")
        
        episode_dir = task_dir / "episode_0"
        episode_dir.mkdir()
        
        h5_file = episode_dir / "aligned_joints.h5"
        with h5py.File(h5_file, 'w') as f:
            f.create_dataset('state', data=np.random.rand(5, 41).astype(np.float32))
            f.create_dataset('action', data=np.random.rand(5, 20).astype(np.float32))
        
        # 所有相机配置
        all_cameras = [
            'cam_high_rgb',                   # 必需
            'cam_left_wrist_rgb',             # 必需
            'cam_right_wrist_rgb',            # 必需
            'cam_high_center_fisheye_rgb',    # 可选 - 第0帧就不存在
            'cam_back_left_fisheye_rgb',      # 可选
        ]
        
        for frame_idx in range(5):
            frame_dir = episode_dir / "camera" / str(frame_idx)
            frame_dir.mkdir(parents=True)
            
            for cam_name in all_cameras:
                # cam_high_center_fisheye_rgb 在第0帧就不创建
                if cam_name == 'cam_high_center_fisheye_rgb' and frame_idx == 0:
                    continue
                
                img = create_test_image()
                img.save(frame_dir / f"{cam_name}.jpg")
        
        (dataset_dir / "local_dataset_info.yaml").write_text("task_descriptions:\n  - test\n")
        
        config = {
            'fps': 30,
            'features': {
                'observation': {
                    'images': [
                        {'cam_name': c, 'args': {'h5_path': f'camera/{{frame_idx}}/{c}.jpg', 'file_type': 'jpg'}}
                        for c in all_cameras
                    ],
                    'state': {'sub_state': [{'names': [f'j{i}' for i in range(41)], 'args': {'h5_path': 'state', 'range_from': 0, 'range_to': 41}, 'convert_func': 'to_float32'}]}
                },
                'action': {'sub_action': [{'names': [f'a{i}' for i in range(20)], 'args': {'h5_path': 'action', 'range_from': 0, 'range_to': 20}, 'convert_func': 'to_float32'}]}
            }
        }
        
        try:
            converter = LerobotFormatConverterH5Jpg(
                dataset_path=str(dataset_dir),
                output_path=str(tmp_path / "output"),
                converter_config=config,
                repo_id="test/test",
                device_model="ruantong_a2d",
                logger=logger
            )
            
            final_cameras = [img['cam_name'] for img in converter.converter_config['features']['observation']['images']]
            logger.info(f"📋 配置的相机 (原始): {all_cameras}")
            logger.info(f"📋 最终相机列表: {final_cameras}")
            
            if 'cam_high_center_fisheye_rgb' not in final_cameras:
                logger.info("✅ cam_high_center_fisheye_rgb 已正确从配置中移除")
            else:
                logger.error("❌ cam_high_center_fisheye_rgb 未被移除!")
                return False
            
            if len(final_cameras) == 4:  # 3个必需 + 1个可选
                logger.info("✅ 场景2测试通过：可选相机第0帧缺失已正确移除\n")
                return True
            else:
                logger.error(f"❌ 相机数量不对: 期望4个，实际{len(final_cameras)}个")
                return False
            
        except Exception as e:
            logger.error(f"❌ 场景2测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_scenario_3_missing_optional_frame5(logger):
    """场景3：可选相机第5帧缺失 - 应该复制上一帧"""
    logger.info("=" * 80)
    logger.info("🧪 场景3：可选相机第5帧缺失 - 应该复制上一帧")
    logger.info("=" * 80)
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        
        task_dir = dataset_dir / "test_task"
        task_dir.mkdir()
        (task_dir / "local_task_info.yaml").write_text("task_index: 0\n")
        
        episode_dir = task_dir / "episode_0"
        episode_dir.mkdir()
        
        h5_file = episode_dir / "aligned_joints.h5"
        with h5py.File(h5_file, 'w') as f:
            f.create_dataset('state', data=np.random.rand(10, 41).astype(np.float32))
            f.create_dataset('action', data=np.random.rand(10, 20).astype(np.float32))
        
        cameras = [
            'cam_high_rgb',
            'cam_left_wrist_rgb',
            'cam_right_wrist_rgb',
            'cam_back_left_fisheye_rgb',  # 这个在第5帧会缺失
        ]
        
        # 创建特殊标记的图像（第4帧用红色）
        for frame_idx in range(10):
            frame_dir = episode_dir / "camera" / str(frame_idx)
            frame_dir.mkdir(parents=True)
            
            for cam_name in cameras:
                # cam_back_left_fisheye_rgb 在第5帧不创建
                if cam_name == 'cam_back_left_fisheye_rgb' and frame_idx == 5:
                    continue
                
                # 第4帧用特殊颜色标记
                color = (255, 0, 0) if frame_idx == 4 else (0, 255, 0)
                img = create_test_image(color=color)
                img.save(frame_dir / f"{cam_name}.jpg")
        
        (dataset_dir / "local_dataset_info.yaml").write_text("task_descriptions:\n  - test\n")
        
        config = {
            'fps': 30,
            'features': {
                'observation': {
                    'images': [
                        {'cam_name': c, 'args': {'h5_path': f'camera/{{frame_idx}}/{c}.jpg', 'file_type': 'jpg'}}
                        for c in cameras
                    ],
                    'state': {'sub_state': [{'names': [f'j{i}' for i in range(41)], 'args': {'h5_path': 'state', 'range_from': 0, 'range_to': 41}, 'convert_func': 'to_float32'}]}
                },
                'action': {'sub_action': [{'names': [f'a{i}' for i in range(20)], 'args': {'h5_path': 'action', 'range_from': 0, 'range_to': 20}, 'convert_func': 'to_float32'}]}
            }
        }
        
        try:
            converter = LerobotFormatConverterH5Jpg(
                dataset_path=str(dataset_dir),
                output_path=str(tmp_path / "output"),
                converter_config=config,
                repo_id="test/test",
                device_model="ruantong_a2d",
                logger=logger
            )
            
            task_path = list(converter.path_task_dict.keys())[0]
            images_buffer = converter._prepare_episode_images_buffer(task_path, 0)
            
            # 读取第4帧（应该是红色）
            args_dict = {
                'cam_name': 'cam_back_left_fisheye_rgb',
                'h5_path': 'camera/{frame_idx}/cam_back_left_fisheye_rgb.jpg'
            }
            img_frame4 = converter._get_frame_image(task_path, 0, 4, args_dict, images_buffer)
            logger.info(f"📸 Frame 4: {img_frame4.shape}, 平均像素值: R={img_frame4[:,:,0].mean():.1f}")
            
            # 读取第5帧（应该复制第4帧，也是红色）
            img_frame5 = converter._get_frame_image(task_path, 0, 5, args_dict, images_buffer)
            logger.info(f"📸 Frame 5 (复制): {img_frame5.shape}, 平均像素值: R={img_frame5[:,:,0].mean():.1f}")
            
            # 检查是否复制成功（第5帧应该和第4帧一样是红色）
            if np.array_equal(img_frame4, img_frame5):
                logger.info("✅ 第5帧成功复制第4帧的数据")
                logger.info("✅ 场景3测试通过：可选相机某帧缺失成功复制上一帧\n")
                return True
            else:
                logger.error("❌ 第5帧数据与第4帧不一致")
                return False
            
        except Exception as e:
            logger.error(f"❌ 场景3测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """主函数"""
    logger = setup_logger()
    
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "软通容错机制演示测试" + " " * 32 + "║")
    print("╚" + "═" * 78 + "╝")
    print()
    
    results = []
    
    # 场景1：正常场景
    results.append(("场景1: 所有相机都存在", test_scenario_1_normal(logger)))
    
    # 场景2：可选相机第0帧缺失
    results.append(("场景2: 可选相机第0帧缺失", test_scenario_2_missing_optional_frame0(logger)))
    
    # 场景3：可选相机第5帧缺失
    results.append(("场景3: 可选相机第5帧缺失", test_scenario_3_missing_optional_frame5(logger)))
    
    # 汇总结果
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 30 + "测试结果汇总" + " " * 34 + "║")
    print("╠" + "═" * 78 + "╣")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for scenario, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"║  {status}  {scenario:<65}  ║")
    
    print("╠" + "═" * 78 + "╣")
    print(f"║  总计: {passed_count}/{total_count} 通过" + " " * (64 - len(f"总计: {passed_count}/{total_count} 通过")) + "║")
    print("╚" + "═" * 78 + "╝")
    print()
    
    return 0 if passed_count == total_count else 1


if __name__ == '__main__':
    sys.exit(main())

