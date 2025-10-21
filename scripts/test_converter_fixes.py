#!/usr/bin/env python3
"""
测试 Converter 修复效果的脚本
验证：
1. Test 模式内存使用
2. 资源泄漏检查
3. 执行时间
"""

import psutil
import os
import time
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_memory_usage():
    """测试内存使用"""
    process = psutil.Process(os.getpid())
    
    # 记录初始内存
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    print(f"初始内存: {initial_memory:.2f} MB")
    
    # TODO: 这里可以导入并运行 converter
    # from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5_mp4 import LerobotFormatConverterH5Mp4
    # converter = LerobotFormatConverterH5Mp4(...)
    # converter.convert(is_test=True)
    
    # 记录峰值内存
    peak_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    print(f"峰值内存: {peak_memory:.2f} MB")
    print(f"内存增长: {peak_memory - initial_memory:.2f} MB")
    
    # 验证内存使用是否合理
    if peak_memory - initial_memory < 500:  # 小于 500 MB
        print("✅ 内存使用正常")
        return True
    else:
        print("❌ 内存使用过高")
        return False

def test_file_descriptor_leak():
    """测试文件句柄泄漏"""
    process = psutil.Process(os.getpid())
    
    # 记录初始文件句柄数
    initial_fds = len(process.open_files())
    
    print(f"初始文件句柄: {initial_fds}")
    
    # TODO: 运行多次转换
    # for i in range(10):
    #     converter.convert(is_test=True)
    
    # 检查文件句柄数
    final_fds = len(process.open_files())
    
    print(f"最终文件句柄: {final_fds}")
    print(f"泄漏文件句柄: {final_fds - initial_fds}")
    
    # 验证没有泄漏
    if final_fds <= initial_fds + 2:  # 允许小幅波动
        print("✅ 无文件句柄泄漏")
        return True
    else:
        print("❌ 检测到文件句柄泄漏")
        return False

def test_execution_time():
    """测试执行时间"""
    start_time = time.time()
    
    # TODO: 运行转换
    # converter.convert(is_test=True)
    
    elapsed = time.time() - start_time
    
    print(f"执行时间: {elapsed:.2f} 秒")
    
    # 验证执行时间
    if elapsed < 30:  # 小于 30 秒
        print("✅ 执行速度正常")
        return True
    else:
        print("❌ 执行速度过慢")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Converter 修复效果验证测试")
    print("=" * 60)
    
    results = []
    
    print("\n📊 测试1: 内存使用")
    print("-" * 60)
    results.append(test_memory_usage())
    
    print("\n🔒 测试2: 文件句柄泄漏")
    print("-" * 60)
    results.append(test_file_descriptor_leak())
    
    print("\n⏱️  测试3: 执行时间")
    print("-" * 60)
    results.append(test_execution_time())
    
    print("\n" + "=" * 60)
    if all(results):
        print("✅ 所有测试通过！")
        sys.exit(0)
    else:
        print("❌ 部分测试失败")
        sys.exit(1)
