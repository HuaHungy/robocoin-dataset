#!/usr/bin/env python3
"""
测试新的容错机制

这个脚本用于验证重构后的转换器框架的智能容错功能。

使用方法:
    python test_fault_tolerance.py --dataset-path /path/to/dataset --device-model zhipingfang

测试内容:
    1. 前N个episode严格模式
    2. 失败率阈值检测
    3. 帧级容错
    4. Episode级容错
    5. 详细的转换报告
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# 添加项目根目录和src目录到Python路径
project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))


def setup_test_logger(log_dir: Path = None) -> logging.Logger:
    """创建测试日志记录器"""
    if log_dir is None:
        log_dir = project_root / "test_logs"
    log_dir.mkdir(exist_ok=True)
    
    logger = logging.getLogger("fault_tolerance_test")
    logger.setLevel(logging.DEBUG)
    
    # 控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # 文件输出
    from datetime import datetime
    log_file = log_dir / f"fault_tolerance_test_{datetime.now():%Y%m%d_%H%M%S}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    logger.info(f"日志文件: {log_file}")
    
    return logger


def load_converter_config(device_model: str) -> tuple[dict, str, str]:
    """加载转换器配置
    
    Returns:
        (converter_config, module_path, class_name)
    """
    import yaml
    
    # 加载factory配置
    factory_config_path = (
        project_root / 
        "scripts/format_converters/tolerobot/configs/converter_factory_config.yaml"
    )
    
    with open(factory_config_path, 'r', encoding='utf-8') as f:
        factory_config = yaml.safe_load(f)
    
    # 获取device_model对应的配置
    if device_model not in factory_config:
        raise ValueError(
            f"Device model '{device_model}' not found in factory config.\n"
            f"Available models: {list(factory_config.keys())}"
        )
    
    model_config = factory_config[device_model]
    
    # 加载具体的converter配置
    converter_config_path = (
        project_root / 
        "scripts/format_converters/tolerobot/configs" /
        model_config['converter_config']
    )
    
    with open(converter_config_path, 'r', encoding='utf-8') as f:
        converter_config = yaml.safe_load(f)
    
    module_path = model_config['converter_module_path']
    class_name = model_config['converter_class_name']
    
    return converter_config, module_path, class_name


def run_conversion_test(
    dataset_path: Path,
    device_model: str,
    logger: logging.Logger,
    strict_episodes: int = 3,
    failure_threshold: float = 0.8,
    min_valid_frame_ratio: float = 0.5,
    test_mode: bool = True,
) -> dict:
    """运行转换测试
    
    Args:
        dataset_path: 数据集路径
        device_model: 设备型号
        logger: 日志记录器
        strict_episodes: 严格模式的episode数量
        failure_threshold: 失败率阈值
        min_valid_frame_ratio: 最小有效帧比例
        test_mode: 是否为测试模式（只转换第一个episode）
    
    Returns:
        转换报告字典
    """
    # 直接从模块导入
    from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import LerobotFormatConverterFactory
    
    logger.info("="*70)
    logger.info("开始容错机制测试")
    logger.info("="*70)
    logger.info(f"数据集路径: {dataset_path}")
    logger.info(f"设备型号: {device_model}")
    logger.info(f"严格模式episodes: {strict_episodes}")
    logger.info(f"失败率阈值: {failure_threshold:.1%}")
    logger.info(f"最小有效帧比例: {min_valid_frame_ratio:.1%}")
    logger.info(f"测试模式: {test_mode}")
    logger.info("="*70)
    
    # 加载配置
    try:
        converter_config, module_path, class_name = load_converter_config(device_model)
        logger.info(f"✓ 加载配置成功: {module_path}.{class_name}")
    except Exception as e:
        logger.error(f"✗ 加载配置失败: {e}")
        raise
    
    # 创建输出目录
    output_path = project_root / "test_output" / f"{device_model}_test"
    output_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"输出路径: {output_path}")
    
    # 创建转换器
    try:
        converter = LerobotFormatConverterFactory.create_converter(
            dataset_path=dataset_path,
            device_model=device_model,
            output_path=output_path,
            converter_config=converter_config,
            converter_module_path=module_path,
            converter_class_name=class_name,
            repo_id=f"test/{device_model}",
            logger=logger,
            strict_episodes=strict_episodes,
            failure_threshold=failure_threshold,
            min_valid_frame_ratio=min_valid_frame_ratio,
        )
        logger.info("✓ 创建转换器成功")
    except Exception as e:
        logger.error(f"✗ 创建转换器失败: {e}")
        raise
    
    # 执行转换
    logger.info("")
    logger.info("开始转换...")
    logger.info("")
    
    converted_episodes = []
    
    try:
        for task, task_ep_idx, global_ep_idx in converter.convert(is_test=test_mode):
            converted_episodes.append({
                'task': task,
                'task_episode': task_ep_idx,
                'global_episode': global_ep_idx,
            })
            logger.info(
                f"✓ Episode {global_ep_idx} 转换成功 "
                f"(task: {task}, task_ep: {task_ep_idx})"
            )
        
        logger.info("")
        logger.info("转换完成！")
        
    except Exception as e:
        logger.error(f"✗ 转换失败: {e}")
        logger.exception("详细错误信息:")
        raise
    
    # 获取转换报告
    report = converter._get_conversion_report()
    report['converted_episodes'] = converted_episodes
    
    return report


def print_test_results(report: dict, logger: logging.Logger):
    """打印测试结果"""
    logger.info("")
    logger.info("="*70)
    logger.info("测试结果")
    logger.info("="*70)
    logger.info(f"数据集: {report['dataset']}")
    logger.info(f"总Episodes尝试: {report['total_episodes_attempted']}")
    logger.info(f"成功转换: {report['successful_episodes']}")
    logger.info(f"跳过: {report['skipped_episodes']}")
    logger.info(f"成功率: {report['success_rate']:.1%}")
    logger.info(f"总帧数: {report['total_frames_converted']}")
    logger.info(f"跳过帧数: {report['total_frames_skipped']}")
    
    if report['skip_details']:
        logger.info("")
        logger.info("跳过详情 (最近50条):")
        for detail in report['skip_details'][-10:]:  # 只显示最近10条
            ep = detail['episode']
            if detail.get('skipped_entire_episode'):
                logger.info(
                    f"  Episode {ep}: 完全跳过 - {detail.get('reason', 'Unknown')}"
                )
            else:
                logger.info(
                    f"  Episode {ep}: 跳过 {detail.get('skipped_frames', 0)} 帧 "
                    f"(转换 {detail.get('converted_frames', 0)} 帧)"
                )
    
    logger.info("="*70)
    
    # 评估测试结果
    logger.info("")
    logger.info("容错机制评估:")
    
    if report['total_episodes_attempted'] == 0:
        logger.warning("⚠️  没有尝试转换任何episode")
    elif report['successful_episodes'] == 0:
        logger.error("✗ 所有episode都失败了 - 可能是配置错误")
    elif report['success_rate'] >= 0.95:
        logger.info("✓ 优秀: 成功率 >= 95%")
    elif report['success_rate'] >= 0.8:
        logger.info("✓ 良好: 成功率 >= 80%")
    elif report['success_rate'] >= 0.5:
        logger.warning("⚠️  一般: 成功率 >= 50%，建议检查数据质量")
    else:
        logger.warning("⚠️  较差: 成功率 < 50%，可能存在系统性问题")
    
    if report['total_frames_skipped'] > 0:
        skip_ratio = report['total_frames_skipped'] / (
            report['total_frames_converted'] + report['total_frames_skipped']
        )
        logger.info(f"帧跳过率: {skip_ratio:.2%}")
        
        if skip_ratio < 0.01:
            logger.info("✓ 优秀: 跳过帧 < 1%")
        elif skip_ratio < 0.05:
            logger.info("✓ 良好: 跳过帧 < 5%")
        else:
            logger.warning(f"⚠️  较高: 跳过帧 >= 5%")


def main():
    parser = argparse.ArgumentParser(
        description="测试LeRobot转换器的容错机制",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 测试智平方数据集（测试模式，只转换第一个episode）
    python test_fault_tolerance.py \\
        --dataset-path /mnt/nas/datasets/zhipingfang/task1 \\
        --device-model zhipingfang \\
        --test-mode
    
    # 测试银河数据集（完整转换）
    python test_fault_tolerance.py \\
        --dataset-path /mnt/nas/datasets/yinhe/task1 \\
        --device-model yinhe \\
        --strict-episodes 5 \\
        --failure-threshold 0.9 \\
        --no-test-mode
    
    # 自定义容错参数
    python test_fault_tolerance.py \\
        --dataset-path /path/to/dataset \\
        --device-model my_robot \\
        --strict-episodes 10 \\
        --failure-threshold 0.7 \\
        --min-valid-frame-ratio 0.4
        """
    )
    
    parser.add_argument(
        "--dataset-path",
        type=Path,
        required=True,
        help="数据集路径"
    )
    
    parser.add_argument(
        "--device-model",
        type=str,
        required=True,
        help="设备型号（如 zhipingfang, yinhe, realman等）"
    )
    
    parser.add_argument(
        "--strict-episodes",
        type=int,
        default=3,
        help="前N个episode使用严格模式（默认: 3）"
    )
    
    parser.add_argument(
        "--failure-threshold",
        type=float,
        default=0.8,
        help="失败率阈值，超过此值判定为配置错误（默认: 0.8）"
    )
    
    parser.add_argument(
        "--min-valid-frame-ratio",
        type=float,
        default=0.5,
        help="Episode最小有效帧比例（默认: 0.5）"
    )
    
    parser.add_argument(
        "--test-mode",
        action="store_true",
        default=True,
        help="测试模式：只转换第一个episode（默认: True）"
    )
    
    parser.add_argument(
        "--no-test-mode",
        action="store_false",
        dest="test_mode",
        help="完整转换模式：转换所有episodes"
    )
    
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="日志目录（默认: project_root/test_logs）"
    )
    
    parser.add_argument(
        "--save-report",
        type=Path,
        default=None,
        help="保存转换报告到JSON文件"
    )
    
    args = parser.parse_args()
    
    # 验证参数
    if not args.dataset_path.exists():
        print(f"错误: 数据集路径不存在: {args.dataset_path}")
        sys.exit(1)
    
    if args.strict_episodes < 1:
        print(f"错误: strict_episodes 必须 >= 1")
        sys.exit(1)
    
    if not (0 < args.failure_threshold <= 1):
        print(f"错误: failure_threshold 必须在 (0, 1] 范围内")
        sys.exit(1)
    
    if not (0 < args.min_valid_frame_ratio <= 1):
        print(f"错误: min_valid_frame_ratio 必须在 (0, 1] 范围内")
        sys.exit(1)
    
    # 设置日志
    logger = setup_test_logger(args.log_dir)
    
    try:
        # 运行测试
        report = run_conversion_test(
            dataset_path=args.dataset_path,
            device_model=args.device_model,
            logger=logger,
            strict_episodes=args.strict_episodes,
            failure_threshold=args.failure_threshold,
            min_valid_frame_ratio=args.min_valid_frame_ratio,
            test_mode=args.test_mode,
        )
        
        # 打印结果
        print_test_results(report, logger)
        
        # 保存报告
        if args.save_report:
            args.save_report.parent.mkdir(parents=True, exist_ok=True)
            with open(args.save_report, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            logger.info(f"✓ 报告已保存到: {args.save_report}")
        
        logger.info("")
        logger.info("✓ 测试完成")
        
        # 根据结果返回退出码
        if report['success_rate'] >= 0.8:
            sys.exit(0)
        elif report['success_rate'] >= 0.5:
            sys.exit(1)  # 警告
        else:
            sys.exit(2)  # 错误
        
    except Exception as e:
        logger.error(f"✗ 测试失败: {e}")
        logger.exception("详细错误:")
        sys.exit(3)


if __name__ == "__main__":
    main()

