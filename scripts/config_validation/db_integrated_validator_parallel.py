#!/usr/bin/env python3
"""数据库集成配置验证器（并行版本）

增强功能：
1. 多进程并行处理多个任务
2. Schema对比（配置vs实际）
3. 高亮显示不匹配
4. 自动修复建议

性能提升：2-5倍（取决于CPU核心数）

Usage:
    python db_integrated_validator_parallel.py --db-path /path/to/robocoin.db --output-dir /path/to/output --num-workers 4
"""

import argparse
import json
import logging
import multiprocessing as mp
import os
import random
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 添加src目录到Python路径
_project_root = Path(__file__).parent.parent.parent
_src_dir = _project_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from robocoin_dataset.utils.logger import setup_logger
from schema_comparator import SchemaComparator


def validate_single_task(task_data: Tuple[Dict[str, Any], int, Path, Path, int]) -> Dict[str, Any]:
    """
    验证单个任务（在子进程中执行）
    
    Args:
        task_data: (task, num_samples, output_dir, project_root, worker_id)
    
    Returns:
        验证结果字典
    """
    task, num_samples, output_dir, project_root, worker_id = task_data
    
    # 在子进程中设置logger
    logger = setup_logger(
        name=f"validator_worker_{worker_id}",
        log_dir=output_dir / "logs",
        level=logging.INFO
    )
    
    task_name = f"{task['device_model']}:{task['device_model_annotation']}"
    logger.info(f"[Worker {worker_id}] 🔍 验证任务: {task_name}")
    
    result = {
        "task_id": task["id"],
        "task_name": task_name,
        "device_model": task["device_model"],
        "device_model_annotation": task["device_model_annotation"],
        "dataset_path": task["dataset_path"],
        "converter_config": task["converter_config_path"],
        "sampled_episodes": [],
        "validation_status": "unknown",
        "schema_comparison": None,
        "errors": [],
        "warnings": [],
    }
    
    try:
        # 1. 导入必需的模块（在子进程中）
        sys.path.insert(0, str(project_root / 'scripts' / 'config_validation'))
        from converter_loader import create_converter_instance
        from schema_analyzer import SchemaAnalyzer
        
        # 2. 抽取episodes
        dataset_path = Path(task["dataset_path"])
        if not dataset_path.exists():
            raise FileNotFoundError(f"Dataset path not found: {dataset_path}")
        
        sampled_episodes = sample_episodes(dataset_path, task_name, num_samples, logger)
        
        if not sampled_episodes:
            result["validation_status"] = "skipped"
            result["errors"].append("No episodes found for sampling")
            return result
        
        # 3. 创建converter实例
        converter_config_path = Path(task["converter_config_path"])
        if not converter_config_path.is_absolute():
            converter_config_path = project_root / converter_config_path
        
        temp_output = output_dir / f"temp_worker_{worker_id}_{task_name.replace(':', '_')}"
        converter = create_converter_instance(
            config_file=converter_config_path,
            dataset_path=dataset_path,
            output_path=temp_output,
            logger=logger
        )
        
        # 4. 提取schema并对比
        analyzer = SchemaAnalyzer(logger=logger)
        comparator = SchemaComparator(logger=logger)
        
        for task_path, ep_idx in sampled_episodes:
            episode_result = {
                "task_path": str(task_path),
                "episode_index": ep_idx,
                "validation_status": "unknown",
                "actual_schema": None,
                "schema_comparison": None,
                "errors": [],
            }
            
            try:
                # 提取实际schema
                actual_schema = analyzer._extract_episode_schema_from_converter(
                    converter=converter,
                    episode_info={"task_path": task_path, "episode_idx": ep_idx, "type": "indexed"},
                    ep_idx=ep_idx
                )
                
                episode_result["actual_schema"] = actual_schema
                
                # 提取配置schema
                config_schema = extract_config_schema(converter)
                
                # 对比schema
                comparison = comparator.compare_schemas(config_schema, actual_schema)
                episode_result["schema_comparison"] = comparison
                
                # 确定验证状态
                if comparison['status'] == 'match':
                    episode_result["validation_status"] = "success"
                elif comparison['status'] == 'partial_match':
                    episode_result["validation_status"] = "warning"
                else:
                    episode_result["validation_status"] = "failed"
                    episode_result["errors"].append(f"Schema mismatch: {comparison['summary']['critical_issues']} critical issues")
                
            except Exception as e:
                episode_result["validation_status"] = "failed"
                episode_result["errors"].append(str(e))
                logger.error(f"[Worker {worker_id}] ❌ Episode {ep_idx} validation failed: {e}")
            
            result["sampled_episodes"].append(episode_result)
        
        # 5. 汇总验证状态
        success_count = sum(1 for ep in result["sampled_episodes"] if ep["validation_status"] == "success")
        warning_count = sum(1 for ep in result["sampled_episodes"] if ep["validation_status"] == "warning")
        failed_count = sum(1 for ep in result["sampled_episodes"] if ep["validation_status"] == "failed")
        
        if failed_count == 0 and warning_count == 0:
            result["validation_status"] = "success"
        elif failed_count == 0 and warning_count > 0:
            result["validation_status"] = "warning"
        elif success_count > 0:
            result["validation_status"] = "partial"
        else:
            result["validation_status"] = "failed"
        
        # 6. 汇总schema对比结果（使用第一个episode的对比结果）
        if result["sampled_episodes"] and result["sampled_episodes"][0].get("schema_comparison"):
            result["schema_comparison"] = result["sampled_episodes"][0]["schema_comparison"]
        
        logger.info(f"[Worker {worker_id}] ✅ 任务验证完成: {task_name} - {result['validation_status']}")
        
    except Exception as e:
        result["validation_status"] = "failed"
        result["errors"].append(f"Task validation error: {e}")
        logger.error(f"[Worker {worker_id}] ❌ 任务验证失败: {e}", exc_info=True)
    
    return result


