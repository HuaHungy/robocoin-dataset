#!/usr/bin/env python3
"""
本地数据集配置验证脚本 - 不依赖数据库

功能：
- 扫描本地data/目录下的所有数据集
- 动态加载对应的converter类
- 使用converter进行episode定位和数据加载
- 对比配置文件，检查字段命名规范
- 生成详细报告

适用场景：
- 在没有数据库的环境中验证配置
- 快速验证新配置文件
- CI/CD集成测试
"""

import argparse
import logging
import json
import sys
import yaml
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.config_validation.schema_analyzer import SchemaAnalyzer
from scripts.config_validation.config_comparator import ConfigComparator
from scripts.config_validation.field_name_checker import FieldNameChecker
from scripts.config_validation.converter_loader import create_converter_instance


def load_factory_config(config_dir: Path) -> Dict[str, Any]:
    """加载converter_factory_config.yaml"""
    factory_config_path = config_dir / "converter_factory_config.yaml"
    with open(factory_config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def scan_local_datasets(data_dir: Path) -> List[Dict[str, str]]:
    """
    扫描本地数据目录，识别数据集
    
    预期数据集命名格式: device_model:device_version
    例如: zhipingfang:dual_arm_no_pose
    """
    datasets = []
    
    if not data_dir.exists():
        return datasets
    
    for dataset_dir in data_dir.iterdir():
        if not dataset_dir.is_dir():
            continue
        
        # 解析数据集名称
        dataset_name = dataset_dir.name
        if ':' in dataset_name:
            device_model, device_version = dataset_name.split(':', 1)
        else:
            # 如果没有版本号，使用default_version
            device_model = dataset_name
            device_version = 'default_version'
        
        datasets.append({
            'dataset_name': dataset_name,
            'dataset_path': str(dataset_dir),
            'device_model': device_model,
            'device_version': device_version
        })
    
    return datasets


def validate_dataset(
    dataset: Dict[str, str],
    factory_config: Dict[str, Any],
    config_dir: Path,
    output_dir: Path,
    num_episodes: int = 1,
    logger: logging.Logger = None
) -> Dict[str, Any]:
    """验证单个数据集"""
    logger = logger or logging.getLogger(__name__)
    
    report = {
        'dataset_name': dataset['dataset_name'],
        'device_model': dataset['device_model'],
        'device_version': dataset['device_version'],
        'dataset_path': dataset['dataset_path'],
        'status': 'unknown',
        'num_episodes_analyzed': 0,
        'schema': {},
        'config_comparison': {},
        'field_name_check': {}
    }
    
    logger.info(f"")
    logger.info(f"{'='*80}")
    logger.info(f"验证数据集: {dataset['dataset_name']}")
    logger.info(f"  Device: {dataset['device_model']}")
    logger.info(f"  Version: {dataset['device_version']}")
    logger.info(f"  Path: {dataset['dataset_path']}")
    logger.info(f"{'='*80}")
    
    # 1. 查找对应的converter配置
    device_model = dataset['device_model']
    device_version = dataset['device_version']
    
    if device_model not in factory_config:
        report['status'] = 'no_config'
        report['error'] = f"未找到 {device_model} 的配置"
        logger.error(f"  ✗ 未找到 {device_model} 的配置")
        return report
    
    versions = factory_config[device_model]
    
    # 查找匹配的版本
    version_config = None
    for v in versions:
        if v.get('version') == device_version:
            version_config = v
            break
    
    if not version_config:
        # 使用第一个版本作为默认
        version_config = versions[0]
        logger.warning(f"  ⚠ 未找到版本 {device_version}，使用 {version_config.get('version')}")
    
    converter_module = version_config.get('module')
    converter_class = version_config.get('class')
    converter_config_file = version_config.get('converter_config_path')
    
    logger.info(f"  ✓ Converter: {converter_class}")
    logger.info(f"  ✓ Config: {converter_config_file}")
    
    # 2. 实例化converter
    try:
        converter_config_path = config_dir / converter_config_file
        converter = create_converter_instance(
            module_path=converter_module,
            class_name=converter_class,
            dataset_path=dataset['dataset_path'],
            output_path="/tmp/validate_local_datasets_temp",
            repo_id="test/validation",
            converter_config_path=str(converter_config_path),
            device_model=dataset['device_model']
            # 注意：不传递fps参数，让converter使用默认值或从配置中读取
        )
        logger.info(f"  ✓ Converter实例化成功")
    except Exception as e:
        report['status'] = 'converter_error'
        report['error'] = f"Converter实例化失败: {e}"
        logger.error(f"  ✗ Converter实例化失败: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return report
    
    # 3. 使用converter分析schema
    try:
        schema_analyzer = SchemaAnalyzer(logger=logger)
        schema = schema_analyzer.analyze_with_converter(
            converter=converter,
            num_episodes=num_episodes
        )
        
        if schema.get('episodes_analyzed', 0) == 0:
            report['status'] = 'no_episodes'
            report['error'] = "未能分析任何episodes"
            logger.error(f"  ✗ 未能分析任何episodes")
            if schema.get('errors'):
                logger.error(f"     错误: {schema['errors']}")
            return report
        
        report['num_episodes_analyzed'] = schema['episodes_analyzed']
        report['schema'] = schema
        logger.info(f"  ✓ 分析了 {schema['episodes_analyzed']} 个episodes")
        
    except Exception as e:
        report['status'] = 'schema_error'
        report['error'] = f"Schema分析失败: {e}"
        logger.error(f"  ✗ Schema分析失败: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return report
    
    # 4. 加载配置并对比
    try:
        config_comparator = ConfigComparator(logger=logger)
        config = config_comparator.load_config(converter_config_path)
        
        comparison = config_comparator.compare(schema, config)
        report['config_comparison'] = comparison
        
        # 生成可读报告
        readable_comparison = config_comparator.generate_readable_report(comparison)
        comparison_file = output_dir / f"{dataset['dataset_name']}_comparison.txt"
        with open(comparison_file, 'w', encoding='utf-8') as f:
            f.write(readable_comparison)
        
        logger.info(f"  ✓ 配置对比完成，报告已保存: {comparison_file.name}")
        
    except Exception as e:
        report['status'] = 'comparison_error'
        report['error'] = f"配置对比失败: {e}"
        logger.error(f"  ✗ 配置对比失败: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return report
    
    # 5. 检查字段命名规范
    try:
        field_checker = FieldNameChecker(logger=logger)
        field_check = field_checker.check_config(config)
        report['field_name_check'] = field_check
        
        if field_check.get('errors'):
            logger.warning(f"  ⚠ 字段命名检查发现 {len(field_check['errors'])} 个问题")
        else:
            logger.info(f"  ✓ 字段命名检查通过")
        
    except Exception as e:
        logger.warning(f"  ⚠ 字段命名检查失败: {e}")
    
    # 6. 设置最终状态
    report['status'] = 'success'
    logger.info(f"  ✅ 验证成功")
    
    return report


def main():
    parser = argparse.ArgumentParser(description="本地数据集配置验证")
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="数据集目录（默认: data）"
    )
    parser.add_argument(
        "--config-dir",
        type=str,
        default="scripts/format_converters/tolerobot/configs",
        help="配置文件目录"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs/validation",
        help="输出目录"
    )
    parser.add_argument(
        "--num-episodes",
        type=int,
        default=1,
        help="每个数据集分析的episode数量"
    )
    parser.add_argument(
        "--device-model",
        type=str,
        help="只验证指定的device_model"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示详细日志"
    )
    
    args = parser.parse_args()
    
    # 设置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # 转换路径
    data_dir = Path(args.data_dir)
    config_dir = Path(args.config_dir)
    output_dir = Path(args.output_dir)
    
    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("\n" + "="*80)
    logger.info("本地数据集配置验证")
    logger.info("="*80)
    logger.info(f"数据目录: {data_dir}")
    logger.info(f"配置目录: {config_dir}")
    logger.info(f"输出目录: {output_dir}")
    logger.info(f"Episode数量: {args.num_episodes}")
    logger.info("="*80 + "\n")
    
    # 1. 加载factory配置
    try:
        factory_config = load_factory_config(config_dir)
        logger.info(f"✓ 加载factory配置成功")
    except Exception as e:
        logger.error(f"✗ 加载factory配置失败: {e}")
        return 1
    
    # 2. 扫描本地数据集
    datasets = scan_local_datasets(data_dir)
    
    if not datasets:
        logger.error(f"✗ 未找到任何数据集在 {data_dir}")
        return 1
    
    logger.info(f"✓ 找到 {len(datasets)} 个数据集\n")
    
    # 过滤device_model
    if args.device_model:
        datasets = [ds for ds in datasets if ds['device_model'] == args.device_model]
        logger.info(f"  过滤后剩余 {len(datasets)} 个数据集（device_model={args.device_model}）\n")
    
    # 3. 验证每个数据集
    results = []
    for ds in datasets:
        result = validate_dataset(
            dataset=ds,
            factory_config=factory_config,
            config_dir=config_dir,
            output_dir=output_dir,
            num_episodes=args.num_episodes,
            logger=logger
        )
        results.append(result)
    
    # 4. 生成总结报告
    logger.info("\n" + "="*80)
    logger.info("验证总结")
    logger.info("="*80)
    
    success_count = sum(1 for r in results if r['status'] == 'success')
    total_count = len(results)
    
    logger.info(f"总数据集: {total_count}")
    logger.info(f"验证成功: {success_count}")
    logger.info(f"验证失败: {total_count - success_count}")
    
    if total_count > 0:
        logger.info(f"成功率: {success_count/total_count*100:.1f}%")
    
    logger.info("")
    for result in results:
        status_icon = "✅" if result['status'] == 'success' else "❌"
        logger.info(f"{status_icon} {result['dataset_name']:40s} {result['status']}")
        if result.get('error'):
            logger.info(f"     错误: {result['error']}")
    
    # 5. 保存JSON报告
    report_file = output_dir / f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_datasets': total_count,
            'success_count': success_count,
            'results': results
        }, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n✓ 详细报告已保存: {report_file}")
    logger.info("="*80 + "\n")
    
    return 0 if success_count == total_count else 1


if __name__ == "__main__":
    sys.exit(main())

