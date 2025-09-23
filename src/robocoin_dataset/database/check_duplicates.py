#check_duplicates.py
import uuid
import yaml
from pathlib import Path
from typing import Dict, Any, Set

# 全局缓存已使用的 UUID，防止重复
_used_uuids = set()


def load_registry(registry_file: Path | str) -> Dict[str, str]:
    """
    从 YAML 文件加载 UUID 注册表

    Args:
        registry_file: 注册表文件路径

    Returns:
        {key: uuid} 字典
    """
    registry_file = Path(registry_file)
    if registry_file.exists():
        try:
            with registry_file.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                # 转换所有值为字符串
                return {k: str(v).strip() for k, v in data.items()}
        except Exception as e:
            print(f"读取注册表失败 {registry_file}: {e}，使用空注册表")
    return {}


def save_registry(registry: Dict[str, str], registry_file: Path | str) -> None:
    """
    保存注册表到 YAML 文件

    Args:
        registry: 要保存的注册表字典
        registry_file: 文件路径
    """
    registry_file = Path(registry_file)
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with registry_file.open("w", encoding="utf-8") as f:
            yaml.dump(registry, f, allow_unicode=True, default_flow_style=False, indent=2)
        print(f"注册表已保存: {registry_file}")
    except Exception as e:
        print(f"❌ 无法保存注册表 {registry_file}: {e}")
        raise


def get_or_create_uuid(
    task: str,
    device: str,
    yaml_path: str,
    registry_file: str | Path,
    used_uuids: Set[str] = None
) -> str:
    """
    根据任务、设备、YAML 路径生成唯一的 dataset_uuid

    使用规则：
    key = f"{task}__{device}__{yaml_path_rel}"

    Args:
        task: 任务描述
        device: 设备型号
        yaml_path: YAML 文件绝对路径
        registry_file: 注册表文件路径
        used_uuids: 已使用的 UUID 集合（线程安全去重）

    Returns:
        UUID 字符串
    """
    global _used_uuids
    if used_uuids is None:
        used_uuids = _used_uuids

    # 构造唯一键
    yaml_path = Path(yaml_path).resolve()
    # 假设项目根目录是 /mnt/nas/... 的某个子目录，我们取相对路径关键部分
    try:
        # 尝试提取有意义的部分，比如从 "7agilex_cobot_magic_aloha/task_pick/config.yaml"
        rel_part = yaml_path.relative_to(yaml_path.parent.parent.parent.parent)
        key = f"{task}__{device}__{rel_part}"
    except Exception:
        # 备用方案：用最后两级目录 + 文件名
        parts = yaml_path.parts
        suffix = "/".join(parts[-3:]) if len(parts) >= 3 else str(yaml_path)
        key = f"{task}__{device}__{suffix}"

    # 规范化 key
    key = key.replace(" ", "_").replace("/", "__").replace("\\", "__")

    # 加载注册表
    registry = load_registry(registry_file)

    if key in registry:
        uid = registry[key]
        if uid not in used_uuids:
            used_uuids.add(uid)
            return uid

    # 生成新 UUID
    while True:
        new_uuid = str(uuid.uuid4())
        if new_uuid not in used_uuids and new_uuid not in registry.values():
            break

    # 写入注册表
    registry[key] = new_uuid
    save_registry(registry, registry_file)
    used_uuids.add(new_uuid)

    print(f"🆕 为 '{key}' 生成新 UUID: {new_uuid}")
    return new_uuid

def clear_used_uuids_cache() -> None:
    """清除内部缓存（测试用）"""
    global _used_uuids
    _used_uuids.clear()