def sample_episodes(
    dataset_path: Path,
    task_name: str,
    num_samples: int,
    logger: logging.Logger
) -> List[Tuple[Path, int]]:
    """
    从数据集中随机抽取episodes
    
    Args:
        dataset_path: 数据集路径
        task_name: 任务名称
        num_samples: 抽样数量
        logger: 日志记录器
    
    Returns:
        List[(task_path, episode_index)] - 抽样的episodes
    """
    logger.info(f"🎲 从任务 '{task_name}' 抽取episodes...")
    
    # 查找所有task_paths (包含local_task_info.yaml的目录)
    task_info_files = list(dataset_path.rglob("local_task_info.yaml"))
    
    if not task_info_files:
        logger.warning(f"⚠️ 任务 '{task_name}' 没有找到task_info文件")
        return []
    
    sampled_episodes = []
    
    for task_info_file in task_info_files:
        task_path = task_info_file.parent
        
        # 尝试估算episode数量
        episodes = estimate_episodes(task_path)
        
        if episodes == 0:
            continue
        
        # 随机抽取最多num_samples个episodes
        num_to_sample = min(num_samples, episodes)
        sampled_indices = random.sample(range(episodes), num_to_sample)
        
        for ep_idx in sampled_indices:
            sampled_episodes.append((task_path, ep_idx))
    
    logger.info(f"✅ 抽取了 {len(sampled_episodes)} 个episodes")
    return sampled_episodes


def estimate_episodes(task_path: Path) -> int:
    """估算task_path下的episode数量（简化实现）"""
    # 查找常见的episode标识
    # H5文件
    h5_files = list(task_path.glob("*.h5")) + list(task_path.glob("*.hdf5"))
    if h5_files:
        return len(h5_files)
    
    # MCAP文件
    mcap_files = list(task_path.glob("*.mcap"))
    if mcap_files:
        return len(mcap_files)
    
    # Episode目录
    episode_dirs = [d for d in task_path.iterdir() if d.is_dir() and "episode" in d.name.lower()]
    if episode_dirs:
        return len(episode_dirs)
    
    # 默认返回1（假设至少有1个episode）
    return 1


