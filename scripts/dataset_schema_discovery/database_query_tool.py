"""
数据库查询工具

从数据库查询数据集信息，用于批量Schema Discovery。
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
import sys

# 添加项目路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / 'src'))

from robocoin_dataset.database.models import DatasetDB
from robocoin_dataset.database.database import DatasetDatabase


class DatabaseQueryTool:
    """数据库查询工具"""
    
    def __init__(self, database_path: str, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.db = DatasetDatabase(Path(database_path))
        self.session = None
    
    def __enter__(self):
        self.session = self.db.session_local()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
    
    def query_datasets_by_device_model(
        self, 
        device_model: str, 
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        根据device_model查询数据集
        
        Args:
            device_model: 设备型号（支持前缀匹配）
            limit: 最多返回多少条（None表示不限制）
            
        Returns:
            数据集信息列表
        """
        if not self.session:
            raise RuntimeError("请使用 'with' 语句创建DatabaseQueryTool实例")
        
        # 直接查询DatasetDB（支持前缀匹配）
        query = self.session.query(DatasetDB).filter(
            DatasetDB.device_model.like(f"{device_model}%")
        )
        
        if limit:
            query = query.limit(limit)
        
        datasets = query.all()
        
        # 转换为字典列表
        result = []
        for dataset in datasets:
            # 数据集路径 = yaml_file_path的父目录
            dataset_path = None
            if dataset.yaml_file_path:
                dataset_path = str(Path(dataset.yaml_file_path).parent)
            
            result.append({
                'dataset_uuid': dataset.dataset_uuid,
                'dataset_name': dataset.dataset_name,
                'dataset_path': dataset_path,
                'device_model': dataset.device_model,
                'device_model_version': dataset.device_model_version,
                'created_at': getattr(dataset, 'created_at', None).isoformat() if hasattr(dataset, 'created_at') and dataset.created_at else None,
            })
        
        self.logger.info(f"找到 {len(result)} 个 {device_model} 数据集")
        
        return result

    def query_all_device_models(self) -> List[Dict[str, Any]]:
        """
        查询所有device_model及其数据集数量
        
        Returns:
            device_model统计列表
        """
        if not self.session:
            raise RuntimeError("请使用 'with' 语句创建DatabaseQueryTool实例")
        
        from sqlalchemy import func
        
        # 按device_model分组统计
        results = self.session.query(
            DatasetDB.device_model,
            DatasetDB.device_model_version,
            func.count(DatasetDB.dataset_uuid).label('count')
        ).group_by(
            DatasetDB.device_model,
            DatasetDB.device_model_version
        ).all()
        
        device_models = []
        for device_model, version, count in results:
            if not device_model:  # 跳过没有device_model的记录
                continue
                
            device_models.append({
                'device_model': device_model,
                'device_model_version': version,
                'dataset_count': count
            })
        
        # 按数量排序
        device_models.sort(key=lambda x: x['dataset_count'], reverse=True)
        
        return device_models
    
    def sample_datasets_for_device_model(
        self,
        device_model: str,
        num_samples: int = 5,
        strategy: str = 'first'
    ) -> List[Dict[str, Any]]:
        """
        为指定device_model采样数据集
        
        Args:
            device_model: 设备型号
            num_samples: 采样数量
            strategy: 采样策略
                - 'first': 取前N个
                - 'random': 随机采样N个
                - 'recent': 取最近的N个
                
        Returns:
            采样的数据集列表
        """
        datasets = self.query_datasets_by_device_model(device_model)
        
        if len(datasets) <= num_samples:
            return datasets
        
        if strategy == 'first':
            return datasets[:num_samples]
        
        elif strategy == 'random':
            import random
            return random.sample(datasets, num_samples)
        
        elif strategy == 'recent':
            # 按created_at排序，取最近的
            datasets_with_date = [d for d in datasets if d.get('created_at')]
            datasets_with_date.sort(key=lambda x: x['created_at'], reverse=True)
            return datasets_with_date[:num_samples]
        
        else:
            raise ValueError(f"Unknown sampling strategy: {strategy}")
    
    def get_priority_device_models(
        self,
        priority_list: List[str]
    ) -> List[Dict[str, Any]]:
        """
        获取优先级列表中的device_model信息
        
        Args:
            priority_list: device_model优先级列表
            
        Returns:
            每个device_model的统计信息
        """
        all_models = self.query_all_device_models()
        
        result = []
        for priority_model in priority_list:
            # 查找匹配的device_model（支持前缀匹配）
            matched = [
                m for m in all_models 
                if m['device_model'].startswith(priority_model)
            ]
            
            if matched:
                # 如果有多个版本，汇总
                total_count = sum(m['dataset_count'] for m in matched)
                versions = [m['device_model_version'] for m in matched]
                
                result.append({
                    'device_model': priority_model,
                    'versions': versions,
                    'total_datasets': total_count,
                    'version_details': matched
                })
            else:
                result.append({
                    'device_model': priority_model,
                    'versions': [],
                    'total_datasets': 0,
                    'version_details': [],
                    'warning': 'Not found in database'
                })
        
        return result


def main():
    """测试数据库查询工具"""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='数据库查询工具')
    parser.add_argument('--database', required=True, help='数据库路径')
    parser.add_argument('--action', choices=['list', 'query', 'sample'], 
                        default='list', help='操作类型')
    parser.add_argument('--device-model', help='设备型号（query/sample时使用）')
    parser.add_argument('--num-samples', type=int, default=5, 
                        help='采样数量（sample时使用）')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
    with DatabaseQueryTool(args.database) as db_tool:
        if args.action == 'list':
            # 列出所有device_model
            models = db_tool.query_all_device_models()
            print("\n设备型号统计:")
            print("=" * 70)
            for model in models:
                print(f"{model['device_model']:40} "
                      f"v{model['device_model_version']:20} "
                      f"{model['dataset_count']:5}个数据集")
        
        elif args.action == 'query':
            if not args.device_model:
                print("错误: --device-model 参数必须提供")
                sys.exit(1)
            
            datasets = db_tool.query_datasets_by_device_model(args.device_model)
            print(json.dumps(datasets, indent=2, ensure_ascii=False))
        
        elif args.action == 'sample':
            if not args.device_model:
                print("错误: --device-model 参数必须提供")
                sys.exit(1)
            
            samples = db_tool.sample_datasets_for_device_model(
                args.device_model, 
                num_samples=args.num_samples
            )
            print(json.dumps(samples, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

