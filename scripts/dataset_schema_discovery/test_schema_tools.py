"""
Schema Discovery工具测试脚本

验证所有模块是否能正常导入和基本功能是否正常。
"""

import sys
from pathlib import Path
import logging

# 添加项目路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / 'src'))

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_imports():
    """测试所有模块导入"""
    logger.info("=" * 70)
    logger.info("测试模块导入")
    logger.info("=" * 70)
    
    try:
        from h5_schema_discoverer import H5SchemaDiscoverer
        logger.info("✓ H5SchemaDiscoverer 导入成功")
    except ImportError as e:
        logger.error(f"✗ H5SchemaDiscoverer 导入失败: {e}")
        return False
    
    try:
        from json_schema_discoverer import JSONSchemaDiscoverer
        logger.info("✓ JSONSchemaDiscoverer 导入成功")
    except ImportError as e:
        logger.error(f"✗ JSONSchemaDiscoverer 导入失败: {e}")
        return False
    
    try:
        from mcap_schema_discoverer import MCAPSchemaDiscoverer
        logger.info("✓ MCAPSchemaDiscoverer 导入成功")
    except ImportError as e:
        logger.error(f"✗ MCAPSchemaDiscoverer 导入失败: {e}")
        return False
    
    try:
        from mmk2_schema_discoverer import MMK2SchemaDiscoverer
        logger.info("✓ MMK2SchemaDiscoverer 导入成功")
    except ImportError as e:
        logger.error(f"✗ MMK2SchemaDiscoverer 导入失败: {e}")
        return False
    
    try:
        from video_metadata_extractor import VideoMetadataExtractor
        logger.info("✓ VideoMetadataExtractor 导入成功")
    except ImportError as e:
        logger.error(f"✗ VideoMetadataExtractor 导入失败: {e}")
        return False
    
    try:
        from dataset_schema_discoverer import DatasetSchemaDiscoverer
        logger.info("✓ DatasetSchemaDiscoverer 导入成功")
    except ImportError as e:
        logger.error(f"✗ DatasetSchemaDiscoverer 导入失败: {e}")
        return False
    
    try:
        from database_query_tool import DatabaseQueryTool
        logger.info("✓ DatabaseQueryTool 导入成功")
    except ImportError as e:
        logger.error(f"✗ DatabaseQueryTool 导入失败: {e}")
        return False
    
    try:
        from schema_config_comparator import SchemaConfigComparator
        logger.info("✓ SchemaConfigComparator 导入成功")
    except ImportError as e:
        logger.error(f"✗ SchemaConfigComparator 导入失败: {e}")
        return False
    
    logger.info("=" * 70)
    logger.info("✅ 所有模块导入成功")
    logger.info("=" * 70)
    return True


def test_dependencies():
    """测试依赖项"""
    logger.info("\n" + "=" * 70)
    logger.info("测试依赖项")
    logger.info("=" * 70)
    
    dependencies = {
        'h5py': 'H5文件支持',
        'yaml': 'YAML配置文件支持',
        'sqlalchemy': '数据库支持',
        'mcap': 'MCAP文件支持（可选）',
        'bson': 'BSON文件支持（可选）',
        'cv2': 'OpenCV视频支持（可选）'
    }
    
    missing = []
    optional_missing = []
    
    for module_name, description in dependencies.items():
        try:
            if module_name == 'yaml':
                import yaml
            elif module_name == 'h5py':
                import h5py
            elif module_name == 'sqlalchemy':
                import sqlalchemy
            elif module_name == 'mcap':
                try:
                    from mcap.reader import make_reader
                except ImportError:
                    raise ImportError("mcap library not found")
            elif module_name == 'bson':
                import bson
            elif module_name == 'cv2':
                import cv2
            
            logger.info(f"✓ {module_name:15} - {description}")
        
        except ImportError:
            if '可选' in description:
                optional_missing.append(module_name)
                logger.warning(f"⚠  {module_name:15} - {description} (未安装)")
            else:
                missing.append(module_name)
                logger.error(f"✗ {module_name:15} - {description} (缺失)")
    
    logger.info("=" * 70)
    
    if missing:
        logger.error(f"❌ 缺少必需依赖: {', '.join(missing)}")
        logger.error("请运行: pip install " + " ".join(missing))
        return False
    
    if optional_missing:
        logger.warning(f"⚠️  缺少可选依赖: {', '.join(optional_missing)}")
        logger.warning("某些功能可能不可用")
    
    logger.info("✅ 所有必需依赖已安装")
    logger.info("=" * 70)
    return True


def test_basic_functionality():
    """测试基本功能"""
    logger.info("\n" + "=" * 70)
    logger.info("测试基本功能")
    logger.info("=" * 70)
    
    # 测试JSON schema discoverer（最简单）
    try:
        from json_schema_discoverer import JSONSchemaDiscoverer
        
        # 创建临时测试JSON
        import tempfile
        import json
        
        test_data = {
            'observations': {
                'qpos': [0.1, 0.2, 0.3],
                'qvel': [0.01, 0.02, 0.03]
            },
            'action': [0.5, 0.6, 0.7]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            test_file = Path(f.name)
        
        discoverer = JSONSchemaDiscoverer(logger)
        schema = discoverer.discover_file(test_file)
        
        # 验证schema
        assert 'structure' in schema
        assert schema['structure']['type'] == 'object'
        assert 'observations' in schema['structure']['fields']
        
        test_file.unlink()  # 删除临时文件
        
        logger.info("✓ JSON Schema Discoverer 基本功能正常")
    
    except Exception as e:
        logger.error(f"✗ JSON Schema Discoverer 测试失败: {e}")
        return False
    
    logger.info("=" * 70)
    logger.info("✅ 基本功能测试通过")
    logger.info("=" * 70)
    return True


def main():
    """主测试函数"""
    logger.info("\n" + "🔍 Schema Discovery 工具测试")
    logger.info("=" * 70 + "\n")
    
    all_passed = True
    
    # 测试1: 模块导入
    if not test_imports():
        all_passed = False
        logger.error("\n❌ 模块导入测试失败")
        return False
    
    # 测试2: 依赖项
    if not test_dependencies():
        all_passed = False
        logger.warning("\n⚠️  依赖项测试有警告，但可以继续")
    
    # 测试3: 基本功能
    if not test_basic_functionality():
        all_passed = False
        logger.error("\n❌ 基本功能测试失败")
        return False
    
    # 总结
    logger.info("\n" + "=" * 70)
    if all_passed:
        logger.info("✅ 所有测试通过！工具已准备就绪。")
        logger.info("\n下一步:")
        logger.info("  1. 运行单个数据集测试:")
        logger.info("     python dataset_schema_discoverer.py /path/to/dataset")
        logger.info("  2. 运行批量discovery:")
        logger.info("     ./run_batch_discovery.sh")
    else:
        logger.error("❌ 部分测试失败，请修复问题后重试")
    logger.info("=" * 70)
    
    return all_passed


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

