#!/usr/bin/env python3
"""Yinhe数据集深度数值分析"""

import json
import numpy as np
from pathlib import Path

def analyze_yinhe_data(json_path: Path):
    """深度分析Yinhe JSON数据"""
    
    print(f"📊 Yinhe数值深度分析")
    print("=" * 80)
    print(f"📄 文件: {json_path}")
    print()
    
    # 加载JSON
    with open(json_path) as f:
        data = json.load(f)
    
    if 'data' not in data:
        print("❌ JSON中没有'data'字段")
        return
    
    json_data = data['data']
    
    print(f"📋 总共{len(json_data)}个数据字段")
    print()
    
    # 分析每个字段
    for key, value in sorted(json_data.items()):
        print(f"{'='*80}")
        print(f"🔍 {key}")
        print(f"{'-'*80}")
        
        if not isinstance(value, list):
            print(f"   类型: {type(value).__name__} (非列表)")
            continue
        
        if len(value) == 0:
            print(f"   ⚠️ 空列表")
            continue
        
        print(f"   帧数: {len(value)}")
        
        # 检查第一个元素的类型
        first_elem = value[0]
        print(f"   元素类型: {type(first_elem).__name__}")
        
        if isinstance(first_elem, (list, tuple)):
            # 数值数组
            try:
                arr = np.array(value, dtype=np.float32)
                
                if arr.ndim == 1:
                    # 1D数组
                    print(f"   形状: ({len(arr)},)")
                    print(f"   Min: {arr.min():.4f}")
                    print(f"   Max: {arr.max():.4f}")
                    print(f"   Mean: {arr.mean():.4f}")
                    print(f"   Std: {arr.std():.4f}")
                    non_zero = np.count_nonzero(arr)
                    print(f"   非零: {non_zero}/{len(arr)} ({100*non_zero/len(arr):.1f}%)")
                    
                    is_all_zero = (non_zero == 0)
                    is_constant = (np.std(arr) < 1e-10) and not is_all_zero
                    if is_all_zero:
                        print(f"   ⚠️ 状态: 全零")
                    elif is_constant:
                        print(f"   ⚠️ 状态: 常量 ({arr[0]:.4f})")
                    else:
                        print(f"   ✅ 状态: 正常")
                
                elif arr.ndim == 2:
                    # 2D数组 (frames, dims)
                    print(f"   形状: {arr.shape}")
                    print(f"   各维度分析:")
                    
                    for i in range(arr.shape[1]):
                        col = arr[:, i]
                        non_zero = np.count_nonzero(col)
                        is_all_zero = (non_zero == 0)
                        is_constant = (np.std(col) < 1e-10) and not is_all_zero
                        
                        status = "⚠️全零" if is_all_zero else ("⚠️常量" if is_constant else "✅正常")
                        
                        print(f"      [dim_{i}] min={col.min():.4f}, max={col.max():.4f}, "
                              f"mean={col.mean():.4f}, std={col.std():.4f}, "
                              f"非零={non_zero}/{len(col)} ({100*non_zero/len(col):.1f}%) {status}")
                
                else:
                    print(f"   形状: {arr.shape} (高维数组)")
            
            except Exception as e:
                print(f"   ❌ 无法转换为numpy数组: {e}")
        
        elif isinstance(first_elem, dict):
            # 字典类型
            print(f"   字典键: {list(first_elem.keys())}")
            
            # 尝试分析字典中的数值字段
            for dict_key in first_elem.keys():
                dict_values = [elem.get(dict_key) for elem in value if isinstance(elem, dict)]
                
                if all(isinstance(v, (int, float)) for v in dict_values):
                    # 单个数值
                    arr = np.array(dict_values, dtype=np.float32)
                    non_zero = np.count_nonzero(arr)
                    is_all_zero = (non_zero == 0)
                    is_constant = (np.std(arr) < 1e-10) and not is_all_zero
                    status = "⚠️全零" if is_all_zero else ("⚠️常量" if is_constant else "✅正常")
                    
                    print(f"      '{dict_key}': min={arr.min():.4f}, max={arr.max():.4f}, "
                          f"mean={arr.mean():.4f}, std={arr.std():.4f}, "
                          f"非零={non_zero}/{len(arr)} ({100*non_zero/len(arr):.1f}%) {status}")
                
                elif all(isinstance(v, (list, tuple)) for v in dict_values):
                    # 数组
                    try:
                        arr = np.array(dict_values, dtype=np.float32)
                        if arr.ndim == 2:
                            print(f"      '{dict_key}': shape={arr.shape}")
                            for i in range(min(3, arr.shape[1])):  # 只显示前3维
                                col = arr[:, i]
                                non_zero = np.count_nonzero(col)
                                is_all_zero = (non_zero == 0)
                                is_constant = (np.std(col) < 1e-10) and not is_all_zero
                                status = "⚠️全零" if is_all_zero else ("⚠️常量" if is_constant else "✅正常")
                                
                                print(f"         [dim_{i}] min={col.min():.4f}, max={col.max():.4f}, "
                                      f"std={col.std():.4f} {status}")
                    except:
                        print(f"      '{dict_key}': 无法转换为数组")
        
        elif isinstance(first_elem, (int, float)):
            # 单个数值
            arr = np.array(value, dtype=np.float32)
            non_zero = np.count_nonzero(arr)
            is_all_zero = (non_zero == 0)
            is_constant = (np.std(arr) < 1e-10) and not is_all_zero
            status = "⚠️全零" if is_all_zero else ("⚠️常量" if is_constant else "✅正常")
            
            print(f"   Min: {arr.min():.4f}")
            print(f"   Max: {arr.max():.4f}")
            print(f"   Mean: {arr.mean():.4f}")
            print(f"   Std: {arr.std():.4f}")
            print(f"   非零: {non_zero}/{len(arr)} ({100*non_zero/len(arr):.1f}%)")
            print(f"   状态: {status}")
        
        else:
            print(f"   示例: {first_elem}")
        
        print()

if __name__ == "__main__":
    json_path = Path("/home/liu/program/robocoin-dataset/data/yinhe:default_version/20250328_record45/data.json")
    
    if not json_path.exists():
        print(f"❌ 文件不存在: {json_path}")
        exit(1)
    
    analyze_yinhe_data(json_path)

