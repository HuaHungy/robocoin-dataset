"""Converter类动态加载器

该模块提供动态加载converter类的功能，用于配置检测器调用实际的converter进行数据加载。
"""

import importlib
import logging
import sys
import yaml
from pathlib import Path
from typing import Type, Any

# 确保src目录在路径中（robocoin_dataset包所在位置）
_project_root = Path(__file__).parent.parent.parent
_src_dir = _project_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


def load_converter_class(module_path: str, class_name: str) -> Type:
    """
    动态加载converter类
    
    Args:
        module_path: converter模块路径，如 "robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5"
        class_name: converter类名，如 "LerobotFormatConverterHdf5"
    
    Returns:
        Converter类（未实例化）
    
    Raises:
        ImportError: 如果模块不存在
        AttributeError: 如果类不存在
    
    示例:
        >>> ConverterClass = load_converter_class(
        ...     "robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5",
        ...     "LerobotFormatConverterHdf5"
        ... )
        >>> converter = ConverterClass(
        ...     dataset_path="/path/to/dataset",
        ...     output_path="/path/to/output",
        ...     repo_id="test/test"
        ... )
    """
    logger = logging.getLogger(__name__)
    
    try:
        # 动态导入模块
        module = importlib.import_module(module_path)
        logger.debug(f"成功导入模块: {module_path}")
    except ImportError as e:
        logger.error(f"导入模块失败: {module_path}")
        logger.error(f"错误: {e}")
        raise ImportError(f"无法导入converter模块 '{module_path}': {e}")
    
    try:
        # 获取类
        converter_class = getattr(module, class_name)
        logger.debug(f"成功获取类: {class_name}")
        return converter_class
    except AttributeError as e:
        logger.error(f"在模块 {module_path} 中未找到类 {class_name}")
        logger.error(f"错误: {e}")
        raise AttributeError(f"模块 '{module_path}' 中不存在类 '{class_name}': {e}")


def create_converter_instance(
    module_path: str,
    class_name: str,
    dataset_path: str,
    output_path: str,
    repo_id: str,
    converter_config_path: str = None,
    logger: logging.Logger = None,
    **kwargs
) -> Any:
    """
    创建converter实例（便捷方法）
    
    Args:
        module_path: converter模块路径
        class_name: converter类名
        dataset_path: 数据集路径
        output_path: 输出路径
        repo_id: 仓库ID
        converter_config_path: 配置文件路径（可选）
        logger: 日志记录器（可选）
        **kwargs: 其他传递给converter的参数
    
    Returns:
        Converter实例
    
    示例:
        >>> converter = create_converter_instance(
        ...     module_path="robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_h5",
        ...     class_name="LerobotFormatConverterHdf5",
        ...     dataset_path="/path/to/dataset",
        ...     output_path="/tmp/test",
        ...     repo_id="test/test",
        ...     converter_config_path="/path/to/config.yaml"
        ... )
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # 加载类
    ConverterClass = load_converter_class(module_path, class_name)
    
    # 加载配置文件（如果提供了路径）
    config_dict = None
    if converter_config_path:
        try:
            with open(converter_config_path, 'r', encoding='utf-8') as f:
                config_dict = yaml.safe_load(f)
            logger.debug(f"成功加载配置文件: {converter_config_path}")
        except Exception as e:
            logger.error(f"加载配置文件失败: {converter_config_path}")
            raise RuntimeError(f"无法加载配置文件 '{converter_config_path}': {e}")
    
    # 准备参数
    init_args = {
        'dataset_path': dataset_path,
        'output_path': output_path,
        'repo_id': repo_id,
        'logger': logger,  # 总是传递logger
    }
    
    if config_dict:
        # 注意：converter期望的是配置字典，不是路径字符串
        init_args['converter_config'] = config_dict
    
    # 合并额外参数
    init_args.update(kwargs)
    
    try:
        # 实例化
        converter = ConverterClass(**init_args)
        logger.debug(f"成功创建converter实例: {class_name}")
        return converter
    except Exception as e:
        logger.error(f"创建converter实例失败: {class_name}")
        logger.error(f"错误: {e}")
        raise RuntimeError(f"无法创建converter实例 '{class_name}': {e}")

