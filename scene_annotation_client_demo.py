#!/usr/bin/env python3
"""
场景标注客户端Demo
连接到场景标注服务器并请求处理任务
"""

import sys
import os
import asyncio
import logging

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from robocoin_dataset.annotation.scene_annotation.scene_annotation import SceneAnnotationClient


def main():
    """启动场景标注客户端"""
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 服务器地址
    server_uri = "ws://localhost:8770"
    
    # 创建客户端实例
    client = SceneAnnotationClient(
        server_uri=server_uri,
        heartbeat_interval=10.0,
    )
    
    print(f"启动场景标注客户端...")
    print(f"连接服务器: {server_uri}")
    print("开始请求任务...")
    
    try:
        # 启动客户端
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\n客户端已停止")
    except Exception as e:
        print(f"客户端连接失败: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())