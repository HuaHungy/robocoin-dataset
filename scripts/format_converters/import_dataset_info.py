#!/usr/bin/env python3
# scripts/db/import_dataset_info_from_yaml.py
import argparse
import shutil
import sys
import os
import re
from pathlib import Path
from typing import List, Dict, Any
import concurrent.futures
import yaml
import logging
import traceback  
import subprocess
# 把项目根目录塞进 sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.services.dataset_info import upsert_dataset_info
from robocoin_dataset.database.check_duplicates import get_or_create_uuid, load_registry, save_registry

# 全局变量（用于本次运行去重）
used_uuids_global = set()

# 支持的 YAML 文件名
SUPPORTED_YAML_NAMES = {"local_dataset_info.yaml", "local_dataset_info.yml"}

# ------------------------------------------------------------------
# 配置日志
# ------------------------------------------------------------------
def setup_logging(log_dir: Path, dry_run: bool = False) -> None:
    """设置日志输出到文件和控制台"""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "import_dataset_info.log"

    # 清空旧日志（避免追加）
    if log_file.exists() and not dry_run:
        log_file.unlink()

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 防止重复添加 handler
    if logger.hasHandlers():
        logger.handlers.clear()

    # 控制台 Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    logger.addHandler(ch)

    # 文件 Handler
    if not dry_run:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(fh)

    logging.info(f"日志已启动，日志文件：{log_file}")

# ------------------------------------------------------------------
# 使用 os.walk 查找 YAML 文件（跳过子目录）
# ------------------------------------------------------------------
def find_local_yaml_files(root: Path) -> List[Path]:
    found = []
    for current, dirnames, files in os.walk(root):
        if SUPPORTED_YAML_NAMES & set(files):
            filename = next(iter(SUPPORTED_YAML_NAMES & set(files)))
            found.append(Path(current) / filename)
            dirnames.clear()  # 不进入子目录
    return found

# ------------------------------------------------------------------
# 数据清理函数
# ------------------------------------------------------------------
def clean_data_value(value: Any) -> Any:
    """清理数据值，确保数据库兼容"""
    if isinstance(value, list):
        if value:
            return str(value[0]) if len(value) == 1 else str(value)
        else:
            return None
    elif isinstance(value, dict):
        return str(value)
    return value

# ------------------------------------------------------------------
# 读取 + 检查 dataset_uuid
# ------------------------------------------------------------------
def load_and_patch(yaml_path: Path, dry_run: bool = False) -> Dict[str, Any]:
    try:
        with yaml_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logging.warning(f"解析失败 {yaml_path}: {e}")
        return {}

    if "dataset_name" not in data:
        logging.warning(f"跳过无效文件（缺少 dataset_name）：{yaml_path}")
        return {}

    # ====== 1. 尝试从主文件获取 UUID ======
    existing_uuid = data.get("dataset_uuid")

    # ====== 2. 如果主文件没有，尝试读取同目录下的 dataset_uuid.yaml ======
    if not existing_uuid:
        uuid_yaml = yaml_path.parent / "dataset_uuid.yaml"
        try:
            if uuid_yaml.exists():
                with uuid_yaml.open(encoding="utf-8") as f:
                    uuid_data = yaml.safe_load(f)
                    external_uuid = uuid_data.get("uuid") or uuid_data.get("dataset_uuid")
                    if external_uuid:
                        logging.info(f"从 {uuid_yaml.name} 获取 UUID: {external_uuid}")
                        existing_uuid = external_uuid
        except Exception as e:
            logging.warning(f"读取 {uuid_yaml} 失败: {e}")

    # ====== 3. 如果还是没有 UUID，才走生成逻辑 ======
    if existing_uuid:
        data["dataset_uuid"] = existing_uuid
        used_uuids_global.add(existing_uuid)
        logging.info(f"[{data['dataset_name']}] 使用已有 UUID: {existing_uuid}")
    else:
        task_desc = data.get("task_description") or data.get("task_desc") or "unknown_task"
        device_model = data.get("device_model") or "unknown_device"

        try:
            registry_file = PROJECT_ROOT / "dataset_registry.yaml"
            new_uuid = get_or_create_uuid(
                task=task_desc,
                device=device_model,
                yaml_path=str(yaml_path),
                registry_file=str(registry_file),
                used_uuids=used_uuids_global
            )
            data["dataset_uuid"] = new_uuid
            used_uuids_global.add(new_uuid)

            if not dry_run:
                with yaml_path.open("w", encoding="utf-8") as f:
                    yaml.dump(data, f, allow_unicode=True, default_flow_style=False, indent=2, sort_keys=False)
                logging.info(f"已写入新 UUID: {yaml_path} → {new_uuid}")
            else:
                logging.info(f"[dry-run] 将生成 UUID: {yaml_path} → {new_uuid}")

        except Exception as e:
            logging.error(f"自动生成 UUID 失败 {yaml_path}: {e}")
            return {}

    # 清理字段...
    for key in ['device_model', 'end_effector_type', 'operation_platform_height']:
        if key in data:
            data[key] = clean_data_value(data[key])

    logging.info(f"[{data['dataset_name']}] -> {data['dataset_uuid']}")
    data['yaml_file_path'] = str(yaml_path)
    return data