def extract_config_schema(converter: Any) -> Dict[str, Any]:
    """
    从converter配置中提取expected schema
    
    Args:
        converter: Converter实例
    
    Returns:
        配置中定义的schema
    """
    config_schema = {
        'observation': {'state': {}, 'images': {}},
        'action': {}
    }
    
    try:
        if hasattr(converter, 'converter_config'):
            config = converter.converter_config
            features = config.get('features', {})
            
            # 提取observation.state的expected shape
            obs_config = features.get('observation', {})
            state_config = obs_config.get('state', {})
            if 'sub_state' in state_config:
                # 计算总维度
                total_dims = 0
                for sub_state in state_config['sub_state']:
                    names = sub_state.get('names', [])
                    total_dims += len(names)
                config_schema['observation']['state'] = {
                    'expected_shape': [total_dims],
                    'expected_dtype': 'float32'  # 默认
                }
            
            # 提取observation.images
            image_configs = obs_config.get('image', [])
            for img_config in image_configs:
                cam_name = img_config.get('cam_name')
                if cam_name:
                    config_schema['observation']['images'][cam_name] = {
                        'expected_shape': [720, 1280, 3],  # 默认，实际应从配置获取
                        'expected_dtype': 'uint8'
                    }
            
            # 提取action的expected shape
            action_config = features.get('action', {})
            if 'sub_action' in action_config:
                total_dims = 0
                for sub_action in action_config['sub_action']:
                    names = sub_action.get('names', [])
                    total_dims += len(names)
                config_schema['action'] = {
                    'expected_shape': [total_dims],
                    'expected_dtype': 'float32'
                }
    
    except Exception as e:
        print(f"Warning: Failed to extract config schema: {e}")
    
    return config_schema


