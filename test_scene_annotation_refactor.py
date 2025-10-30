#!/usr/bin/env python3
"""
测试重构后的场景标注功能
"""
import sys
from pathlib import Path

# 添加项目src目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

def test_imports():
    """测试导入"""
    print("测试导入...")
    
    try:
        from robocoin_dataset.database.database import DatasetDatabase
        print("✓ DatasetDatabase 导入成功")
        
        from robocoin_dataset.database.models import DatasetDB, TaskStatus
        print("✓ DatasetDB, TaskStatus 导入成功")
        
        from robocoin_dataset.annotation.scene_annotation.scene_annotation_local import SceneAnnotation
        print("✓ SceneAnnotation 导入成功")
        
        from robocoin_dataset.annotation.scene_annotation.scene_annotation_server import SceneAnnotationServer
        print("✓ SceneAnnotationServer 导入成功")
        
        print("🎉 所有导入测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_scene_annotation_creation():
    """测试场景标注类创建"""
    print("\n测试场景标注类创建...")
    
    try:
        from robocoin_dataset.annotation.scene_annotation.scene_annotation_local import SceneAnnotation
        
        # 创建临时数据库路径
        db_path = "/tmp/test_scene_annotation.db"
        output_dir = "/tmp/scene_annotation_test_output"
        
        scene_annotation = SceneAnnotation(
            db_file_path=db_path,
            output_dir=output_dir
        )
        
        print(f"✓ SceneAnnotation 创建成功")
        print(f"  数据库路径: {scene_annotation.db_file_path}")
        print(f"  输出目录: {scene_annotation.output_dir}")
        print(f"  版本UUID: {scene_annotation.version_uuid}")
        
        return True
        
    except Exception as e:
        print(f"❌ SceneAnnotation 创建失败: {e}")
        return False

def test_config_loader():
    """测试配置加载器"""
    print("\n测试配置加载器...")
    
    try:
        sys.path.insert(0, str(Path(__file__).parent / "scripts" / "annotation" / "scene_annotation"))
        from config_loader import ConfigLoader
        
        config = ConfigLoader()
        
        print(f"✓ ConfigLoader 创建成功")
        print(f"  数据库路径: {config.get_database_path()}")
        print(f"  输出目录: {config.get_output_directory()}")
        print(f"  服务器配置: {config.get_server_config()}")
        
        return True
        
    except Exception as e:
        print(f"❌ ConfigLoader 测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🧪 开始测试重构后的场景标注功能")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_scene_annotation_creation,
        test_config_loader,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"测试结果: 通过 {passed}, 失败 {failed}")
    
    if failed == 0:
        print("🎉 所有测试通过！重构成功！")
        return True
    else:
        print("❌ 部分测试失败，需要检查")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)