# ---------------- 新增：提取 yaml 文件 ----------------
def collect_yaml_files(root_dirs: List[Path], output_dir: Path, dry_run: bool = False) -> None:
    """收集所有 local_dataset_info.yml/.yaml 到 output_dir，并记录日志"""
    log_dir = output_dir / "logs"
    setup_logging(log_dir, dry_run=dry_run)

    if not dry_run:
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=False)
    else:
        if output_dir.exists():
            logging.info(f"[dry-run] 输出目录: {output_dir} (将被清空)")
        else:
            logging.info(f"[dry-run] 输出目录: {output_dir} (将被创建)")

    hub = {}
    idx = 0
    for r in root_dirs:
        for dirpath, dirnames, files in os.walk(r):
            if SUPPORTED_YAML_NAMES & set(files):
                filename = next(iter(SUPPORTED_YAML_NAMES & set(files)))
                src = Path(dirpath) / filename
                dst = output_dir / f"local_dataset_info_{idx}.yml"
                if not dry_run:
                    shutil.copy2(src, dst)
                hub[str(dst.resolve())] = str(src.resolve())
                logging.info(f"已复制: {src} → {dst}")
                idx += 1
                dirnames.clear()

    if not dry_run:
        hub_file = output_dir / "local_dataset_info_hub.yml"
        hub_file.write_text(
            yaml.dump(hub, sort_keys=True, allow_unicode=True, indent=2),
            encoding="utf-8"
        )
        logging.info(f"已生成 hub 文件: {hub_file}")

    logging.info(f"已收集 {idx} 个文件到 {output_dir}")

# ------------------------------------------------------------------
# 批量处理函数
# ------------------------------------------------------------------
def process_files_batch(yaml_files: List[Path], max_workers: int = 8, dry_run: bool = False) -> tuple[List[Dict[str, Any]], int]:
    datasets = []
    invalid_count = 0
    seen_dataset_device_combos = set()  

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(load_and_patch, yml, dry_run): yml 
            for yml in yaml_files
        }

        for future in concurrent.futures.as_completed(future_to_file):
            yml = future_to_file[future]
            try:
                data = future.result()
                if not data:
                    invalid_count += 1
                    continue

                dataset_name = data.get("dataset_name")
                device_model = data.get("device_model", "unknown_device")  
                
                # 检查 dataset_name 和 device_model 组合是否重复
                combo_key = (dataset_name, device_model)
                if combo_key in seen_dataset_device_combos:
                    logging.warning(f"跳过重复的数据集组合: {dataset_name} (device_model: {device_model}) - 文件: {yml}")
                    invalid_count += 1
                    continue
                
                # 添加到已见集合
                seen_dataset_device_combos.add(combo_key)
                datasets.append(data)
                
            except Exception as e:
                logging.error(f"处理文件失败 {yml}: {e}")
                invalid_count += 1

    return datasets, invalid_count

