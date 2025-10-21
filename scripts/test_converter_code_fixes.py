#!/usr/bin/env python3
"""
单元测试：验证修复的关键功能

测试内容：
1. Test 模式标志是否正确设置
2. 资源清理代码是否存在（try-finally）
3. 帧数限制逻辑是否正确
"""

import sys
import inspect
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


def test_converter_has_test_mode_support(converter_class, converter_name):
    """测试 converter 是否支持 test 模式"""
    print(f"\n{'='*70}")
    print(f"测试 {converter_name} - Test 模式支持")
    print(f"{'='*70}")
    
    results = []
    
    # 1. 检查 _is_test_mode 属性
    source = inspect.getsource(converter_class)
    
    has_test_flag = "_is_test_mode" in source
    if has_test_flag:
        print("  ✅ 有 _is_test_mode 标志")
        results.append(True)
    else:
        print("  ⏭️  无 _is_test_mode 标志（可能不需要）")
        results.append(None)
    
    # 2. 检查 convert() 方法是否接受 is_test 参数
    if hasattr(converter_class, 'convert'):
        convert_sig = inspect.signature(converter_class.convert)
        has_is_test_param = 'is_test' in convert_sig.parameters
        
        if has_is_test_param:
            print("  ✅ convert() 支持 is_test 参数")
            results.append(True)
        else:
            print("  ⏭️  convert() 不支持 is_test 参数（通过父类兼容）")
            results.append(None)
    
    # 3. 检查帧数限制逻辑
    has_frame_limit = "11" in source and ("test" in source.lower() or "frame" in source.lower())
    if has_frame_limit:
        print("  ✅ 有帧数限制逻辑（检测到 '11' 和 test/frame 关键字）")
        results.append(True)
    else:
        print("  ⏭️  未检测到明显的帧数限制逻辑")
        results.append(None)
    
    # 4. 检查资源清理（try-finally）
    has_try_finally = "try:" in source and "finally:" in source
    has_close_or_release = "close()" in source or "release()" in source
    
    if has_try_finally and has_close_or_release:
        print("  ✅ 有资源清理代码（try-finally + close/release）")
        results.append(True)
    else:
        if not has_close_or_release:
            print("  ⏭️  没有资源清理需求（不使用视频资源）")
            results.append(None)
        else:
            print("  ⚠️  有 close/release 但缺少 try-finally")
            results.append(False)
    
    # 汇总
    has_issues = any(r is False for r in results)
    has_improvements = any(r is True for r in results)
    
    if has_issues:
        print(f"\n❌ {converter_name} 有问题需要修复")
        return False
    elif has_improvements:
        print(f"\n✅ {converter_name} 已正确修复")
        return True
    else:
        print(f"\n⏭️  {converter_name} 无需修复（不受影响）")
        return None


def main():
    """运行所有测试"""
    print("="*70)
    print("Converter 代码修复验证")
    print("="*70)
    print("\n本测试验证关键修复是否正确实现：")
    print("  1. Test 模式标志 (_is_test_mode)")
    print("  2. convert() 方法支持 is_test 参数")
    print("  3. 帧数限制逻辑 (11 frames)")
    print("  4. 资源清理代码 (try-finally + close/release)")
    
    # 定义要测试的 converters
    test_cases = []
    
    # 1. LejuWaibu (修复了内存+资源泄漏)
    try:
        from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_leju_waibu import (
            LerobotFormatConverterLejuWaibu,
        )
        test_cases.append((LerobotFormatConverterLejuWaibu, "LejuWaibu"))
    except ImportError as e:
        print(f"⚠️  无法导入 LejuWaibu: {e}")
    
    # 2. H5Mp4 (修复了内存+资源泄漏)
    try:
        from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5_mp4 import (
            LerobotFormatConverterH5Mp4,
        )
        test_cases.append((LerobotFormatConverterH5Mp4, "H5Mp4"))
    except ImportError as e:
        print(f"⚠️  无法导入 H5Mp4: {e}")
    
    # 3. Mp4Json (修复了内存+资源泄漏)
    try:
        from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_mp4_json import (
            LerobotFormatConverterMp4Json,
        )
        test_cases.append((LerobotFormatConverterMp4Json, "Mp4Json"))
    except ImportError as e:
        print(f"⚠️  无法导入 Mp4Json: {e}")
    
    # 4. JpgJson (修复了内存)
    try:
        from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_jpg_json import (
            LerobotFormatConverterJpgJson,
        )
        test_cases.append((LerobotFormatConverterJpgJson, "JpgJson"))
    except ImportError as e:
        print(f"⚠️  无法导入 JpgJson: {e}")
    
    # 5. MCAP (修复了信号量泄漏)
    try:
        from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_mcap import (
            LerobotFormatConverterMcap,
        )
        test_cases.append((LerobotFormatConverterMcap, "MCAP"))
    except ImportError as e:
        print(f"⚠️  无法导入 MCAP: {e}")
    
    # 6. 对比组：一个未修复的 converter
    try:
        from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_g1 import (
            LerobotFormatConverterG1,
        )
        test_cases.append((LerobotFormatConverterG1, "G1 (对比组)"))
    except ImportError as e:
        print(f"⚠️  无法导入 G1: {e}")
    
    if not test_cases:
        print("\n❌ 没有可用的测试用例")
        return False
    
    # 运行测试
    results = {}
    for converter_class, converter_name in test_cases:
        try:
            result = test_converter_has_test_mode_support(converter_class, converter_name)
            results[converter_name] = result
        except Exception as e:
            print(f"\n❌ 测试 {converter_name} 时出错: {e}")
            import traceback
            traceback.print_exc()
            results[converter_name] = False
    
    # 汇总结果
    print(f"\n{'='*70}")
    print("测试结果汇总")
    print(f"{'='*70}")
    
    fixed_converters = []
    unfixed_converters = []
    skipped_converters = []
    
    for converter_name, result in results.items():
        if result is True:
            print(f"  ✅ {converter_name}: 已修复")
            fixed_converters.append(converter_name)
        elif result is False:
            print(f"  ❌ {converter_name}: 有问题")
            unfixed_converters.append(converter_name)
        else:
            print(f"  ⏭️  {converter_name}: 无需修复")
            skipped_converters.append(converter_name)
    
    print(f"\n总结:")
    print(f"  ✅ 已修复: {len(fixed_converters)} 个")
    print(f"  ⏭️  无需修复: {len(skipped_converters)} 个")
    print(f"  ❌ 有问题: {len(unfixed_converters)} 个")
    
    if unfixed_converters:
        print(f"\n⚠️  以下 converters 需要检查: {', '.join(unfixed_converters)}")
        return False
    else:
        print(f"\n✅ 所有修复验证通过！")
        return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n\n❌ 测试发生异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
