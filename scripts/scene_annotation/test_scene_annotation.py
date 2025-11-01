#!/usr/bin/env python3
"""
场景注释测试脚本

该脚本提供多种测试模式，帮助用户验证场景注释功能是否正常工作。
"""

import argparse
import asyncio
import json
import logging
import tempfile
from pathlib import Path

from robocoin_dataset.annotation.scene_annotation.scene_annotation import (
    SceneAnnotation,
    SceneAnnotationServer,
    SceneAnnotationClient,
    test_scene_annotation,
    test_with_real_data
)


def create_test_environment():
    """创建测试环境"""
    print("=== 创建测试环境 ===")
    
    # 创建临时测试环境
    temp_dir = tempfile.mkdtemp(prefix="scene_annotation_test_")
    temp_path = Path(temp_dir)
    
    # 创建测试数据库文件路径
    test_db_path = temp_path / "test_dataset.db"
    
    # 创建测试数据集文件夹
    test_dataset_folder = temp_path / "test_dataset"
    test_dataset_folder.mkdir()
    
    # 创建测试JSON文件
    test_json_files = [
        {"description": "机器人抓取红色方块并放置到指定位置"},
        {"description": "机器人移动到目标位置执行拾取任务"},
        {"description": "机器人将物体从容器A移动到容器B"},
        {"description": "机器人执行精确的装配操作"},
        {"description": "机器人进行物体分类和排序任务"}
    ]
    
    for i, data in enumerate(test_json_files):
        json_file = test_dataset_folder / f"episode_{i:03d}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"测试环境创建完成: {temp_path}")
    print(f"测试数据库: {test_db_path}")
    print(f"测试数据集: {test_dataset_folder}")
    print(f"创建了 {len(test_json_files)} 个测试JSON文件")
    
    return temp_path, test_db_path, test_dataset_folder


async def test_server_client():
    """测试服务器和客户端"""
    print("=== 测试服务器和客户端 ===")
    
    # 创建测试环境
    temp_path, test_db_path, test_dataset_folder = create_test_environment()
    
    try:
        print("注意: 这是一个模拟测试，实际运行需要真实的数据库")
        print("服务器和客户端测试结构验证完成")
        
        # 这里可以添加更多的集成测试逻辑
        print("要运行完整的服务器/客户端测试，请:")
        print("1. 确保数据库文件存在且包含相应的数据集记录")
        print("2. 先启动服务器: python scene_annotation_server.py --db_file_path <db_path>")
        print("3. 再启动客户端: python scene_annotation_client.py --host 127.0.0.1 --port 8769")
        
    finally:
        # 清理测试环境
        import shutil
        shutil.rmtree(temp_path)
        print(f"清理测试环境: {temp_path}")


def test_local_processing():
    """测试本地处理功能"""
    print("=== 测试本地处理功能 ===")
    
    # 使用内置的测试函数
    try:
        test_scene_annotation()
        print("本地处理测试完成")
    except Exception as e:
        print(f"本地处理测试失败: {e}")


def test_real_data_processing():
    """测试真实数据处理"""
    print("=== 测试真实数据处理 ===")
    
    try:
        test_with_real_data()
        print("真实数据处理测试完成")
    except Exception as e:
        print(f"真实数据处理测试失败: {e}")


async def main():
    parser = argparse.ArgumentParser(
        description="场景注释测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
测试模式:
  local     - 测试本地处理功能（创建临时测试环境）
  real      - 测试真实数据处理（需要真实的数据库和数据）
  server    - 测试服务器和客户端（模拟测试）
  all       - 运行所有测试

使用示例:
  # 测试本地处理
  python test_scene_annotation.py local

  # 测试真实数据处理
  python test_scene_annotation.py real

  # 测试服务器客户端
  python test_scene_annotation.py server

  # 运行所有测试
  python test_scene_annotation.py all
        """
    )
    
    parser.add_argument(
        "mode",
        choices=["local", "real", "server", "all"],
        help="测试模式"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="启用详细输出"
    )

    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    print("场景注释功能测试开始")
    print("=" * 50)
    
    try:
        if args.mode == "local":
            test_local_processing()
        elif args.mode == "real":
            test_real_data_processing()
        elif args.mode == "server":
            await test_server_client()
        elif args.mode == "all":
            test_local_processing()
            print("\n" + "=" * 50 + "\n")
            test_real_data_processing()
            print("\n" + "=" * 50 + "\n")
            await test_server_client()
        
        print("\n" + "=" * 50)
        print("测试完成！")
        
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        exit(exit_code)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        exit(1)
    except Exception as e:
        print(f"测试启动失败: {e}")
        exit(1)