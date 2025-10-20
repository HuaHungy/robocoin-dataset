#!/usr/bin/env python3
"""
测试银河预验证器的帧数一致性检查

创建一个模拟的episode来测试不同的帧数场景
"""

import json
import tempfile
import shutil
from pathlib import Path

def create_test_episode(episode_dir: Path, json_frame_count: int, video_note: str = ""):
    """创建测试episode"""
    episode_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建 data.json
    data = {
        "data": {
            "state_body_joint_position": [[0, 0, 0]] * json_frame_count,
            "state_left_arm_joint_position": [[0]*7] * json_frame_count,
            "state_right_arm_joint_position": [[0]*7] * json_frame_count,
            "cmd_left_joint_state": [[0]*7] * json_frame_count,
            "cmd_right_joint_state": [[0]*7] * json_frame_count,
        }
    }
    
    with open(episode_dir / "data.json", 'w') as f:
        json.dump(data, f)
    
    # 创建空的视频文件（模拟）
    for video_name in ["camera_front_head_rgb.mp4", "camera_left_wrist.mp4", "camera_right_wrist.mp4"]:
        (episode_dir / video_name).touch()
    
    # 创建report.txt
    (episode_dir / "report.txt").write_text(f"Test episode with {json_frame_count} JSON frames {video_note}")
    
    print(f"✅ 创建测试episode: {episode_dir.name}")
    print(f"   JSON帧数: {json_frame_count}")
    print(f"   备注: {video_note}")

def main():
    print("🧪 银河预验证器 - 帧数一致性检查测试\n")
    print("="*70)
    
    # 创建临时测试目录
    test_root = Path(tempfile.mkdtemp(prefix="yinhe_test_"))
    print(f"📁 临时测试目录: {test_root}\n")
    
    try:
        # 场景1: 正常episode（所有帧数一致）
        task1 = test_root / "test_task" / "robot_001"
        create_test_episode(
            task1 / "20250101_record1",
            json_frame_count=100,
            video_note="(正常：所有100帧)"
        )
        
        # 场景2: 轻微不一致（<10%差异）
        create_test_episode(
            task1 / "20250101_record2", 
            json_frame_count=105,
            video_note="(轻微不一致：JSON 105帧 vs 视频100帧)"
        )
        
        # 场景3: 严重不一致（>10%差异）
        create_test_episode(
            task1 / "20250101_record3",
            json_frame_count=150,
            video_note="(严重不一致：JSON 150帧 vs 视频100帧)"
        )
        
        # 场景4: JSON字段之间帧数不一致
        episode4 = task1 / "20250101_record4"
        episode4.mkdir(parents=True, exist_ok=True)
        
        data4 = {
            "data": {
                "state_body_joint_position": [[0, 0, 0]] * 100,
                "state_left_arm_joint_position": [[0]*7] * 100,
                "state_right_arm_joint_position": [[0]*7] * 50,  # ⚠️ 只有50帧
                "cmd_left_joint_state": [[0]*7] * 100,
                "cmd_right_joint_state": [[0]*7] * 100,
            }
        }
        
        with open(episode4 / "data.json", 'w') as f:
            json.dump(data4, f)
        
        for video_name in ["camera_front_head_rgb.mp4", "camera_left_wrist.mp4", "camera_right_wrist.mp4"]:
            (episode4 / video_name).touch()
        
        (episode4 / "report.txt").write_text("Test episode with inconsistent JSON fields")
        
        print(f"✅ 创建测试episode: {episode4.name}")
        print(f"   JSON帧数不一致: body=100, left_arm=100, right_arm=50")
        
        print("\n" + "="*70)
        print("📋 测试场景总结:")
        print("  1. 正常episode: JSON 100帧")
        print("  2. 轻微不一致: JSON 105帧 (差异5%, 应为Warning)")
        print("  3. 严重不一致: JSON 150帧 (差异33%, 应为Error)")
        print("  4. JSON内部不一致: right_arm只有50帧 (差异50%, 应为Error)")
        
        print("\n" + "="*70)
        print("🚀 运行验证器测试...")
        print(f"\n命令:")
        print(f"  python3 scripts/dataset_statistics/yinhe_preconversion_validator_v2.py \\")
        print(f"    --dataset-path {test_root} \\")
        print(f"    --verbose")
        
        print("\n💡 预期结果:")
        print("  ✅ Episode 1: 通过")
        print("  ⚠️  Episode 2: 通过但有警告 (轻微不一致<10%)")
        print("  ❌ Episode 3: 失败 (严重不一致>10%)")
        print("  ❌ Episode 4: 失败 (JSON字段帧数不一致)")
        
        print("\n📂 测试文件保留在: " + str(test_root))
        print("   测试完成后请手动删除")
        
    except Exception as e:
        print(f"\n❌ 测试设置失败: {e}")
        shutil.rmtree(test_root, ignore_errors=True)
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
