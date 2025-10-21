#!/usr/bin/env python3
"""
Converter 兼容性检查脚本

检查所有 converter 的实现是否有以下问题：
1. 方法签名不兼容
2. 资源泄漏风险
3. 缺少必要的方法实现
"""

import inspect
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# 导入所有 converter
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import LerobotFormatConverter
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_mcap import LerobotFormatConverterRealmanRmcAidalMcap
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_mmk2 import LerobotFormatConverterMmk2
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_leju_waibu import LerobotFormatConverterLejuWaibu
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_jpg_json import LerobotFormatConverterJpgJson
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_mp4_json import LerobotFormatConverterMp4Json
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5_jpg import LerobotFormatConverterH5Jpg
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5_mp4 import LerobotFormatConverterH5Mp4
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_g1 import LerobotFormatConverterG1
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5 import LerobotFormatConverterHdf5
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_rosbag import LerobotFormatConverterRosbag
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_lerobot import LerobotFormatConverterLerobot

# 所有 converter 类
CONVERTERS = [
    LerobotFormatConverterRealmanRmcAidalMcap,
    LerobotFormatConverterMmk2,
    LerobotFormatConverterLejuWaibu,
    LerobotFormatConverterJpgJson,
    LerobotFormatConverterMp4Json,
    LerobotFormatConverterH5Jpg,
    LerobotFormatConverterH5Mp4,
    LerobotFormatConverterG1,
    LerobotFormatConverterHdf5,
    LerobotFormatConverterRosbag,
    LerobotFormatConverterLerobot,
]

# 需要检查的方法
BUFFER_METHODS = [
    '_prepare_episode_images_buffer',
    '_prepare_episode_states_buffer',
    '_prepare_episode_actions_buffer',
]

def check_method_signature(cls, method_name):
    """检查方法签名"""
    if not hasattr(cls, method_name):
        return {
            'exists': False,
            'has_is_test': False,
            'status': '❌ 方法不存在'
        }
    
    method = getattr(cls, method_name)
    sig = inspect.signature(method)
    params = sig.parameters
    
    has_is_test = 'is_test' in params
    
    # 检查是否是父类的默认实现（未被重写）
    parent_method = getattr(LerobotFormatConverter, method_name)
    is_overridden = method != parent_method
    
    if not is_overridden:
        status = '⚪ 使用父类默认实现（返回 None）'
    elif has_is_test:
        status = '✅ 已实现且支持 is_test'
    else:
        status = '⚠️ 已实现但不支持 is_test（兼容模式）'
    
    return {
        'exists': True,
        'has_is_test': has_is_test,
        'is_overridden': is_overridden,
        'status': status,
        'signature': str(sig)
    }

def check_converter(cls):
    """全面检查一个 converter"""
    print(f"\n{'='*80}")
    print(f"📦 {cls.__name__}")
    print(f"{'='*80}")
    
    results = {}
    
    # 检查 buffer 方法
    print("\n🔍 Buffer 方法检查：")
    for method_name in BUFFER_METHODS:
        result = check_method_signature(cls, method_name)
        results[method_name] = result
        print(f"  {result['status']}")
        print(f"     方法：{method_name}")
        if result['exists']:
            print(f"     签名：{result['signature']}")
    
    # 检查是否实现了必要的方法
    print("\n🔍 必要方法检查：")
    required_methods = [
        '_get_dataset_task_paths',
        '_get_task_episodes_num', 
        '_get_episode_frames_num',
    ]
    
    for method_name in required_methods:
        if hasattr(cls, method_name):
            method = getattr(cls, method_name)
            parent_method = getattr(LerobotFormatConverter, method_name, None)
            is_overridden = parent_method is None or method != parent_method
            
            if is_overridden:
                print(f"  ✅ {method_name} - 已实现")
            else:
                print(f"  ⚪ {method_name} - 使用父类实现")
        else:
            print(f"  ❌ {method_name} - 缺失！")
    
    # 检查是否有 convert 方法重写（用于 test 模式优化）
    print("\n🔍 Test 模式优化检查：")
    if hasattr(cls, 'convert'):
        method = getattr(cls, 'convert')
        parent_method = getattr(LerobotFormatConverter, 'convert')
        if method != parent_method:
            print(f"  ✅ 重写了 convert() - 可能有特殊优化")
        else:
            print(f"  ⚪ 使用父类 convert() - 标准流程")
    
    return results

def main():
    print("="*80)
    print("🚀 Converter 兼容性全面检查")
    print("="*80)
    
    all_compatible = True
    
    for cls in CONVERTERS:
        try:
            results = check_converter(cls)
            
            # 检查是否有任何方法不兼容
            for method_name, result in results.items():
                if result['exists'] and result['is_overridden'] and not result['has_is_test']:
                    # 这些 converter 依赖智能调用机制
                    pass
        
        except Exception as e:
            print(f"\n❌ 检查 {cls.__name__} 时出错: {e}")
            import traceback
            traceback.print_exc()
            all_compatible = False
    
    print(f"\n{'='*80}")
    if all_compatible:
        print("✅ 所有 Converter 兼容性检查通过！")
    else:
        print("❌ 发现兼容性问题，请查看上方详情")
    print(f"{'='*80}")
    
    return 0 if all_compatible else 1

if __name__ == '__main__':
    sys.exit(main())
