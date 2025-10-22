"""
批量配置验证脚本 - 快速验证多个数据集的配置正确性

功能：
- 从数据库查询指定device_model的数据集
- 每个数据集随机采样2个episodes
- 深度分析schema
- 对比配置文件
- 检查字段命名规范
- 生成详细报告
"""

import argparse
import logging
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.config_validation.episode_locator import EpisodeLocator
from scripts.config_validation.schema_analyzer import SchemaAnalyzer
from scripts.config_validation.config_comparator import ConfigComparator
from scripts.config_validation.field_name_checker import FieldNameChecker
from scripts.dataset_schema_discovery.database_query_tool import DatabaseQueryTool


class BatchValidator:
    """批量验证器"""
    
    # 优先级device models（按用户指定的顺序）
    PRIORITY_MODELS = [
        'discover_robotics_aitbot_mmk2',
        'yinhe',
        'realman_rmc_aidal',
        'agilex',
        'leju',
        'ruantong',
        'zhipingfang',
        'galaxea'
    ]
    
    def __init__(
        self,
        database_path: str,
        config_dir: Path,
        output_dir: Path,
        logger: Optional[logging.Logger] = None
    ):
        self.database_path = database_path
        self.config_dir = Path(config_dir)
        self.output_dir = Path(output_dir)
        self.logger = logger or logging.getLogger(__name__)
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化组件
        self.episode_locator = EpisodeLocator(logger=self.logger)
        self.schema_analyzer = SchemaAnalyzer(logger=self.logger)
        self.config_comparator = ConfigComparator(logger=self.logger)
        self.field_name_checker = FieldNameChecker(logger=self.logger)
    
    def run(
        self,
        device_models: Optional[List[str]] = None,
        num_datasets_per_model: int = 2,
        num_episodes_per_dataset: int = 2
    ) -> Dict[str, Any]:
        """
        运行批量验证
        
        Args:
            device_models: 要验证的device_model列表（None表示使用优先级列表）
            num_datasets_per_model: 每个model采样多少个数据集
            num_episodes_per_dataset: 每个数据集采样多少个episodes
            
        Returns:
            总体报告
        """
        if device_models is None:
            device_models = self.PRIORITY_MODELS
        
        self.logger.info("=" * 70)
        self.logger.info("批量配置验证")
        self.logger.info("=" * 70)
        self.logger.info(f"Device Models: {', '.join(device_models)}")
        self.logger.info(f"每个模型采样: {num_datasets_per_model} 个数据集")
        self.logger.info(f"每个数据集采样: {num_episodes_per_dataset} 个episodes")
        self.logger.info("=" * 70)
        
        overall_report = {
            'timestamp': datetime.now().isoformat(),
            'device_models': {},
            'summary': {
                'total_models': len(device_models),
                'total_datasets': 0,
                'total_episodes_analyzed': 0,
                'successful_validations': 0,
                'failed_validations': 0
            }
        }
        
        # 逐个验证device_model
        for idx, device_model in enumerate(device_models, 1):
            self.logger.info(f"\n[{idx}/{len(device_models)}] 验证 {device_model}")
            self.logger.info("=" * 70)
            
            try:
                model_report = self._validate_device_model(
                    device_model=device_model,
                    num_datasets=num_datasets_per_model,
                    num_episodes=num_episodes_per_dataset
                )
                
                overall_report['device_models'][device_model] = model_report
                
                # 更新统计
                overall_report['summary']['total_datasets'] += model_report.get('num_datasets', 0)
                overall_report['summary']['total_episodes_analyzed'] += model_report.get('total_episodes_analyzed', 0)
                
                if model_report.get('status') == 'success':
                    overall_report['summary']['successful_validations'] += 1
                else:
                    overall_report['summary']['failed_validations'] += 1
                
                self.logger.info(f"✓ {device_model} 验证完成")
                
            except Exception as e:
                self.logger.error(f"✗ {device_model} 验证失败: {e}", exc_info=True)
                overall_report['device_models'][device_model] = {
                    'status': 'error',
                    'error': str(e)
                }
                overall_report['summary']['failed_validations'] += 1
        
        # 保存总体报告
        report_path = self.output_dir / "validation_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(overall_report, f, indent=2, ensure_ascii=False, default=str)
        
        self.logger.info("\n" + "=" * 70)
        self.logger.info("验证完成！")
        self.logger.info("=" * 70)
        self.logger.info(f"总Device Models: {overall_report['summary']['total_models']}")
        self.logger.info(f"总数据集: {overall_report['summary']['total_datasets']}")
        self.logger.info(f"总Episodes分析: {overall_report['summary']['total_episodes_analyzed']}")
        self.logger.info(f"成功: {overall_report['summary']['successful_validations']}")
        self.logger.info(f"失败: {overall_report['summary']['failed_validations']}")
        self.logger.info(f"\n报告保存到: {report_path}")
        self.logger.info("=" * 70)
        
        return overall_report
    
    def _validate_device_model(
        self,
        device_model: str,
        num_datasets: int,
        num_episodes: int
    ) -> Dict[str, Any]:
        """验证单个device_model的数据集"""
        report = {
            'device_model': device_model,
            'num_datasets': 0,
            'datasets': [],
            'total_episodes_analyzed': 0,
            'status': 'unknown'
        }
        
        # 1. 查询数据集
        with DatabaseQueryTool(self.database_path, logger=self.logger) as db_tool:
            datasets = db_tool.sample_datasets_for_device_model(
                device_model=device_model,
                num_samples=num_datasets
            )
        
        if not datasets:
            self.logger.warning(f"未找到 {device_model} 的数据集")
            report['status'] = 'no_datasets'
            return report
        
        self.logger.info(f"找到 {len(datasets)} 个数据集")
        report['num_datasets'] = len(datasets)
        
        # 2. 加载配置文件
        config = self._load_config_for_device_model(device_model)
        if not config:
            self.logger.error(f"未找到 {device_model} 的配置文件")
            report['status'] = 'no_config'
            return report
        
        self.logger.info(f"✓ 加载配置文件: {config.get('_config_file', 'unknown')}")
        
        # 3. 逐个验证数据集
        for ds_idx, dataset in enumerate(datasets, 1):
            self.logger.info(f"\n  [{ds_idx}/{len(datasets)}] 验证数据集: {dataset['dataset_name']}")
            self.logger.info(f"      路径: {dataset['dataset_path']}")
            
            try:
                ds_report = self._validate_single_dataset(
                    dataset=dataset,
                    config=config,
                    num_episodes=num_episodes
                )
                
                report['datasets'].append(ds_report)
                report['total_episodes_analyzed'] += ds_report.get('num_episodes_analyzed', 0)
                
                # 简要显示结果
                if ds_report.get('status') == 'success':
                    self.logger.info(f"      ✓ 验证通过")
                else:
                    self.logger.info(f"      ✗ 验证失败: {ds_report.get('error', 'unknown')}")
            
            except Exception as e:
                self.logger.error(f"      ✗ 验证失败: {e}")
                report['datasets'].append({
                    'dataset_name': dataset['dataset_name'],
                    'dataset_path': dataset['dataset_path'],
                    'status': 'error',
                    'error': str(e)
                })
        
        # 判断整体状态
        successful_datasets = sum(1 for ds in report['datasets'] if ds.get('status') == 'success')
        if successful_datasets > 0:
            report['status'] = 'success'
        else:
            report['status'] = 'failed'
        
        return report
    
    def _validate_single_dataset(
        self,
        dataset: Dict[str, Any],
        config: Dict[str, Any],
        num_episodes: int
    ) -> Dict[str, Any]:
        """验证单个数据集"""
        report = {
            'dataset_name': dataset['dataset_name'],
            'dataset_path': dataset['dataset_path'],
            'num_episodes_analyzed': 0,
            'episodes': [],
            'schema_summary': {},
            'config_comparison': {},
            'field_name_check': {},
            'status': 'unknown'
        }
        
        dataset_path = Path(dataset['dataset_path'])
        
        if not dataset_path or not dataset_path.exists():
            report['status'] = 'error'
            report['error'] = f"数据集路径不存在: {dataset_path}"
            return report
        
        # 1. 定位episodes
        try:
            episodes = self.episode_locator.locate_episodes(
                dataset_path=dataset_path,
                num_samples=num_episodes
            )
        except Exception as e:
            report['status'] = 'error'
            report['error'] = f"定位episodes失败: {e}"
            return report
        
        if not episodes:
            report['status'] = 'error'
            report['error'] = "未找到任何episodes"
            return report
        
        self.logger.info(f"      采样 {len(episodes)} 个episodes: {[ep.episode_idx for ep in episodes]}")
        report['num_episodes_analyzed'] = len(episodes)
        
        # 2. 分析schemas
        schemas = []
        for ep in episodes:
            try:
                schema = self.schema_analyzer.analyze_episode(
                    episode_path=ep.episode_path,
                    format_type=ep.format_type
                )
                schemas.append(schema)
                report['episodes'].append({
                    'episode_idx': ep.episode_idx,
                    'episode_path': str(ep.episode_path),
                    'format': ep.format_type,
                    'schema_status': 'success' if not schema.get('errors') else 'error'
                })
            except Exception as e:
                self.logger.error(f"      分析Episode {ep.episode_idx} 失败: {e}")
                report['episodes'].append({
                    'episode_idx': ep.episode_idx,
                    'episode_path': str(ep.episode_path),
                    'schema_status': 'error',
                    'error': str(e)
                })
        
        if not schemas:
            report['status'] = 'error'
            report['error'] = "所有episodes分析失败"
            return report
        
        # 3. 生成schema摘要
        report['schema_summary'] = self.schema_analyzer.generate_schema_report(schemas)
        
        # 4. 对比配置
        try:
            # 使用第一个成功的schema进行对比
            first_schema = schemas[0]
            comparison = self.config_comparator.compare(first_schema, config)
            report['config_comparison'] = comparison
            
            # 生成可读报告并保存
            readable_comparison = self.config_comparator.generate_readable_report(comparison)
            comparison_file = self.output_dir / f"{dataset['dataset_name']}_comparison.txt"
            with open(comparison_file, 'w', encoding='utf-8') as f:
                f.write(readable_comparison)
            
            self.logger.info(f"      配置对比报告: {comparison_file}")
            
        except Exception as e:
            self.logger.error(f"      配置对比失败: {e}")
            report['config_comparison'] = {'error': str(e)}
        
        # 5. 检查字段命名
        try:
            field_name_report = self.field_name_checker.check_config_field_names(config)
            report['field_name_check'] = field_name_report
            
            # 生成可读报告并保存
            readable_field_check = self.field_name_checker.generate_readable_report(field_name_report)
            field_check_file = self.output_dir / f"{dataset['dataset_name']}_field_names.txt"
            with open(field_check_file, 'w', encoding='utf-8') as f:
                f.write(readable_field_check)
            
            self.logger.info(f"      字段命名报告: {field_check_file}")
            
        except Exception as e:
            self.logger.error(f"      字段命名检查失败: {e}")
            report['field_name_check'] = {'error': str(e)}
        
        # 6. 判断整体状态
        has_errors = (
            report['config_comparison'].get('summary', {}).get('total_errors', 0) > 0
        )
        
        if has_errors:
            report['status'] = 'has_errors'
        else:
            report['status'] = 'success'
        
        return report
    
    def _load_config_for_device_model(self, device_model: str) -> Optional[Dict[str, Any]]:
        """加载device_model的配置文件"""
        # 从converter_factory_config.yaml中查找配置文件映射
        factory_config_path = self.config_dir / "converter_factory_config.yaml"
        
        if factory_config_path.exists():
            factory_config = self.config_comparator.load_config(factory_config_path)
            
            # 查找匹配的device_model_version
            for entry in factory_config.get('device_model_versions', []):
                if entry.get('device_model', '').startswith(device_model):
                    config_file = entry.get('converter_config_file')
                    if config_file:
                        config_path = self.config_dir / config_file
                        if config_path.exists():
                            config = self.config_comparator.load_config(config_path)
                            config['_config_file'] = config_file
                            return config
        
        # 如果没找到，尝试直接查找converter_config_{device_model}.yaml
        config_path = self.config_dir / f"converter_config_{device_model}.yaml"
        if config_path.exists():
            config = self.config_comparator.load_config(config_path)
            config['_config_file'] = config_path.name
            return config
        
        return None


