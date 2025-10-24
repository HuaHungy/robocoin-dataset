"""
批量Schema Discovery工具

从数据库批量抽取优先device_model的数据集，执行schema discovery和诊断。
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
import json
import sys
from datetime import datetime

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from database_query_tool import DatabaseQueryTool
from dataset_schema_discoverer import DatasetSchemaDiscoverer
from schema_config_comparator import SchemaConfigComparator


class BatchSchemaDiscovery:
    """批量Schema Discovery工具"""
    
    def __init__(
        self,
        database_path: str,
        config_dir: Path,
        output_dir: Path,
        logger: Optional[logging.Logger] = None
    ):
        self.database_path = database_path
        self.config_dir = config_dir
        self.output_dir = output_dir
        self.logger = logger or logging.getLogger(__name__)
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / 'schemas').mkdir(exist_ok=True)
        (self.output_dir / 'diagnoses').mkdir(exist_ok=True)
        
        # 初始化工具
        self.discoverer = DatasetSchemaDiscoverer(logger)
        self.comparator = SchemaConfigComparator(logger)
    
    def run_for_priority_models(
        self,
        priority_models: List[str],
        num_samples_per_model: int = 5,
        num_episodes_per_dataset: int = 5
    ) -> Dict[str, Any]:
        """
        为优先级device_model执行批量schema discovery
        
        Args:
            priority_models: 优先级device_model列表
            num_samples_per_model: 每个device_model采样多少个数据集
            num_episodes_per_dataset: 每个数据集采样多少个episodes
            
        Returns:
            总体分析报告
        """
        self.logger.info("=" * 70)
        self.logger.info("批量Schema Discovery")
        self.logger.info("=" * 70)
        self.logger.info(f"优先级Device Models: {', '.join(priority_models)}")
        self.logger.info(f"每个模型采样: {num_samples_per_model} 个数据集")
        self.logger.info(f"每个数据集采样: {num_episodes_per_dataset} 个episodes")
        self.logger.info("=" * 70)
        
        overall_report = {
            'timestamp': datetime.now().isoformat(),
            'priority_models': priority_models,
            'models_analysis': {},
            'summary': {
                'total_models_analyzed': 0,
                'total_datasets_analyzed': 0,
                'total_errors': 0,
                'total_warnings': 0
            }
        }
        
        with DatabaseQueryTool(self.database_path, self.logger) as db_tool:
            # 先获取优先级models的统计信息
            model_stats = db_tool.get_priority_device_models(priority_models)
            
            self.logger.info("\n优先级Device Model统计:")
            for stat in model_stats:
                self.logger.info(
                    f"  {stat['device_model']:30} "
                    f"{stat['total_datasets']:5} 数据集, "
                    f"{len(stat['versions'])} 版本"
                )
            
            # 对每个device_model进行分析
            for i, priority_model in enumerate(priority_models, 1):
                self.logger.info(f"\n{'='*70}")
                self.logger.info(f"[{i}/{len(priority_models)}] 分析 {priority_model}")
                self.logger.info(f"{'='*70}")
                
                try:
                    model_report = self._analyze_device_model(
                        db_tool,
                        priority_model,
                        num_samples_per_model,
                        num_episodes_per_dataset
                    )
                    
                    overall_report['models_analysis'][priority_model] = model_report
                    overall_report['summary']['total_models_analyzed'] += 1
                    overall_report['summary']['total_datasets_analyzed'] += model_report['datasets_analyzed']
                    overall_report['summary']['total_errors'] += model_report['total_errors']
                    overall_report['summary']['total_warnings'] += model_report['total_warnings']
                    
                except Exception as e:
                    self.logger.error(f"分析 {priority_model} 失败: {e}", exc_info=True)
                    overall_report['models_analysis'][priority_model] = {
                        'status': 'failed',
                        'error': str(e)
                    }
        
        # 保存总体报告
        self._save_overall_report(overall_report)
        
        # 打印总结
        self._print_summary(overall_report)
        
        return overall_report
    
    def _analyze_device_model(
        self,
        db_tool: DatabaseQueryTool,
        device_model: str,
        num_samples: int,
        num_episodes: int
    ) -> Dict[str, Any]:
        """分析单个device_model"""
        # 采样数据集
        datasets = db_tool.sample_datasets_for_device_model(
            device_model,
            num_samples=num_samples,
            strategy='first'  # 可以改为'random'或'recent'
        )
        
        if not datasets:
            self.logger.warning(f"未找到 {device_model} 的数据集")
            return {
                'status': 'no_datasets',
                'datasets_analyzed': 0,
                'total_errors': 0,
                'total_warnings': 0
            }
        
        self.logger.info(f"找到 {len(datasets)} 个数据集进行分析")
        
        model_report = {
            'device_model': device_model,
            'datasets_analyzed': 0,
            'datasets_details': [],
            'total_errors': 0,
            'total_warnings': 0,
            'common_issues': [],
            'common_warnings': []
        }
        
        # 加载converter config（如果存在）
        converter_config = self._load_converter_config(device_model)
        
        # 分析每个数据集
        for j, dataset in enumerate(datasets, 1):
            dataset_path = Path(dataset['dataset_path'])
            
            if not dataset_path.exists():
                self.logger.warning(f"  [{j}/{len(datasets)}] 数据集路径不存在: {dataset_path}")
                continue
            
            self.logger.info(f"\n  [{j}/{len(datasets)}] 分析数据集: {dataset['dataset_name']}")
            self.logger.info(f"  路径: {dataset_path}")
            
            try:
                # Schema Discovery
                schema = self.discoverer.discover_dataset(
                    dataset_path,
                    device_model=device_model,
                    num_episodes=num_episodes
                )
                
                # 保存schema
                schema_file = self._save_schema(device_model, dataset['dataset_name'], schema)
                
                # 如果有converter config，进行诊断
                diagnosis = None
                if converter_config:
                    diagnosis = self.comparator.compare(schema, converter_config)
                    diagnosis_file = self._save_diagnosis(device_model, dataset['dataset_name'], diagnosis)
                    
                    # 统计错误和警告
                    model_report['total_errors'] += len(diagnosis.get('issues', []))
                    model_report['total_warnings'] += len(diagnosis.get('warnings', []))
                
                model_report['datasets_analyzed'] += 1
                model_report['datasets_details'].append({
                    'dataset_name': dataset['dataset_name'],
                    'dataset_uuid': dataset['dataset_uuid'],
                    'schema_file': str(schema_file),
                    'diagnosis_file': str(diagnosis_file) if diagnosis else None,
                    'num_errors': len(diagnosis.get('issues', [])) if diagnosis else 0,
                    'num_warnings': len(diagnosis.get('warnings', [])) if diagnosis else 0
                })
                
            except Exception as e:
                self.logger.error(f"  ✗ 分析失败: {e}")
                model_report['datasets_details'].append({
                    'dataset_name': dataset['dataset_name'],
                    'status': 'failed',
                    'error': str(e)
                })
        
        # 汇总常见问题
        self._summarize_common_issues(model_report)
        
        return model_report
    
    def _load_converter_config(self, device_model: str) -> Optional[Dict[str, Any]]:
        """加载device_model对应的converter config"""
        # 尝试查找config文件
        # 配置文件命名通常是 converter_config_<device_model>.yaml
        
        config_patterns = [
            f"converter_config_{device_model}.yaml",
            f"converter_config_{device_model}_*.yaml"
        ]
        
        for pattern in config_patterns:
            config_files = list(self.config_dir.glob(pattern))
            if config_files:
                # 如果有多个，取第一个（或最常用的版本）
                config_file = config_files[0]
                self.logger.info(f"加载配置文件: {config_file.name}")
                
                try:
                    return self.comparator.load_converter_config(config_file)
                except Exception as e:
                    self.logger.error(f"加载配置文件失败: {e}")
                    return None
        
        self.logger.warning(f"未找到 {device_model} 的converter config")
        return None
    
    def _save_schema(self, device_model: str, dataset_name: str, schema: Dict[str, Any]) -> Path:
        """保存schema到文件"""
        filename = f"{device_model}_{dataset_name}_schema.json"
        # 清理文件名中的非法字符
        filename = filename.replace('/', '_').replace(' ', '_')
        
        output_path = self.output_dir / 'schemas' / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        
        return output_path
    
    def _save_diagnosis(self, device_model: str, dataset_name: str, diagnosis: Dict[str, Any]) -> Path:
        """保存diagnosis到文件"""
        filename = f"{device_model}_{dataset_name}_diagnosis.json"
        filename = filename.replace('/', '_').replace(' ', '_')
        
        output_path = self.output_dir / 'diagnoses' / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(diagnosis, f, indent=2, ensure_ascii=False)
        
        return output_path
    
    def _summarize_common_issues(self, model_report: Dict[str, Any]):
        """汇总常见问题"""
        # TODO: 分析所有datasets_details，找出共同的issues
        # 这个可以帮助识别配置文件的系统性问题
        pass
    
    def _save_overall_report(self, report: Dict[str, Any]):
        """保存总体报告"""
        report_file = self.output_dir / 'overall_report.json'
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"\n✓ 总体报告已保存到: {report_file}")
    
    def _print_summary(self, report: Dict[str, Any]):
        """打印总结"""
        summary = report['summary']
        
        print("\n" + "=" * 70)
        print("总结")
        print("=" * 70)
        print(f"分析的Device Models: {summary['total_models_analyzed']}/{len(report['priority_models'])}")
        print(f"分析的数据集总数: {summary['total_datasets_analyzed']}")
        print(f"发现的错误总数: {summary['total_errors']}")
        print(f"发现的警告总数: {summary['total_warnings']}")
        print()
        
        # 按device_model打印详情
        for device_model, model_data in report['models_analysis'].items():
            if model_data.get('status') == 'failed':
                print(f"❌ {device_model}: 分析失败 - {model_data.get('error')}")
            elif model_data.get('status') == 'no_datasets':
                print(f"⚠️  {device_model}: 未找到数据集")
            else:
                print(f"✓ {device_model}: "
                      f"{model_data['datasets_analyzed']} 数据集, "
                      f"{model_data['total_errors']} 错误, "
                      f"{model_data['total_warnings']} 警告")
        
        print("=" * 70)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='批量Schema Discovery工具')
    parser.add_argument('--database', required=True, help='数据库路径')
    parser.add_argument('--config-dir', required=True, help='Converter配置文件目录')
    parser.add_argument('--output-dir', required=True, help='输出目录')
    parser.add_argument('--num-samples', type=int, default=5, 
                        help='每个device_model采样多少个数据集（默认5）')
    parser.add_argument('--num-episodes', type=int, default=5,
                        help='每个数据集采样多少个episodes（默认5）')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    
    # 设置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # 优先级device_model列表（从用户需求）
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
    
    # 创建工具并运行
    tool = BatchSchemaDiscovery(
        database_path=args.database,
        config_dir=Path(args.config_dir),
        output_dir=Path(args.output_dir)
    )
    
    tool.run_for_priority_models(
        priority_models=PRIORITY_MODELS,
        num_samples_per_model=args.num_samples,
        num_episodes_per_dataset=args.num_episodes
    )


if __name__ == '__main__':
    from typing import Optional
    main()

