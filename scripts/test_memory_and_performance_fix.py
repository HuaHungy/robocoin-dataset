#!/usr/bin/env python3
"""
测试内存泄漏和性能优化修复

测试内容:
1. MCAP内存泄漏修复
2. Episode查找性能优化
"""

import sys
import time
from pathlib import Path
import psutil
import os

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_episode_finder_performance():
    """测试Episode查找性能"""
    print("="*80)
    print("测试1: Episode查找性能对比")
    print("="*80)
    
    from robocoin_dataset.format_converter.tolerobot.episode_finder import EpisodeFinder
    
    # 测试数据集路径（请根据实际情况修改）
    test_cases = [
        {
            "name": "银河(Yinhe)",
            "path": "/mnt/nas/synnas/docker/外部数据/银河通用",
            "device_model": "yinhe",
            "extensions": [".json"],
        },
        {
            "name": "乐聚(Leju)",
            "path": "/mnt/nas/synnas/docker2/外部数据/乐聚2",
            "device_model": "leju_robot",
            "extensions": [".hdf5"],
        },
        {
            "name": "软通(Ruantong)",
            "path": "/mnt/nas/synnas/docker/8ruantong_a2d",
            "device_model": "ruantong_a2d",
            "extensions": [".hdf5"],
        },
    ]
    
    for test_case in test_cases:
        task_path = Path(test_case["path"])
        
        if not task_path.exists():
            print(f"⏭️  跳过 {test_case['name']}: 路径不存在")
            continue
        
        print(f"\n{'='*60}")
        print(f"📊 测试: {test_case['name']}")
        print(f"📁 路径: {task_path}")
        print(f"{'='*60}")
        
        # 测试规则匹配（新方法）
        print("\n⚡ 方法1: 规则匹配（EpisodeFinder）")
        finder = EpisodeFinder(
            device_model=test_case["device_model"],
            logger=None,
            enable_recursive_fallback=False,  # 禁用递归fallback
        )
        
        start = time.time()
        try:
            files_fast = finder.find_episode_files(
                task_path=task_path,
                file_extensions=test_case["extensions"],
            )
            elapsed_fast = time.time() - start
            print(f"   ✅ 找到 {len(files_fast)} 个episodes")
            print(f"   ⏱️  耗时: {elapsed_fast:.2f} 秒")
        except Exception as e:
            elapsed_fast = None
            print(f"   ❌ 失败: {e}")
        
        # 测试递归搜索（旧方法）
        print("\n🐌 方法2: 递归搜索（rglob）")
        start = time.time()
        try:
            files_slow = []
            for ext in test_case["extensions"]:
                files_slow.extend(list(task_path.rglob(f"*{ext}")))
            # 过滤隐藏目录
            files_slow = [f for f in files_slow if not any(part.startswith('.') or part.startswith('@') for part in f.parts)]
            elapsed_slow = time.time() - start
            print(f"   ✅ 找到 {len(files_slow)} 个episodes")
            print(f"   ⏱️  耗时: {elapsed_slow:.2f} 秒")
        except Exception as e:
            elapsed_slow = None
            print(f"   ❌ 失败: {e}")
        
        # 性能对比
        if elapsed_fast and elapsed_slow:
            speedup = elapsed_slow / elapsed_fast
            print(f"\n🎯 性能提升: {speedup:.1f}x faster! 🚀")
            print(f"   节省时间: {elapsed_slow - elapsed_fast:.1f} 秒")
        
        print()


