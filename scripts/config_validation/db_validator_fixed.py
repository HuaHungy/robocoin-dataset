#!/usr/bin/env python3
"""数据库集成配置验证器（修正版）

基于实际数据库结构：
- 从 device_model_annotation 表读取任务列表
- 优先使用 annotatio_file_path（生产环境NAS路径）
- 回退到本地映射 data/{device_model}:{device_model_version}/（开发环境）
- 从 converter_factory_config.yaml 获取converter配置
- 验证配置并生成报告

使用场景：
1. 生产环境（NAS已挂载）：直接使用 annotatio_file_path
2. 开发环境（NAS未挂载）：回退到本地 data/ 目录

Usage:
    # 生产环境（NAS路径可用）
    python db_validator_fixed.py --db-path /path/to/database.db
    
    # 开发环境（本地路径）
    python db_validator_fixed.py --db-path /path/to/database.db --data-root data/
"""

import argparse
import json
import logging
import random
import sqlite3
import sys
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 添加src目录到Python路径
_project_root = Path(__file__).parent.parent.parent
_src_dir = _project_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from robocoin_dataset.utils.logger import setup_logger


class DBValidatorFixed:
    """数据库集成配置验证器（修正版）"""
    
    def __init__(
        self,
        db_path: Path,
        data_root: Path,
        factory_config_path: Path,
        output_dir: Path,
        num_samples_per_task: int = 2,
        logger: Optional[logging.Logger] = None
    ):
        """初始化
        
        Args:
            db_path: 数据库文件路径
            data_root: 本地数据根目录（默认：data/）
            factory_config_path: converter factory配置文件路径
            output_dir: 输出目录
            num_samples_per_task: 每个任务抽取的episode数量
            logger: 日志记录器
        """
        self.db_path = db_path
        self.data_root = data_root
        self.factory_config_path = factory_config_path
        self.output_dir = output_dir
        self.num_samples_per_task = num_samples_per_task
        self.logger = logger or logging.getLogger(__name__)
        
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 验证文件存在
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")
        if not self.data_root.exists():
            raise FileNotFoundError(f"Data root not found: {self.data_root}")
        if not self.factory_config_path.exists():
            raise FileNotFoundError(f"Factory config not found: {self.factory_config_path}")
        
        # 加载factory配置
        self.factory_config = self._load_factory_config()
        
        self.logger.info(f"✅ Validator initialized")
        self.logger.info(f"   Database: {self.db_path}")
        self.logger.info(f"   Data root: {self.data_root}")
        self.logger.info(f"   Factory config: {self.factory_config_path}")
    
    def _load_factory_config(self) -> Dict[str, Any]:
        """加载converter factory配置"""
        with open(self.factory_config_path) as f:
            return yaml.safe_load(f)
    
    def connect_db(self) -> sqlite3.Connection:
        """连接数据库"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def fetch_tasks_from_db(self) -> List[Dict[str, Any]]:
        """从device_model_annotation表获取所有任务
        
        Returns:
            任务列表，每个任务包含：
            - dataset_uuid
            - device_model
            - device_model_version
            - annotation_status
            - annotatio_file_path (NAS路径，仅供参考)
        """
        self.logger.info("📊 从数据库读取任务列表...")
        
        conn = self.connect_db()
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT 
                    dataset_uuid,
                    device_model,
                    device_model_version,
                    annotation_status,
                    annotatio_file_path
                FROM device_model_annotation
                WHERE device_model IS NOT NULL
                    AND device_model != ''
                    AND device_model_version IS NOT NULL
                    AND device_model_version != ''
                ORDER BY device_model, device_model_version
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            tasks = []
            for row in rows:
                tasks.append({
                    "dataset_uuid": row["dataset_uuid"],
                    "device_model": row["device_model"],
                    "device_model_version": row["device_model_version"],
                    "annotation_status": row["annotation_status"],
                    "annotatio_file_path": row["annotatio_file_path"],
                })
            
            self.logger.info(f"✅ 从数据库找到 {len(tasks)} 个任务")
            return tasks
            
        finally:
            conn.close()
    
    def map_db_task_to_local(self, db_task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """将数据库任务映射到本地配置
        
        Args:
            db_task: 数据库任务信息
        
        Returns:
            完整的任务配置，如果映射失败则返回None
        """
        device_model = db_task["device_model"]
        device_model_version = db_task["device_model_version"]
        
        # 1. 确定数据集路径（优先使用NAS路径，回退到本地路径）
        dataset_path = None
        path_source = None
        
        # 1.1 优先使用数据库中的 annotatio_file_path（生产环境NAS路径）
        db_path_str = db_task.get("annotatio_file_path")
        if db_path_str:
            db_path = Path(db_path_str)
            if db_path.exists():
                dataset_path = db_path
                path_source = "NAS"
                self.logger.debug(f"✅ 使用NAS路径: {dataset_path}")
            else:
                self.logger.debug(f"⚠️  NAS路径不存在: {db_path}")
        
        # 1.2 回退到本地映射路径（开发环境）
        if dataset_path is None:
            local_path = self.data_root / f"{device_model}:{device_model_version}"
            if local_path.exists():
                dataset_path = local_path
                path_source = "local"
                self.logger.debug(f"✅ 使用本地路径: {dataset_path}")
            else:
                self.logger.debug(f"⚠️  本地路径不存在: {local_path}")
        
        # 1.3 都不存在，无法继续
        if dataset_path is None:
            self.logger.warning(
                f"⚠️  数据集路径不存在: {device_model}:{device_model_version}\n"
                f"   NAS路径: {db_path_str or 'N/A'}\n"
                f"   本地路径: {self.data_root / f'{device_model}:{device_model_version}'}"
            )
            return None
        
        # 2. 从factory config查找converter配置
        if device_model not in self.factory_config:
            self.logger.warning(f"⚠️  设备模型未在factory config中定义: {device_model}")
            return None
        
        # 查找对应version的配置
        versions = self.factory_config[device_model]
        converter_info = None
        for version_config in versions:
            if version_config.get('version') == device_model_version:
                converter_info = version_config
                break
        
        if not converter_info:
            self.logger.warning(
                f"⚠️  版本未在factory config中定义: {device_model}:{device_model_version}"
            )
            return None
        
        # 3. 构建converter配置文件路径
        converter_config_path = (
            self.factory_config_path.parent / converter_info['converter_config_path']
        )
        
        if not converter_config_path.exists():
            self.logger.warning(f"⚠️  Converter配置文件不存在: {converter_config_path}")
            return None
        
        # 4. 返回完整配置
        return {
            "dataset_uuid": db_task["dataset_uuid"],
            "device_model": device_model,
            "device_model_version": device_model_version,
            "task_name": f"{device_model}:{device_model_version}",
            "dataset_path": str(dataset_path),
            "path_source": path_source,  # "NAS" 或 "local"
            "converter_module": converter_info['module'],
            "converter_class": converter_info['class'],
            "converter_config_path": str(converter_config_path),
            "annotation_status": db_task["annotation_status"],
        }
    
    def filter_local_available_tasks(
        self,
        db_tasks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """过滤出本地可用的任务
        
        Args:
            db_tasks: 数据库任务列表
        
        Returns:
            本地可用的任务列表（已映射）
        """
        self.logger.info("🔍 映射数据库任务到本地配置...")
        
        available_tasks = []
        skipped_count = 0
        
        for db_task in db_tasks:
            mapped_task = self.map_db_task_to_local(db_task)
            if mapped_task:
                available_tasks.append(mapped_task)
            else:
                skipped_count += 1
        
        self.logger.info(f"✅ 本地可用任务: {len(available_tasks)}")
        self.logger.info(f"⏭️  跳过任务: {skipped_count}")
        
        return available_tasks
    
    def sample_episodes(
        self,
        dataset_path: Path,
        task_name: str
    ) -> List[Tuple[Path, int]]:
        """从数据集中随机抽取episodes
        
        Args:
            dataset_path: 数据集路径
            task_name: 任务名称
        
        Returns:
            List[(task_path, episode_index)] - 抽样的episodes
        """
        self.logger.info(f"🎲 从任务 '{task_name}' 抽取episodes...")
        
        # 查找所有task_paths (包含local_task_info.yaml的目录)
        task_info_files = list(dataset_path.rglob("local_task_info.yaml"))
        
        if not task_info_files:
            self.logger.warning(f"⚠️  任务 '{task_name}' 没有找到task_info文件")
            return []
        
        sampled_episodes = []
        
        for task_info_file in task_info_files:
            task_path = task_info_file.parent
            
            # 尝试估算episode数量
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
        """估算task_path下的episode数量"""
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
        
        # 默认返回1
        return 1
    
    def validate_task(
        self,
        task: Dict[str, Any]
    ) -> Dict[str, Any]:
        """验证单个任务
        
        Args:
            task: 任务信息
        
        Returns:
            验证结果字典
        """
        task_name = task["task_name"]
        self.logger.info(f"🔍 验证任务: {task_name}")
        
        result = {
            "task_name": task_name,
            "dataset_uuid": task["dataset_uuid"],
            "device_model": task["device_model"],
            "device_model_version": task["device_model_version"],
            "dataset_path": task["dataset_path"],
            "converter_config": task["converter_config_path"],
            "converter_module": task["converter_module"],
            "converter_class": task["converter_class"],
            "sampled_episodes": [],
            "validation_status": "unknown",
            "errors": [],
            "warnings": [],
        }
        
        try:
            # 1. 导入converter_loader和schema_analyzer
            sys.path.insert(0, str(_project_root / 'scripts' / 'config_validation'))
            from converter_loader import create_converter_instance
            from schema_analyzer import SchemaAnalyzer
            
            # 2. 抽取episodes
            dataset_path = Path(task["dataset_path"])
            sampled_episodes = self.sample_episodes(dataset_path, task_name)
            
            if not sampled_episodes:
                result["validation_status"] = "skipped"
                result["warnings"].append("No episodes found for sampling")
                return result
            
            # 3. 创建converter实例
            temp_output = self.output_dir / f"temp_{task_name.replace(':', '_')}"
            converter = create_converter_instance(
                config_file=Path(task["converter_config_path"]),
                dataset_path=dataset_path,
                output_path=temp_output,
                logger=self.logger
            )
            
            # 4. 提取schema
            analyzer = SchemaAnalyzer(logger=self.logger)
            
            for task_path, ep_idx in sampled_episodes:
                episode_result = {
                    "task_path": str(task_path.relative_to(dataset_path)),
                    "episode_index": ep_idx,
                    "validation_status": "unknown",
                    "schema": None,
                    "errors": [],
                }
                
                try:
                    schema = analyzer._extract_episode_schema_from_converter(
                        converter=converter,
                        episode_info={"task_path": task_path, "episode_idx": ep_idx, "type": "indexed"},
                        ep_idx=ep_idx
                    )
                    
                    episode_result["schema"] = schema
                    episode_result["validation_status"] = "success"
                    
                except Exception as e:
                    episode_result["validation_status"] = "failed"
                    episode_result["errors"].append(str(e))
                    self.logger.warning(f"⚠️  Episode {ep_idx} validation failed: {e}")
                
                result["sampled_episodes"].append(episode_result)
            
            # 5. 汇总验证状态
            success_count = sum(1 for ep in result["sampled_episodes"] if ep["validation_status"] == "success")
            failed_count = sum(1 for ep in result["sampled_episodes"] if ep["validation_status"] == "failed")
            
            if success_count == len(result["sampled_episodes"]):
                result["validation_status"] = "success"
            elif success_count > 0:
                result["validation_status"] = "partial"
            else:
                result["validation_status"] = "failed"
            
            self.logger.info(f"✅ 任务验证完成: {task_name} - {result['validation_status']}")
            
        except Exception as e:
            result["validation_status"] = "failed"
            result["errors"].append(f"Task validation error: {e}")
            self.logger.error(f"❌ 任务验证失败: {e}", exc_info=True)
        
        return result
    
    def run(self) -> Path:
        """运行完整的验证流程
        
        Returns:
            报告文件路径
        """
        self.logger.info("🚀 启动数据库集成配置验证器...")
        
        # 1. 从数据库获取任务列表
        db_tasks = self.fetch_tasks_from_db()
        
        if not db_tasks:
            self.logger.warning("⚠️  数据库中没有任务")
            return None
        
        # 2. 过滤本地可用任务
        available_tasks = self.filter_local_available_tasks(db_tasks)
        
        if not available_tasks:
            self.logger.warning("⚠️  没有本地可用的任务")
            return None
        
        # 3. 验证每个任务
        validation_results = []
        
        for i, task in enumerate(available_tasks, 1):
            self.logger.info(f"\n{'='*70}")
            self.logger.info(f"处理任务 {i}/{len(available_tasks)}")
            
            result = self.validate_task(task)
            validation_results.append(result)
        
        # 4. 生成报告
        self.logger.info(f"\n{'='*70}")
        report_path = self.generate_report(validation_results, db_tasks, available_tasks)
        
        self.logger.info("\n✅ 数据库集成配置验证完成！")
        return report_path
    
    def generate_report(
        self,
        validation_results: List[Dict[str, Any]],
        db_tasks: List[Dict[str, Any]],
        available_tasks: List[Dict[str, Any]]
    ) -> Path:
        """生成详细的JSON报告"""
        # 统计路径来源
        nas_count = sum(1 for t in available_tasks if t.get("path_source") == "NAS")
        local_count = sum(1 for t in available_tasks if t.get("path_source") == "local")
        
        report_data = {
            "metadata": {
                "validation_date": datetime.now().isoformat(),
                "database_path": str(self.db_path),
                "data_root": str(self.data_root),
                "factory_config": str(self.factory_config_path),
                "total_db_tasks": len(db_tasks),
                "local_available_tasks": len(available_tasks),
                "validated_tasks": len(validation_results),
                "samples_per_task": self.num_samples_per_task,
                "path_sources": {
                    "nas_paths": nas_count,
                    "local_paths": local_count,
                },
            },
            "summary": {
                "total_tasks": len(validation_results),
                "successful_tasks": sum(1 for r in validation_results if r["validation_status"] == "success"),
                "partial_tasks": sum(1 for r in validation_results if r["validation_status"] == "partial"),
                "failed_tasks": sum(1 for r in validation_results if r["validation_status"] == "failed"),
                "skipped_tasks": sum(1 for r in validation_results if r["validation_status"] == "skipped"),
            },
            "validation_results": validation_results,
        }
        
        # 保存报告
        report_filename = f"db_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = self.output_dir / report_filename
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"✅ 验证报告已保存: {report_path}")
        self.logger.info(f"   - 数据库任务总数: {report_data['metadata']['total_db_tasks']}")
        self.logger.info(f"   - 本地可用任务: {report_data['metadata']['local_available_tasks']}")
        self.logger.info(f"     • NAS路径: {report_data['metadata']['path_sources']['nas_paths']}")
        self.logger.info(f"     • 本地路径: {report_data['metadata']['path_sources']['local_paths']}")
        self.logger.info(f"   - 验证成功: {report_data['summary']['successful_tasks']}")
        self.logger.info(f"   - 部分成功: {report_data['summary']['partial_tasks']}")
        self.logger.info(f"   - 失败: {report_data['summary']['failed_tasks']}")
        self.logger.info(f"   - 跳过: {report_data['summary']['skipped_tasks']}")
        
        return report_path


def main():
    parser = argparse.ArgumentParser(description="数据库集成配置验证器（修正版）")
    parser.add_argument(
        "--db-path",
        type=Path,
        required=True,
        help="数据库文件路径"
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data"),
        help="本地数据根目录 (默认: data/)"
    )
    parser.add_argument(
        "--factory-config",
        type=Path,
        default=Path("scripts/format_converters/tolerobot/configs/converter_factory_config.yaml"),
        help="Factory配置文件路径 (默认: scripts/format_converters/tolerobot/configs/converter_factory_config.yaml)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/db_validation_fixed"),
        help="输出目录 (默认: outputs/db_validation_fixed)"
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
        name="db_validator_fixed",
        log_dir=args.output_dir / "logs",
        level=getattr(logging, args.log_level)
    )
    
    # 运行验证
    validator = DBValidatorFixed(
        db_path=args.db_path,
        data_root=args.data_root,
        factory_config_path=args.factory_config,
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