# ------------------------------------------------------------------
# 主入口
# ------------------------------------------------------------------
def main() -> None:
    """
    主函数，负责解析命令行参数，设置日志，扫描 YAML 文件，处理这些文件，并将数据导入数据库。
    """
    global used_uuids_global
    used_uuids_global = set()

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="递归查找 local_dataset_info.yaml/.yml，检查 dataset_uuid 并批量入库"
    )
    parser.add_argument(
        "scan_root",
        type=str,
        help="要扫描的根目录，支持多个路径（用空格、逗号、分号分隔）",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="./db/datasets.db",
        help="数据库文件路径，默认 ./db/datasets.db",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="并行工作线程数，默认8",
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="仅收集 yaml 文件，不做数据库导入"
    )
    parser.add_argument(
        "--collect-output",
        type=Path,
        default=Path("./collected_yamls"),
        help="收集模式下的输出目录（日志也存放于此）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只扫描和模拟，不写入文件或数据库"
    )
    args = parser.parse_args()

    # 解析多个路径
    root_paths = re.split(r"[\s;,:\n]+", args.scan_root.strip())
    root_paths = [Path(p.strip()) for p in root_paths if p.strip()]

    # 设置日志
    log_dir = args.collect_output / "logs"
    setup_logging(log_dir, dry_run=args.dry_run)

    if args.collect_only:
        logging.info(f"收集模式：从 {len(root_paths)} 个根目录收集 YAML 文件")
        collect_yaml_files(root_paths, args.collect_output, dry_run=args.dry_run)
        return

    # 扫描所有路径
    all_yaml_files = []
    for root in root_paths:
        if not root.exists():
            logging.error(f"路径不存在：{root}")
            continue
        logging.info(f"扫描目录: {root}")
        yaml_files = find_local_yaml_files(root)
        all_yaml_files.extend(yaml_files)

    if not all_yaml_files:
        logging.warning("未找到任何 local_dataset_info.yaml/.yml，退出。")
        sys.exit(0)

    logging.info(f"找到 {len(all_yaml_files)} 个 YAML 文件")

    # 并行处理
    datasets, invalid_count = process_files_batch(all_yaml_files, args.workers, dry_run=args.dry_run)

    if invalid_count > 0:
        logging.warning(f"跳过 {invalid_count} 个无效文件")

    if not datasets:
        logging.warning("没有有效数据集，退出。")
        sys.exit(0)

    logging.info(f"准备处理 {len(datasets)} 个数据集")

    if args.dry_run:
        logging.info("[dry-run] 模拟结束，未写入数据库或文件。")
        return

    # 1. 创建数据库路径
    db_path = Path(args.db_path).expanduser().absolute()
    db_path.parent.mkdir(parents=True, exist_ok=True)  # 确保目录存在

    # 2. 创建数据库实例
    db = DatasetDatabase(db_path)
    logging.info(f"数据库连接已创建: {db_path}")

    # 3. 写入数据库
    try:
        with db.with_session() as session:
            for record in datasets:
                upsert_dataset_info(yaml_data=record, db_path=args.db_path)
            session.commit()
        success_count = len(datasets)
        logging.info(f"成功导入 {success_count} 个数据集到数据库")

        # 执行 separate.py
        logging.info("正在执行 separate.py 脚本...")
        separate_script = PROJECT_ROOT / "scripts" / "db" / "separate.py"
        if not separate_script.exists():
            logging.critical(f"无法找到 separate.py: {separate_script}")
            sys.exit(1)

        cmd = [
            sys.executable,
            str(separate_script),
            *[str(p) for p in root_paths],
            "--log-dir", str(log_dir / "separate_logs")
        ]
        if args.dry_run:
            cmd.append("--dry-run")

        try:
            logging.info(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                check=True,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            logging.info("separate.py 脚本执行成功。")
            if result.stdout.strip():
                for line in result.stdout.strip().splitlines():
                    if "DRY RUN" in line or "处理完成" in line or "统计" in line:
                        logging.info(f"[separate] {line}")
        except subprocess.CalledProcessError as e:
            logging.critical(f"separate.py 脚本执行失败: {e}")
            if e.stdout:
                logging.critical(f"标准输出:\n{e.stdout}")
            if e.stderr:
                logging.critical(f"错误输出:\n{e.stderr}")
            sys.exit(1)

    except Exception as e:
        logging.critical(f"批量导入失败: {e}")
        logging.critical(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
    
    

"""
# 收集模式
python scripts/db/import_dataset_info.py \
    /mnt/nas/4unitree_g1/basket_storage_apple \
    --collect-only \
    --collect-output ./collected_yamls \
    --dry-run

# 导入模式
python scripts/db/import_dataset_info.py \
    --db-path /home/adminpc1/robocoin-dataset/db/datasets.db \
    --workers 4 \
    /mnt/nas/synnas/docker2/外部数据/智平方
"""
