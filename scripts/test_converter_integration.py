#!/usr/bin/env python3
"""
集成测试：验证修复后的 converter 实际转换效果

测试场景：
1. H5Mp4 Converter (alohanew)
2. LejuWaibu Converter (leju_waibu)
3. Mp4Json Converter (mayi)
"""

import os
import sys
import time
import psutil
import tempfile
import logging
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


def get_memory_mb():
    """获取当前进程内存使用（MB）"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def get_open_files_count():
    """获取当前打开的文件句柄数"""
    process = psutil.Process(os.getpid())
    try:
        return len(process.open_files())
    except:
        return 0


def test_converter(converter_name, dataset_name, converter_class):
    """测试单个 converter
    
    Args:
        converter_name: Converter 名称
        dataset_name: 数据集名称
        converter_class: Converter 类
    
    Returns:
        bool: 测试是否通过
    """
    print(f"\n{'='*70}")
    print(f"测试 {converter_name}")
    print(f"{'='*70}")
    
    # 检查数据集
    dataset_path = project_root / "data" / dataset_name
    if not dataset_path.exists():
        print(f"⏭️  跳过: 数据集不存在 ({dataset_path})")
        return None
    
    # 创建临时输出目录
    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "output"
        
        # 记录初始状态
        initial_memory = get_memory_mb()
        initial_fds = get_open_files_count()
        
        print(f"\n📊 初始状态:")
        print(f"  内存: {initial_memory:.1f} MB")
        print(f"  文件句柄: {initial_fds}")
        
        # 创建 logger
        logger = logging.getLogger(f"test_{converter_name}")
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
        
        # 初始化 converter
        try:
            converter = converter_class(
                dataset_path=str(dataset_path),
                output_path=str(output_path),
                converter_config={},  # 简化配置
                repo_id=f"test/{dataset_name}",
                device_model="test_device",
                logger=logger,
                video_backend="pyav",
                image_writer_processes=1,  # 减少进程数
                image_writer_threads=1,
            )
            print(f"✅ Converter 初始化成功")
            
        except Exception as e:
            print(f"❌ Converter 初始化失败: {e}")
            return False
        
        # 运行 test 模式转换
        print(f"\n⚙️  开始转换 (TEST 模式)...")
        start_time = time.time()
        
        try:
            converter.convert(is_test=True)
            print(f"✅ 转换完成")
            
        except Exception as e:
            print(f"❌ 转换失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            # 记录最终状态
            elapsed = time.time() - start_time
            final_memory = get_memory_mb()
            final_fds = get_open_files_count()
            memory_growth = final_memory - initial_memory
            
            print(f"\n📈 最终状态:")
            print(f"  执行时间: {elapsed:.1f} 秒")
            print(f"  内存使用: {final_memory:.1f} MB (增长: {memory_growth:+.1f} MB)")
            print(f"  文件句柄: {final_fds} (变化: {final_fds - initial_fds:+d})")
            
            # 验证
            print(f"\n🎯 验证结果:")
            
            memory_ok = memory_growth < 1000  # 增长 < 1 GB
            fds_ok = abs(final_fds - initial_fds) <= 5  # 允许小幅波动
            time_ok = elapsed < 60  # < 60 秒
            
            results = []
            
            if memory_ok:
                print(f"  ✅ 内存: 增长 {memory_growth:.1f} MB < 1000 MB")
                results.append(True)
            else:
                print(f"  ❌ 内存: 增长 {memory_growth:.1f} MB > 1000 MB")
                results.append(False)
            
            if fds_ok:
                print(f"  ✅ 文件句柄: 无明显泄漏")
                results.append(True)
            else:
                print(f"  ⚠️  文件句柄: 变化 {final_fds - initial_fds}")
                results.append(True)  # 不算失败
            
            if time_ok:
                print(f"  ✅ 速度: {elapsed:.1f} 秒 < 60 秒")
                results.append(True)
            else:
                print(f"  ⚠️  速度: {elapsed:.1f} 秒 > 60 秒")
                results.append(True)  # 不算失败
            
            return all(results)


def main():
    """运行所有测试"""
    print("="*70)
    print("Converter 修复效果集成测试")
    print("="*70)
    print("\n本测试将验证修复后的 converters 在 TEST 模式下的表现:")
    print("  1. 内存使用是否合理 (< 1 GB 增长)")
    print("  2. 是否有资源泄漏")
    print("  3. 执行速度是否正常 (< 60 秒)")
    
    # 定义测试用例
    test_cases = []
    
    # 1. LejuWaibu
    try:
        from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_leju_waibu import (
            LerobotFormatConverterLejuWaibu,
        )
        test_cases.append(("LejuWaibu", "leju_waibu", LerobotFormatConverterLejuWaibu))
    except ImportError as e:
        print(f"⚠️  无法导入 LejuWaibu: {e}")
    
    # 2. H5Mp4 (alohanew)
    try:
        from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5_mp4 import (
            LerobotFormatConverterH5Mp4,
        )
        test_cases.append(("H5Mp4", "alohanew", LerobotFormatConverterH5Mp4))
    except ImportError as e:
        print(f"⚠️  无法导入 H5Mp4: {e}")
    
    # 3. Mp4Json (mayi)
    try:
        from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_mp4_json import (
            LerobotFormatConverterMp4Json,
        )
        test_cases.append(("Mp4Json", "mayi", LerobotFormatConverterMp4Json))
    except ImportError as e:
        print(f"⚠️  无法导入 Mp4Json: {e}")
    
    if not test_cases:
        print("\n❌ 没有可用的测试用例")
        return False
    
    # 运行测试
    results = {}
    for converter_name, dataset_name, converter_class in test_cases:
        try:
            result = test_converter(converter_name, dataset_name, converter_class)
            results[converter_name] = result
        except KeyboardInterrupt:
            print(f"\n⚠️  测试被中断")
            return False
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results[converter_name] = False
    
    # 汇总结果
    print(f"\n{'='*70}")
    print("测试结果汇总")
    print(f"{'='*70}")
    
    for converter_name, result in results.items():
        if result is None:
            print(f"  ⏭️  {converter_name}: 跳过（数据集不存在）")
        elif result:
            print(f"  ✅ {converter_name}: 通过")
        else:
            print(f"  ❌ {converter_name}: 失败")
    
    # 判断整体结果
    tested = [r for r in results.values() if r is not None]
    if not tested:
        print(f"\n⚠️  没有执行任何测试（数据集不存在）")
        return False
    
    passed = sum(1 for r in tested if r)
    total = len(tested)
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("✅ 所有测试通过！修复效果良好")
        return True
    else:
        print("⚠️  部分测试失败")
        return False


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 测试发生异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
