#!/usr/bin/env python3
"""数据库集成配置验证器

从device_model_annotation表读取任务，为每个任务随机抽取2个episodes进行配置验证。
生成详细的JSON报告。

Usage:
    python db_integrated_validator.py --db-path /path/to/robocoin.db --output-dir /path/to/output
"""

import argparse
import json
import logging
import random
import sqlite3
import sys,os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple ,Iterator

# 添加src目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
_project_root = Path(__file__).parent.parent.parent
_src_dir = _project_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from robocoin_dataset.utils.logger import setup_logger


class DBIntegratedValidator:
    """数据库集成配置验证器"""
    
    def __init__(
        self,
        db_path: Path,
        output_dir: Path,
        num_samples_per_task: int = 2,
        logger: Optional[logging.Logger] = None
    ):
        """初始化
        
        Args:
            db_path: 数据库文件路径
            output_dir: 输出目录
            num_samples_per_task: 每个任务抽取的episode数量
            logger: 日志记录器
        """
        self.db_path = db_path
        self.output_dir = output_dir
        self.num_samples_per_task = num_samples_per_task
        self.logger = logger or logging.getLogger(__name__)
        
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 验证数据库存在
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")
    
    def connect_db(self) -> sqlite3.Connection:
        """连接数据库"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 返回字典形式的行
        return conn
    
    def fetch_tasks(self) -> List[Dict[str, Any]]:
        """从device_model_annotation表获取所有任务
        
        Returns:
            任务列表，每个任务包含: id, device_model, device_model_annotation, dataset_path, etc.
        """
        self.logger.info("📊 从数据库读取任务列表...")
        
        conn = self.connect_db()
        cursor = conn.cursor()
        
        try:  
            # 查询device_model_annotation表
            query = """
                SELECT 
                    dma.id,
                    d.device_model,
                    dma.device_model_version AS device_model_annotation,
                    d.yaml_file_path AS dataset_path,
                    d.dataset_uuid AS repo_id,
                    dma.annotatio_file_path AS converter_config_path,
                    dma.device_model AS converter_module,
                    dma.device_model_version AS converter_class
                FROM device_model_annotation AS dma
                LEFT JOIN datasets AS d
                       ON dma.dataset_uuid = d.dataset_uuid
                WHERE dma.annotatio_file_path IS NOT NULL
                    AND dma.annotatio_file_path != ''
                    AND dma.device_model IS NOT NULL
                    AND dma.device_model_version != ''
                ORDER BY dma.device_model, dma.device_model_version
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
            
    def _rglob_prune(self, root: Path, pattern: str, max_depth: int = 2) -> Iterator[Path]:
        if max_depth < 0:
            return
        for p in root.iterdir():
            if p.is_dir():
                found = list(p.glob(pattern))
                if found:
                    yield from found
                    continue            
                yield from self._rglob_prune(p, pattern, max_depth - 1)
            elif p.match(pattern):
                yield p
            
    def sample_episodes(self, dataset_path: Path, task_name: str) -> List[Tuple[Path, int]]:
        """从数据集中随机抽取episodes
        
        Args:
            dataset_path: 数据集路径
            task_name: 任务名称
        
        Returns:
            List[(task_path, episode_index)] - 抽样的episodes
        """
        self.logger.info(f"🎲 从任务 '{task_name}' 抽取episodes...")
        
        # 查找所有task_paths (包含local_task_info.yaml的目录)
        search_root = dataset_path.parent if dataset_path.is_file() else dataset_path
        task_info_files = list(self._rglob_prune(search_root, "local_task_info.yaml"))
        
        if not task_info_files:
            self.logger.warning(f"⚠️ 任务 '{task_name}' 没有找到task_info文件")
            return []
        
        sampled_episodes = []
        
        for task_info_file in task_info_files:
            task_path = task_info_file.parent
            
            # 尝试估算episode数量（简化实现）
            # 这里可以根据具体数据格式调整
            episodes = self._estimate_episodes(task_path)
            
            if episodes == 0:
                continue
            
            # 随机抽取最多num_samples_per_task个episodes
            num_to_sample = min(self.num_samples_per_task, episodes)
            sampled_indices = random.sample(range(episodes), num_to_sample)
            
            for ep_idx in sampled_indices:
                sampled_episodes.append((task_path, ep_idx))
        
        self.logger.info(f"✅ 抽取了 {len(sampled_episodes)} 个episodes")
        return sampled_episodes
    
    def _estimate_episodes(self, task_path: Path) -> int:
        """估算task_path下的episode数量（简化实现）
        
        Args:
            task_path: 任务路径
        
        Returns:
            估算的episode数量
        """
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
    
    def validate_task(
        self,
        task: Dict[str, Any],
        sampled_episodes: List[Tuple[Path, int]]
    ) -> Dict[str, Any]:
        """验证单个任务的配置
        
        Args:
            task: 任务信息
            sampled_episodes: 抽样的episodes
        
        Returns:
            验证结果字典
        """
        from config_validation.converter_loader import create_converter_instance
        from config_validation.schema_analyzer import SchemaAnalyzer
        
        task_name = f"{task['device_model']}:{task['device_model_annotation']}"
        self.logger.info(f"🔍 验证任务: {task_name}")
        
        result = {
            "task_id": task["id"],
            "task_name": task_name,
            "device_model": task["device_model"],
            "device_model_annotation": task["device_model_annotation"],
            "dataset_path": task["dataset_path"],
            "converter_config": task["converter_config_path"],
            "sampled_episodes": [],
            "validation_status": "unknown",
            "errors": [],
            "warnings": [],
        }
        
        try:
            # 1. 创建converter实例
            converter_config_path = Path(task["converter_config_path"])
            if not converter_config_path.is_absolute():
                converter_config_path = _project_root / converter_config_path
            
            converter = create_converter_instance(
                module_path=task["converter_module"] or "converters.mcap",
                class_name=task["converter_class"] or "McapConverter",
                repo_id=task["repo_id"],
                config_file=converter_config_path,
                dataset_path=Path(task["dataset_path"]),
                output_path=self.output_dir / 
                f"temp_{task_name.replace(':', '_')}",
                logger=self.logger,
            )           
            
            # 2. 为每个抽样的episode运行Schema分析
            analyzer = SchemaAnalyzer(logger=self.logger)
            
            for task_path, ep_idx in sampled_episodes:
                episode_result = {
                    "task_path": str(task_path),
                    "episode_index": ep_idx,
                    "validation_status": "unknown",
                    "schema": None,
                    "errors": [],
                }
                
                try:
                    # 提取schema
                    schema = analyzer._extract_episode_schema_from_converter(
                        converter=converter,
                        episode_info={"task_path": task_path, "episode_idx": ep_idx, "type": "indexed"}
                    )
                    
                    episode_result["schema"] = schema
                    episode_result["validation_status"] = "success"
                    
                except Exception as e:
                    episode_result["validation_status"] = "failed"
                    episode_result["errors"].append(str(e))
                
                result["sampled_episodes"].append(episode_result)
            
            # 3. 汇总验证状态
            if all(ep["validation_status"] == "success" for ep in result["sampled_episodes"]):
                result["validation_status"] = "success"
            elif any(ep["validation_status"] == "success" for ep in result["sampled_episodes"]):
                result["validation_status"] = "partial"
            else:
                result["validation_status"] = "failed"
            
        except Exception as e:
            result["validation_status"] = "failed"
            result["errors"].append(f"Task validation error: {e}")
            self.logger.error(f"❌ 任务验证失败: {e}")
        
        return result
    
    def generate_report(self, validation_results: List[Dict[str, Any]]) -> Path:
        """生成详细的JSON报告
        
        Args:
            validation_results: 所有任务的验证结果
        
        Returns:
            报告文件路径
        """
        report_data = {
            "metadata": {
                "validation_date": datetime.now().isoformat(),
                "database_path": str(self.db_path),
                "total_tasks": len(validation_results),
                "samples_per_task": self.num_samples_per_task,
            },
            "summary": {
                "total_tasks": len(validation_results),
                "successful_tasks": sum(1 for r in validation_results if r["validation_status"] == "success"),
                "partial_tasks": sum(1 for r in validation_results if r["validation_status"] == "partial"),
                "failed_tasks": sum(1 for r in validation_results if r["validation_status"] == "failed"),
            },
            "validation_results": validation_results,
        }
        
        # 保存报告
        report_filename = f"db_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = self.output_dir / report_filename
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"✅ 验证报告已保存: {report_path}")
        self.logger.info(f"   - 总任务数: {report_data['summary']['total_tasks']}")
        self.logger.info(f"   - 成功: {report_data['summary']['successful_tasks']}")
        self.logger.info(f"   - 部分成功: {report_data['summary']['partial_tasks']}")
        self.logger.info(f"   - 失败: {report_data['summary']['failed_tasks']}")
        
        return report_path
    
    def run(self) -> Path:
        """运行完整的验证流程
        
        Returns:
            报告文件路径
        """
        self.logger.info("🚀 启动数据库集成配置验证器...")
        
        # 1. 获取任务列表
        tasks = self.fetch_tasks()
        
        if not tasks:
            self.logger.warning("⚠️ 没有找到任务，退出")
            return None
        
        # 2. 为每个任务进行验证
        validation_results = []
        
        for i, task in enumerate(tasks, 1):
            self.logger.info(f"\n{'='*70}")
            self.logger.info(f"处理任务 {i}/{len(tasks)}")
            
            # 抽取episodes
            dataset_path = Path(task["dataset_path"])
            task_name = f"{task['device_model']}:{task['device_model_annotation']}"
            
            if not dataset_path.exists():
                self.logger.warning(f"⚠️ 数据集路径不存在: {dataset_path}")
                validation_results.append({
                    "task_id": task["id"],
                    "task_name": task_name,
                    "validation_status": "failed",
                    "errors": [f"Dataset path not found: {dataset_path}"],
                })
                continue
            
            sampled_episodes = self.sample_episodes(dataset_path, task_name)
            
            if not sampled_episodes:
                self.logger.warning(f"⚠️ 未能抽取到episodes，跳过")
                validation_results.append({
                    "task_id": task["id"],
                    "task_name": task_name,
                    "validation_status": "skipped",
                    "errors": ["No episodes found for sampling"],
                })
                continue
            
            # 验证任务
            result = self.validate_task(task, sampled_episodes)
            validation_results.append(result)
        
        # 3. 生成报告
        self.logger.info(f"\n{'='*70}")
        report_path = self.generate_report(validation_results)
        
        self.logger.info("\n✅ 数据库集成配置验证完成！")
        return report_path


def main():
    parser = argparse.ArgumentParser(description="数据库集成配置验证器")
    parser.add_argument(
        "--db-path",
        type=Path,
        required=True,
        help="数据库文件路径 (robocoin.db)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/db_validation"),
        help="输出目录 (默认: outputs/db_validation)"
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=2,
        help="每个任务抽取的episode数量 (默认: 2)"
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
        name="db_integrated_validator",
        log_dir=args.output_dir / "logs",
        level=getattr(logging, args.log_level)
    )
    
    # 运行验证
    validator = DBIntegratedValidator(
        db_path=args.db_path,
        output_dir=args.output_dir,
        num_samples_per_task=args.num_samples,
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

