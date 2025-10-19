#!/usr/bin/env python3
"""
银河数据集快速验证测试工具

这个脚本提供快速的数据集质量检查,用于:
1. 快速验证少量episodes
2. 获取数据集整体统计信息
3. 识别明显的数据问题

使用方法:
    python3 yinhe_quick_test.py
"""

import sys
from pathlib import Path
from yinhe_preconversion_validator import YinheDatasetValidator


def main():
    dataset_path = Path("/mnt/nas/synnas/docker/外部数据/银河通用")
    
    if not dataset_path.exists():
        print(f"❌ 数据集路径不存在: {dataset_path}")
        sys.exit(1)
    
    print("🚀 银河数据集快速验证测试")
    print("="*70)
    
    # 1. 快速测试前10个episodes
    print("\n📊 阶段1: 快速测试前10个episodes")
    print("-"*70)
    validator = YinheDatasetValidator(dataset_path, verbose=False)
    results = validator.validate_all(max_episodes=10)
    
    # 打印简要统计
    total = len(results)
    valid = sum(1 for r in results if r.is_valid)
    print(f"\n快速测试结果: {valid}/{total} episodes有效 ({valid/total*100:.1f}%)")
    
    # 2. 统计每个任务的episode数量
    print("\n📊 阶段2: 统计任务和episode数量")
    print("-"*70)
    all_episodes = validator.find_episodes()
    task_counts = {}
    for episode in all_episodes:
        task = episode.parent.parent.name
        task_counts[task] = task_counts.get(task, 0) + 1
    
    print(f"总共找到 {len(all_episodes)} 个episodes")
    print(f"\n按任务分布:")
    for task, count in sorted(task_counts.items()):
        print(f"  {task}: {count} episodes")
    
    # 3. 检查常见问题
    print("\n📊 阶段3: 检查前20个episodes的常见问题")
    print("-"*70)
    validator_verbose = YinheDatasetValidator(dataset_path, verbose=True)
    test_results = validator_verbose.validate_all(max_episodes=20)
    
    # 统计问题类型
    all_errors = []
    all_warnings = []
    for result in test_results:
        all_errors.extend(result.errors)
        all_warnings.extend(result.warnings)
    
    if all_errors:
        error_counts = {}
        for error in all_errors:
            error_counts[error] = error_counts.get(error, 0) + 1
        
        print(f"\n发现的错误类型 (共{len(all_errors)}个错误):")
        for error, count in sorted(error_counts.items(), key=lambda x: -x[1])[:5]:
            print(f"  [{count}] {error}")
    else:
        print("\n✅ 前20个episodes没有发现错误!")
    
    if all_warnings:
        warning_counts = {}
        for warning in all_warnings:
            warning_counts[warning] = warning_counts.get(warning, 0) + 1
        
        print(f"\n警告类型 (共{len(all_warnings)}个警告):")
        for warning, count in sorted(warning_counts.items(), key=lambda x: -x[1])[:3]:
            print(f"  [{count}] {warning}")
    
    print("\n" + "="*70)
    print("✅ 快速测试完成!")
    
    # 给出建议
    invalid_ratio = sum(1 for r in test_results if not r.is_valid) / len(test_results)
    if invalid_ratio > 0.1:
        print(f"\n⚠️  警告: 检测到 {invalid_ratio*100:.1f}% 的episodes有问题")
        print("   建议运行完整验证: python3 yinhe_preconversion_validator.py")
    else:
        print(f"\n✅ 数据集质量良好: {(1-invalid_ratio)*100:.1f}% episodes有效")
    
    print("="*70)


if __name__ == "__main__":
    main()