def test_mcap_memory_leak():
    """测试MCAP内存泄漏修复"""
    print("="*80)
    print("测试2: MCAP内存泄漏修复")
    print("="*80)
    
    # 获取当前进程
    process = psutil.Process(os.getpid())
    
    # 记录初始内存
    initial_memory = process.memory_info().rss / (1024 ** 3)  # GB
    print(f"\n📊 初始内存: {initial_memory:.2f} GB")
    
    try:
        from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_mcap import LerobotFormatConverterMcap
        
        # 测试路径（请根据实际情况修改）
        test_dataset_path = Path("/mnt/nas/synnas/docker/11realman_rmc_aidal")
        
        if not test_dataset_path.exists():
            print("⏭️  跳过MCAP测试: 路径不存在")
            return
        
        print(f"📁 测试数据集: {test_dataset_path}")
        
        # 创建转换器
        converter = LerobotFormatConverterMcap(
            dataset_path=test_dataset_path,
            output_path=Path("/tmp/test_output"),
            converter_config_path=Path("scripts/format_converters/tolerobot/configs/converter_config_realman_rmc_aidal_mcap.yaml"),
            device_model="realman_rmc_aidal",
            logger=None,
        )
        
        # 模拟转换前3个episodes并检查内存
        print("\n🔄 模拟转换episodes (测试内存管理)...")
        
        for i in range(min(3, converter.get_total_episodes_num())):
            print(f"\n--- Episode {i} ---")
            
            # 记录episode前内存
            before_memory = process.memory_info().rss / (1024 ** 3)
            print(f"   转换前内存: {before_memory:.2f} GB")
            
            # 模拟episode数据加载
            try:
                task_path = list(converter.dataset_path.iterdir())[0]
                if hasattr(converter, '_get_episode_data'):
                    _ = converter._get_episode_data(task_path, i)
                    print(f"   ✅ Episode {i} 数据加载完成")
                
                # 调用缓存清理（如果存在）
                if hasattr(converter, '_clear_episode_cache'):
                    converter._clear_episode_cache()
                    print(f"   🧹 缓存已清理")
                else:
                    print(f"   ⚠️  未找到_clear_episode_cache方法")
                
            except Exception as e:
                print(f"   ❌ Episode {i} 失败: {e}")
            
            # 记录episode后内存
            after_memory = process.memory_info().rss / (1024 ** 3)
            print(f"   转换后内存: {after_memory:.2f} GB")
            print(f"   内存变化: {after_memory - before_memory:+.2f} GB")
        
        # 最终内存
        final_memory = process.memory_info().rss / (1024 ** 3)
        print(f"\n📊 最终内存: {final_memory:.2f} GB")
        print(f"📊 总内存增长: {final_memory - initial_memory:+.2f} GB")
        
        # 判断内存泄漏
        if final_memory - initial_memory > 1.0:  # 增长超过1GB视为泄漏
            print("\n⚠️  检测到内存泄漏！")
        else:
            print("\n✅ 内存使用稳定，无明显泄漏")
            
    except ImportError:
        print("⚠️  无法导入MCAP转换器，跳过测试")
    except Exception as e:
        print(f"❌ MCAP测试失败: {e}")


def test_episode_finder_correctness():
    """测试Episode查找正确性（规则匹配vs递归搜索）"""
    print("="*80)
    print("测试3: Episode查找正确性验证")
    print("="*80)
    
    from robocoin_dataset.format_converter.tolerobot.episode_finder import EpisodeFinder
    
    test_path = Path("/mnt/nas/synnas/docker/外部数据/银河通用")
    
    if not test_path.exists():
        print("⏭️  跳过: 测试路径不存在")
        return
    
    print(f"\n📁 测试路径: {test_path}")
    
    # 方法1: 规则匹配
    finder = EpisodeFinder(device_model="yinhe", logger=None, enable_recursive_fallback=False)
    files_fast = finder.find_episode_files(test_path, [".json"])
    
    # 方法2: 递归搜索
    files_slow = list(test_path.rglob("*.json"))
    files_slow = [f for f in files_slow if not any(part.startswith('.') or part.startswith('@') for part in f.parts)]
    files_slow = sorted(files_slow)
    
    print(f"\n📊 规则匹配找到: {len(files_fast)} 个文件")
    print(f"📊 递归搜索找到: {len(files_slow)} 个文件")
    
    # 对比结果
    if len(files_fast) == len(files_slow):
        print("✅ 文件数量一致")
    else:
        print("⚠️  文件数量不一致！")
        print(f"   差异: {abs(len(files_fast) - len(files_slow))} 个文件")
    
    # 检查文件是否完全匹配
    set_fast = set(files_fast)
    set_slow = set(files_slow)
    
    missing_in_fast = set_slow - set_fast
    extra_in_fast = set_fast - set_slow
    
    if not missing_in_fast and not extra_in_fast:
        print("✅ 文件完全匹配")
    else:
        if missing_in_fast:
            print(f"⚠️  规则匹配遗漏 {len(missing_in_fast)} 个文件:")
            for f in list(missing_in_fast)[:5]:
                print(f"     - {f}")
        
        if extra_in_fast:
            print(f"⚠️  规则匹配多找到 {len(extra_in_fast)} 个文件:")
            for f in list(extra_in_fast)[:5]:
                print(f"     - {f}")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("           内存泄漏和性能优化修复测试")
    print("="*80 + "\n")
    
    # 测试1: Episode查找性能
    try:
        test_episode_finder_performance()
    except Exception as e:
        print(f"❌ 性能测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n")
    
    # 测试2: MCAP内存泄漏
    try:
        test_mcap_memory_leak()
    except Exception as e:
        print(f"❌ 内存测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n")
    
    # 测试3: 正确性验证
    try:
        test_episode_finder_correctness()
    except Exception as e:
        print(f"❌ 正确性测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*80)
    print("                     测试完成")
    print("="*80 + "\n")