def main():
    parser = argparse.ArgumentParser(
        description="批量验证转换器配置",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 验证所有优先级device models
  python batch_validation.py \\
      --database /mnt/db/datasets.db \\
      --config-dir ./scripts/format_converters/tolerobot/configs/ \\
      --output-dir ./outputs/config_validation
  
  # 只验证特定device models
  python batch_validation.py \\
      --database /mnt/db/datasets.db \\
      --config-dir ./configs/ \\
      --output-dir ./outputs/ \\
      --device-models mmk2 yinhe
        """
    )
    
    parser.add_argument(
        '--database',
        type=str,
        required=True,
        help='数据库路径'
    )
    
    parser.add_argument(
        '--config-dir',
        type=str,
        required=True,
        help='配置文件目录'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        required=True,
        help='输出目录'
    )
    
    parser.add_argument(
        '--device-models',
        nargs='+',
        default=None,
        help='要验证的device models（默认使用优先级列表）'
    )
    
    parser.add_argument(
        '--num-datasets',
        type=int,
        default=2,
        help='每个device model采样的数据集数量（默认2）'
    )
    
    parser.add_argument(
        '--num-episodes',
        type=int,
        default=2,
        help='每个数据集采样的episodes数量（默认2）'
    )
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    logger = logging.getLogger(__name__)
    
    # 运行验证
    validator = BatchValidator(
        database_path=args.database,
        config_dir=Path(args.config_dir),
        output_dir=Path(args.output_dir),
        logger=logger
    )
    
    validator.run(
        device_models=args.device_models,
        num_datasets_per_model=args.num_datasets,
        num_episodes_per_dataset=args.num_episodes
    )


if __name__ == "__main__":
    main()

