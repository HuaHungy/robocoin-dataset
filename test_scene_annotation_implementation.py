#!/usr/bin/env python3
"""
测试场景标注实现的脚本
"""

import sys
import logging
from pathlib import Path

# 添加项目路径到sys.path
project_root = Path(__file__).parent / "src"
sys.path.insert(0, str(project_root))

try:
    from robocoin_dataset.annotation.scene_annotation.dataset_scene_annotation_embedding import (
        DatasetSceneAnnotationEmbedding,
        SceneAnnotationDataPostProcessor,
        scene_annotations_to_frame_array,
    )
    from robocoin_dataset.data_post_process import DataPostProcessorBase
    from robocoin_dataset.database.models import DatasetDB, TaskStatus
    print("✅ 成功导入所有必要的模块")
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    sys.exit(1)

def test_scene_annotations_to_frame_array():
    """测试场景标注转换为帧数组的功能"""
    print("\n🧪 测试 scene_annotations_to_frame_array 函数...")
    
    # 模拟场景标注数据
    scene_annotations = [
        {
            'episode_idx': 0,
            'objects': [
                {'name': 'cup'},
                {'name': 'table'},
                {'name': 'robot_arm'}
            ],
            'scene_type': 'kitchen'
        },
        {
            'episode_idx': 1,
            'objects': [
                {'name': 'book'},
                {'name': 'shelf'}
            ],
            'scene_type': 'library'
        }
    ]
    
    episode_frame_nums = {0: 50, 1: 30}
    
    try:
        result = scene_annotations_to_frame_array(
            scene_annotations=scene_annotations,
            max_objects_num=5,
            episode_frame_nums=episode_frame_nums
        )
        
        print(f"✅ 成功转换场景标注，生成了 {len(result)} 个episode的数据")
        print(f"   Episode 0 形状: {result[0].shape}")
        print(f"   Episode 1 形状: {result[1].shape}")
        
        # 检查数据类型和形状
        for i, arr in enumerate(result):
            assert arr.dtype == 'int32', f"Episode {i} 数据类型错误"
            assert arr.shape[1] == 6, f"Episode {i} 列数错误 (应该是 max_objects_num + 1 = 6)"
            
        print("✅ 数据格式验证通过")
        
    except Exception as e:
        print(f"❌ scene_annotations_to_frame_array 测试失败: {e}")
        return False
    
    return True

def test_data_post_processor_inheritance():
    """测试SceneAnnotationDataPostProcessor是否正确继承DataPostProcessorBase"""
    print("\n🧪 测试 SceneAnnotationDataPostProcessor 继承关系...")
    
    try:
        # 检查继承关系
        assert issubclass(SceneAnnotationDataPostProcessor, DataPostProcessorBase)
        print("✅ SceneAnnotationDataPostProcessor 正确继承了 DataPostProcessorBase")
        
        # 检查必要方法是否存在
        required_methods = [
            'prepare_processing',
            'process_episode_data', 
            'get_modified_feature_names'
        ]
        
        for method_name in required_methods:
            assert hasattr(SceneAnnotationDataPostProcessor, method_name)
            print(f"✅ 方法 {method_name} 存在")
            
    except Exception as e:
        print(f"❌ 继承关系测试失败: {e}")
        return False
    
    return True

def test_database_models():
    """测试数据库模型是否正确导入"""
    print("\n🧪 测试数据库模型...")
    
    try:
        # 检查TaskStatus枚举
        assert hasattr(TaskStatus, 'PENDING')
        assert hasattr(TaskStatus, 'PROCESSING') 
        assert hasattr(TaskStatus, 'COMPLETED')
        assert hasattr(TaskStatus, 'FAILED')
        print("✅ TaskStatus 枚举正确")
        
        # 检查DatasetDB模型
        assert hasattr(DatasetDB, 'scene_annotation_status')
        assert hasattr(DatasetDB, 'scene_annotation_version')
        assert hasattr(DatasetDB, 'scene_annotation_err_msg')
        print("✅ DatasetDB 场景标注字段存在")
        
    except Exception as e:
        print(f"❌ 数据库模型测试失败: {e}")
        return False
    
    return True

def main():
    """主测试函数"""
    print("🚀 开始测试场景标注实现...")
    
    # 设置日志
    logging.basicConfig(level=logging.INFO)
    
    tests = [
        test_database_models,
        test_scene_annotations_to_frame_array,
        test_data_post_processor_inheritance,
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ 测试 {test_func.__name__} 出现异常: {e}")
    
    print(f"\n📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！场景标注实现正确。")
        return 0
    else:
        print("⚠️  部分测试失败，请检查实现。")
        return 1

if __name__ == "__main__":
    sys.exit(main())