class DBIntegratedValidatorParallel:
    """数据库集成配置验证器（并行版本）"""
    
    def __init__(
        self,
        db_path: Path,
        output_dir: Path,
        num_samples_per_task: int = 2,
        num_workers: int = None,
        logger: Optional[logging.Logger] = None
    ):
        """初始化
        
        Args:
            db_path: 数据库文件路径
            output_dir: 输出目录
            num_samples_per_task: 每个任务抽取的episode数量
            num_workers: 并行worker数量（None=自动检测CPU核心数）
            logger: 日志记录器
        """
        self.db_path = db_path
        self.output_dir = output_dir
        self.num_samples_per_task = num_samples_per_task
        self.num_workers = num_workers or max(1, mp.cpu_count() - 1)
        self.logger = logger or logging.getLogger(__name__)
        self.project_root = _project_root
        
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 验证数据库存在
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")
        
        self.logger.info(f"🚀 并行验证器初始化: {self.num_workers} workers")
    
    def connect_db(self) -> sqlite3.Connection:
        """连接数据库"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def fetch_tasks(self) -> List[Dict[str, Any]]:
        """从device_model_annotation表获取所有任务"""
        self.logger.info("📊 从数据库读取任务列表...")
        
        conn = self.connect_db()
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT 
                    id,
                    device_model,
                    device_model_annotation,
                    dataset_path,
                    repo_id,
                    converter_config_path,
                    converter_module,
                    converter_class
                FROM device_model_annotation
                WHERE dataset_path IS NOT NULL
                    AND dataset_path != ''
                    AND converter_config_path IS NOT NULL
                    AND converter_config_path != ''
                ORDER BY device_model, device_model_annotation
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            tasks = []
            for row in rows:
                tasks.append({
                    "id": row["id"],
                    "device_model": row["device_model"],
                    "device_model_annotation": row["device_model_annotation"],
                    "dataset_path": row["dataset_path"],
                    "repo_id": row["repo_id"],
                    "converter_config_path": row["converter_config_path"],
                    "converter_module": row["converter_module"],
                    "converter_class": row["converter_class"],
                })
            
            self.logger.info(f"✅ 找到 {len(tasks)} 个任务")
            return tasks
            
        finally:
            conn.close()
    
    def run(self) -> Path:
        """运行完整的并行验证流程
        
        Returns:
            报告文件路径
        """
        start_time = time.time()
        self.logger.info("🚀 启动数据库集成配置验证器（并行模式）...")
        self.logger.info(f"⚡ 使用 {self.num_workers} 个并行workers")
        
        # 1. 获取任务列表
        tasks = self.fetch_tasks()
        
        if not tasks:
            self.logger.warning("⚠️ 没有找到任务，退出")
            return None
        
        # 2. 准备任务数据（为每个worker准备）
        task_data_list = [
            (task, self.num_samples_per_task, self.output_dir, self.project_root, i % self.num_workers)
            for i, task in enumerate(tasks)
        ]
        
        # 3. 并行验证
        self.logger.info(f"🔄 开始并行验证 {len(tasks)} 个任务...")
        
        validation_results = []
        
        if self.num_workers == 1:
            # 单进程模式（用于调试）
            for task_data in task_data_list:
                result = validate_single_task(task_data)
                validation_results.append(result)
        else:
            # 多进程模式
            with mp.Pool(processes=self.num_workers) as pool:
                validation_results = pool.map(validate_single_task, task_data_list)
        
        # 4. 生成报告
        self.logger.info(f"\n{'='*70}")
        elapsed_time = time.time() - start_time
        report_path = self.generate_report(validation_results, elapsed_time)
        
        self.logger.info(f"\n✅ 数据库集成配置验证完成！")
        self.logger.info(f"⏱️  总耗时: {elapsed_time:.2f} 秒")
        self.logger.info(f"⚡ 并行加速比: ~{len(tasks)/elapsed_time:.1f} 任务/秒")
        
        return report_path
    
    def generate_report(
        self,
        validation_results: List[Dict[str, Any]],
        elapsed_time: float
    ) -> Path:
        """生成详细的JSON报告"""
        # 统计不同状态的任务数量
        status_counts = {}
        for result in validation_results:
            status = result.get('validation_status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        report_data = {
            "metadata": {
                "validation_date": datetime.now().isoformat(),
                "database_path": str(self.db_path),
                "total_tasks": len(validation_results),
                "samples_per_task": self.num_samples_per_task,
                "num_workers": self.num_workers,
                "elapsed_time_seconds": round(elapsed_time, 2),
                "performance": {
                    "tasks_per_second": round(len(validation_results) / elapsed_time, 2),
                    "estimated_speedup": f"{self.num_workers}x (theoretical)"
                }
            },
            "summary": {
                "total_tasks": len(validation_results),
                "successful_tasks": status_counts.get('success', 0),
                "warning_tasks": status_counts.get('warning', 0),
                "partial_tasks": status_counts.get('partial', 0),
                "failed_tasks": status_counts.get('failed', 0),
                "skipped_tasks": status_counts.get('skipped', 0),
                "status_breakdown": status_counts
            },
            "validation_results": validation_results,
        }
        
        # 保存报告
        report_filename = f"db_validation_report_parallel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = self.output_dir / report_filename
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"✅ 验证报告已保存: {report_path}")
        self.logger.info(f"   - 总任务数: {report_data['summary']['total_tasks']}")
        self.logger.info(f"   - 成功: {report_data['summary']['successful_tasks']}")
        self.logger.info(f"   - 警告: {report_data['summary']['warning_tasks']}")
        self.logger.info(f"   - 部分成功: {report_data['summary']['partial_tasks']}")
        self.logger.info(f"   - 失败: {report_data['summary']['failed_tasks']}")
        self.logger.info(f"   - 跳过: {report_data['summary']['skipped_tasks']}")
        
        return report_path


def main():
    parser = argparse.ArgumentParser(description="数据库集成配置验证器（并行版本）")
    parser.add_argument(
        "--db-path",
        type=Path,
        required=True,
        help="数据库文件路径 (robocoin.db)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/db_validation_parallel"),
        help="输出目录 (默认: outputs/db_validation_parallel)"
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=2,
        help="每个任务抽取的episode数量 (默认: 2)"
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=None,
        help="并行worker数量 (默认: CPU核心数-1)"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别"
    )
    
    args = parser.parse_args()
    
    # 设置日志
    logger = setup_logger(
        name="db_integrated_validator_parallel",
        log_dir=args.output_dir / "logs",
        level=getattr(logging, args.log_level)
    )
    
    # 运行验证
    validator = DBIntegratedValidatorParallel(
        db_path=args.db_path,
        output_dir=args.output_dir,
        num_samples_per_task=args.num_samples,
        num_workers=args.num_workers,
        logger=logger
    )
    
    try:
        report_path = validator.run()
        if report_path:
            print(f"\n✅ 验证完成！报告已保存到: {report_path}")
            sys.exit(0)
        else:
            print("\n⚠️ 验证未能生成报告")
            sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 验证过程发生错误: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

