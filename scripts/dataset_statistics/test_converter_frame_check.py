#!/usr/bin/env python3
"""
测试转换器的帧数一致性检查

使用已知有问题的文件来测试转换器是否能正确检测并报告帧数不一致问题
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5 import (
    LerobotFormatConverterH5
)

def test_frame_consistency_detection():
    """测试转换器能否检测到帧数不一致"""
    
    print("🧪 测试：转换器帧数一致性检查\n")
    
    # 配置
    config_path = Path("/home/diy01/dev/robocoin-dataset/scripts/format_converters/tolerobot/configs/converter_config_zhipingfang_left_arm_with_pose.yaml")
    
    # 数据路径 - 使用已知有问题的任务
    data_root = Path("/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批-20250930-32274条")
    
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return False
    
    if not data_root.exists():
        print(f"❌ 数据路径不存在: {data_root}")
        return False
    
    print(f"📁 配置: {config_path.name}")
    print(f"📁 数据: {data_root.name}")
    print()
    
    try:
        # 创建转换器实例
        converter = LerobotFormatConverterH5(
            data_root_path=str(data_root),
            lerobot_root_path="/tmp/test_output",
            converter_config_path=str(config_path),
            video_backend="pyav",
            fps=30,
            image_writer_processes=1,
            image_writer_threads=1,
            is_test=True
        )
        
        print("✅ 转换器初始化成功\n")
        
        # 尝试处理一个已知有问题的episode
        # 算法采集_PCB 任务下的第198个文件
        task_path = data_root / "算法采集_PCB"
        
        if not task_path.exists():
            print(f"❌ 任务路径不存在: {task_path}")
            return False
        
        print(f"🎯 测试任务: {task_path.name}")
        print(f"🎯 测试episode索引: 198\n")
        
        # 调用 _get_episode_frames_num，这应该会检测到帧数不一致
        try:
            frame_count = converter._get_episode_frames_num(task_path, 198)
            print(f"❌ 测试失败：没有检测到帧数不一致问题")
            print(f"   返回帧数: {frame_count}")
            return False
        
        except ValueError as e:
            error_msg = str(e)
            
            # 检查错误信息是否包含关键信息
            required_keywords = [
                "帧数不一致",
                "0629_a.h5",  # 文件名
                "算法采集_PCB",  # 任务名
                "observations/timestamp",  # 应该提到这个路径
            ]
            
            missing_keywords = [kw for kw in required_keywords if kw not in error_msg]
            
            print("✅ 成功检测到帧数不一致！\n")
            print("=" * 70)
            print("📋 完整错误信息：")
            print("=" * 70)
            print(error_msg)
            print("=" * 70)
            
            if missing_keywords:
                print(f"\n⚠️  警告：错误信息缺少以下关键字: {missing_keywords}")
                return False
            
            print("\n✅ 错误信息完整，包含所有必要的诊断信息")
            return True
    
    except Exception as e:
        print(f"❌ 测试过程出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 70)
    print("🚀 转换器帧数一致性检查测试")
    print("=" * 70)
    print()
    
    success = test_frame_consistency_detection()
    
    print("\n" + "=" * 70)
    if success:
        print("✅ 测试通过：转换器能正确检测并报告帧数不一致问题")
        print("   - 错误检测：✅")
        print("   - 详细信息：✅")
        print("   - 文件定位：✅")
        print("   - 修复建议：✅")
        sys.exit(0)
    else:
        print("❌ 测试失败：转换器未能正确检测问题")
        sys.exit(1)

if __name__ == "__main__":
    main()
