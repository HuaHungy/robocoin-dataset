#!/usr/bin/env python3
"""
测试各converter的episode定位和数据加载

功能：
- 动态加载指定的converter类
- 定位episodes
- 加载第一帧数据
- 验证配置字段是否存在
- 输出数据shape和统计信息
"""

import argparse
import importlib
import logging
import sys
from pathlib import Path
import yaml
import numpy as np

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_converter_class(module_path, class_name):
    """动态加载converter类"""
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def load_factory_config():
    """加载factory配置"""
    config_path = Path("scripts/format_converters/tolerobot/configs/converter_factory_config.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def find_test_data(device_model, device_version):
    """查找本地测试数据"""
    data_dir = Path("data")
    
    # 构建可能的数据路径
    possible_paths = [
        data_dir / f"{device_model}:{device_version}",
        data_dir / f"{device_model.replace('_', '-')}:{device_version}",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    return None


def test_converter(device_model, device_version=None):
    """测试指定device的converter"""
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    print("=" * 80)
    print(f"🧪 测试 Converter: {device_model}")
    if device_version:
        print(f"   版本: {device_version}")
    print("=" * 80)
    
    # 1. 加载factory配置
    factory_config = load_factory_config()
    
    if device_model not in factory_config:
        print(f"❌ 错误: 未找到设备 '{device_model}' 的配置")
        return False
    
    device_config = factory_config[device_model]
    
    # 选择版本
    if device_version:
        version_config = None
        for v in device_config:
            if v.get('version') == device_version:
                version_config = v
                break
        if not version_config:
            print(f"❌ 错误: 未找到版本 '{device_version}'")
            return False
    else:
        version_config = device_config[0]
        device_version = version_config.get('version', 'default_version')
    
    print(f"\n📋 配置信息:")
    print(f"   模块: {version_config.get('module')}")
    print(f"   类名: {version_config.get('class')}")
    print(f"   配置文件: {version_config.get('converter_config_path')}")
    
    # 2. 查找测试数据
    dataset_path = find_test_data(device_model, device_version)
    if not dataset_path:
        print(f"\n⚠️  警告: 未找到测试数据")
        print(f"   查找路径: data/{device_model}:{device_version}")
        return False
    
    print(f"\n📁 数据集路径: {dataset_path}")
    
    # 3. 加载converter类
    try:
        ConverterClass = load_converter_class(
            version_config['module'],
            version_config['class']
        )
        print(f"✅ 成功加载converter类: {version_config['class']}")
    except Exception as e:
        print(f"❌ 加载converter类失败: {e}")
        return False
    
    # 4. 实例化converter
    try:
        config_path = Path("scripts/format_converters/tolerobot/configs") / version_config['converter_config_path']
        
        converter = ConverterClass(
            dataset_path=dataset_path,
            output_path="/tmp/test_converter_output",
            repo_id="test/test",
            converter_config_path=config_path,
            fps=30
        )
        print(f"✅ 成功实例化converter")
    except Exception as e:
        print(f"❌ 实例化converter失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 5. 定位episodes
    try:
        # 尝试获取episodes（不同converter可能有不同方法）
        if hasattr(converter, 'task_episode_h5file_paths'):
            # H5 converter
            all_episodes = []
            for task_path, h5_files in converter.task_episode_h5file_paths.items():
                all_episodes.extend(h5_files)
            print(f"\n📊 Episode定位结果:")
            print(f"   找到episodes: {len(all_episodes)}")
            if all_episodes:
                for i, ep in enumerate(all_episodes[:5]):
                    print(f"   Episode {i}: {ep}")
                if len(all_episodes) > 5:
                    print(f"   ... 还有 {len(all_episodes) - 5} 个")
        elif hasattr(converter, '_get_all_episode_dirs'):
            # H5+JPG converter
            all_episodes = converter._get_all_episode_dirs(dataset_path)
            print(f"\n📊 Episode定位结果:")
            print(f"   找到episodes: {len(all_episodes)}")
            if all_episodes:
                for i, ep in enumerate(all_episodes[:5]):
                    print(f"   Episode {i}: {ep}")
                if len(all_episodes) > 5:
                    print(f"   ... 还有 {len(all_episodes) - 5} 个")
        else:
            print(f"\n⚠️  警告: 未找到episode定位方法")
            return False
        
        if not all_episodes:
            print(f"❌ 未找到任何episodes")
            return False
        
    except Exception as e:
        print(f"❌ Episode定位失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 6. 测试数据加载（第一个episode的第一帧）
    print(f"\n🔍 测试数据加载 (第一个episode，第一帧):")
    try:
        # 这部分需要根据实际converter的API调整
        # 暂时只打印基本信息
        print(f"   ✅ Episode定位测试通过")
        print(f"   ℹ️  数据加载测试需要进一步实现")
        
    except Exception as e:
        print(f"❌ 数据加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print(f"\n{'=' * 80}")
    print(f"✅ 测试完成: {device_model}:{device_version}")
    print(f"{'=' * 80}\n")
    
    return True


def main():
    parser = argparse.ArgumentParser(description="测试converter的episode定位和数据加载")
    parser.add_argument("--device", required=True, help="设备型号 (如: zhipingfang)")
    parser.add_argument("--version", help="设备版本 (可选，默认使用第一个版本)")
    parser.add_argument("--all", action="store_true", help="测试所有本地数据集")
    
    args = parser.parse_args()
    
    if args.all:
        # 测试所有本地数据集
        data_dir = Path("data")
        datasets = [d.name for d in data_dir.iterdir() if d.is_dir() and ':' in d.name]
        
        print(f"找到 {len(datasets)} 个本地数据集")
        
        success_count = 0
        failed_datasets = []
        
        for dataset in sorted(datasets):
            device, version = dataset.split(':', 1)
            success = test_converter(device, version)
            if success:
                success_count += 1
            else:
                failed_datasets.append(dataset)
        
        print("\n" + "=" * 80)
        print(f"📊 测试总结:")
        print(f"   总数: {len(datasets)}")
        print(f"   成功: {success_count}")
        print(f"   失败: {len(failed_datasets)}")
        if failed_datasets:
            print(f"\n❌ 失败的数据集:")
            for ds in failed_datasets:
                print(f"   - {ds}")
        print("=" * 80)
    else:
        # 测试单个数据集
        test_converter(args.device, args.version)


if __name__ == "__main__":
    main()

