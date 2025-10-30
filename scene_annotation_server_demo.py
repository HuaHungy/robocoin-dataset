#!/usr/bin/env python3
"""
场景标注服务器Demo
启动一个场景标注服务器，等待客户端连接并处理任务
"""

import sys
import os
import asyncio
import logging

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from robocoin_dataset.annotation.scene_annotation.scene_annotation import SceneAnnotationServer


def main():
    """启动场景标注服务器"""
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 数据库文件路径
    db_file_path = "/home/diy02/下载/datasets.db"
    
    # 输出目录
    output_dir = "/tmp/scene_annotations"
    
    # 创建服务器实例
    server = SceneAnnotationServer(
        db_file_path=db_file_path,
        output_dir=output_dir,
        host="0.0.0.0",
        port=8770,
    )
    
    print(f"启动场景标注服务器...")
    print(f"数据库: {db_file_path}")
    print(f"输出目录: {output_dir}")
    print(f"监听地址: 0.0.0.0:8770")
    print("等待客户端连接...")
    
    try:
        # 启动服务器
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        print(f"服务器启动失败: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())