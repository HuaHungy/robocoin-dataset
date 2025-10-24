#!/usr/bin/env python3
"""
Ruantong GT01 No Depth相机一致性检查工具

检查配置文件中的相机列表与实际数据是否匹配
"""

import json
import sys
import yaml
from pathlib import Path
from typing import Dict, Set, List

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / 'src'))


def get_config_cameras(config_path: Path) -> Set[str]:
    """从配置文件中获取相机列表
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        相机名称集合
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    cameras = set()
    if 'features' in config and 'observation' in config['features']:
        if 'images' in config['features']['observation']:
            for img in config['features']['observation']['images']:
                cameras.add(img['cam_name'])
    
    return cameras


def get_actual_cameras(task_dir: Path) -> Dict[str, List[str]]:
    """从实际数据中获取相机列表
    
    Args:
        task_dir: Task目录路径
        
    Returns:
        字典，key为帧号，value为相机名称列表
    """
    camera_base_dir = task_dir / "camera"
    
    if not camera_base_dir.exists():
        return {}
    
    frame_cameras = {}
    
    # 检查前10帧
    for frame_dir in sorted(camera_base_dir.iterdir())[:10]:
        if not frame_dir.is_dir():
            continue
        
        cameras = []
        for img_file in frame_dir.iterdir():
            if img_file.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                # 相机名是文件名（去除扩展名）
                cam_name = img_file.stem
                cameras.append(cam_name)
        
        frame_cameras[frame_dir.name] = sorted(cameras)
    
    return frame_cameras


def check_camera_consistency(dataset_path: Path, config_path: Path) -> Dict:
    """检查配置文件与实际数据的相机一致性
    
    Args:
        dataset_path: 数据集根目录
        config_path: 配置文件路径
        
    Returns:
        检查结果字典
    """
    print(f"🔍 检查相机一致性")
    print(f"   数据集: {dataset_path}")
    print(f"   配置:   {config_path}\n")
    
    # 1. 读取配置中的相机
    print("📋 读取配置文件...")
    config_cameras = get_config_cameras(config_path)
    print(f"   配置中的相机 ({len(config_cameras)}):")
    for cam in sorted(config_cameras):
        print(f"      - {cam}")
    
    # 2. 读取实际数据中的相机
    print("\n📂 读取实际数据...")
    
    # 查找所有task目录
    task_dirs = []
    for path in dataset_path.iterdir():
        if path.is_dir() and path.name.isdigit():  # Ruantong的task目录是数字
            task_dirs.append(path)
    
    if not task_dirs:
        # 尝试查找带local_task_info.yaml的目录
        for path in dataset_path.iterdir():
            if path.is_dir() and (path / "local_task_info.yaml").exists():
                task_dirs.append(path)
    
    print(f"   找到 {len(task_dirs)} 个task目录")
    
    all_actual_cameras = set()
    task_results = []
    
    for task_dir in sorted(task_dirs):
        print(f"\n   检查task: {task_dir.name}")
        frame_cameras = get_actual_cameras(task_dir)
        
        if not frame_cameras:
            print(f"      ⚠️  未找到camera目录或无图像文件")
            continue
        
        # 取第一帧的相机列表作为参考
        first_frame = min(frame_cameras.keys(), key=int)
        cameras_in_frame = set(frame_cameras[first_frame])
        all_actual_cameras.update(cameras_in_frame)
        
        print(f"      帧0的相机 ({len(cameras_in_frame)}):")
        for cam in sorted(cameras_in_frame):
            print(f"         - {cam}")
        
        # 检查所有帧的相机是否一致
        inconsistent_frames = []
        for frame, cams in frame_cameras.items():
            if set(cams) != cameras_in_frame:
                inconsistent_frames.append(frame)
        
        if inconsistent_frames:
            print(f"      ⚠️  帧间相机不一致: 帧 {', '.join(inconsistent_frames[:5])}")
        
        task_results.append({
            "task_dir": task_dir.name,
            "frame_cameras": frame_cameras,
            "cameras_in_first_frame": list(cameras_in_frame),
            "inconsistent_frames": inconsistent_frames
        })
    
    # 3. 对比分析
    print("\n" + "="*70)
    print("📊 对比结果")
    print("="*70)
    
    missing_in_data = config_cameras - all_actual_cameras
    missing_in_config = all_actual_cameras - config_cameras
    matched = config_cameras & all_actual_cameras
    
    print(f"\n✅ 匹配的相机 ({len(matched)}):")
    for cam in sorted(matched):
        print(f"   - {cam}")
    
    if missing_in_data:
        print(f"\n❌ 配置中有但数据中没有 ({len(missing_in_data)}):")
        for cam in sorted(missing_in_data):
            print(f"   - {cam}")
    
    if missing_in_config:
        print(f"\n⚠️  数据中有但配置中没有 ({len(missing_in_config)}):")
        for cam in sorted(missing_in_config):
            print(f"   - {cam}")
    
    if not missing_in_data and not missing_in_config:
        print("\n🎉 配置与数据完全匹配！")
    else:
        print("\n💡 建议修复配置文件:")
        if missing_in_config:
            print("\n   需要添加到配置:")
            for cam in sorted(missing_in_config):
                print(f"      - cam_name: {cam}")
                print(f"        args:")
                file_type = "jpg"  # 默认
                # 检查实际文件类型
                for task_result in task_results:
                    if cam in task_result['cameras_in_first_frame']:
                        task_dir = dataset_path / task_result['task_dir']
                        camera_dir = task_dir / "camera" / "0"
                        for img_file in camera_dir.glob(f"{cam}.*"):
                            file_type = img_file.suffix[1:]  # 去除点号
                            break
                        break
                print(f"          file_type: {file_type}")
                print()
        
        if missing_in_data:
            print("   需要从配置中删除:")
            for cam in sorted(missing_in_data):
                print(f"      - {cam}")
    
    # 返回结果
    return {
        "config_path": str(config_path),
        "dataset_path": str(dataset_path),
        "config_cameras": sorted(list(config_cameras)),
        "actual_cameras": sorted(list(all_actual_cameras)),
        "matched_cameras": sorted(list(matched)),
        "missing_in_data": sorted(list(missing_in_data)),
        "missing_in_config": sorted(list(missing_in_config)),
        "is_consistent": len(missing_in_data) == 0 and len(missing_in_config) == 0,
        "task_results": task_results
    }


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="检查Ruantong GT01相机一致性")
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=Path("/home/liu/program/robocoin-dataset/data/ruantong_a2d:gt01_no_depth"),
        help="数据集路径"
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=Path("/home/liu/program/robocoin-dataset/scripts/format_converters/tolerobot/configs/converter_config_ruantong_gt01_no_depth.yaml"),
        help="配置文件路径"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ruantong_gt01_camera_consistency.json"),
        help="输出报告路径"
    )
    
    args = parser.parse_args()
    
    if not args.dataset_path.exists():
        print(f"❌ 数据集路径不存在: {args.dataset_path}")
        return 1
    
    if not args.config_path.exists():
        print(f"❌ 配置文件不存在: {args.config_path}")
        return 1
    
    # 检查相机一致性
    result = check_camera_consistency(args.dataset_path, args.config_path)
    
    # 保存结果
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 详细报告已保存: {args.output}")
    
    # 返回状态码
    if not result["is_consistent"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

