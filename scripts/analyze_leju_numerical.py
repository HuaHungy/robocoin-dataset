#!/usr/bin/env python3
"""Leju Waibu H5文件深度数值分析脚本

分析所有字段的数值特征：
- Min/Max/Mean/Std
- 非零帧数和比例
- 数据质量评估
"""

import h5py
import numpy as np
from pathlib import Path

def analyze_array(data: np.ndarray, name: str) -> dict:
    """分析数组的数值特征"""
    result = {
        'name': name,
        'shape': data.shape,
        'dtype': str(data.dtype)
    }
    
    # 如果是3D或更高维数组，先展平成2D
    if len(data.shape) > 2:
        # 对于3D数组 (N, M, K)，展平为 (N, M*K)
        original_shape = data.shape
        data = data.reshape(data.shape[0], -1)
        result['note'] = f'原始shape={original_shape}, 展平后分析'
    
    # 如果是多维数组，按最后一维分析
    if len(data.shape) > 1:
        result['dimensions'] = []
        num_dims = data.shape[-1]
        for i in range(num_dims):
            dim_data = data[:, i]
            
            # 计算统计信息
            non_zero_count = np.count_nonzero(dim_data)
            non_zero_ratio = non_zero_count / len(dim_data)
            
            # 检查是否全零
            is_all_zero = (non_zero_count == 0)
            
            # 检查是否常量
            is_constant = False
            if not is_all_zero:
                is_constant = (np.std(dim_data) < 1e-10)
            
            dim_result = {
                'index': i,
                'min': float(np.min(dim_data)),
                'max': float(np.max(dim_data)),
                'mean': float(np.mean(dim_data)),
                'std': float(np.std(dim_data)),
                'non_zero_count': int(non_zero_count),
                'non_zero_ratio': float(non_zero_ratio),
                'is_all_zero': is_all_zero,
                'is_constant': is_constant
            }
            result['dimensions'].append(dim_result)
    else:
        # 一维数组
        non_zero_count = np.count_nonzero(data)
        non_zero_ratio = non_zero_count / len(data)
        is_all_zero = (non_zero_count == 0)
        is_constant = False
        if not is_all_zero:
            is_constant = (np.std(data) < 1e-10)
        
        result['stats'] = {
            'min': float(np.min(data)),
            'max': float(np.max(data)),
            'mean': float(np.mean(data)),
            'std': float(np.std(data)),
            'non_zero_count': int(non_zero_count),
            'non_zero_ratio': float(non_zero_ratio),
            'is_all_zero': is_all_zero,
            'is_constant': is_constant
        }
    
    return result

def analyze_h5_file(h5_path: Path):
    """分析H5文件中的所有数据集"""
    print(f"📊 分析H5文件: {h5_path}")
    print(f"=" * 80)
    
    results = {}
    
    with h5py.File(h5_path, 'r') as f:
        def visit_datasets(name, obj):
            if isinstance(obj, h5py.Dataset):
                print(f"\n🔍 分析: {name}")
                data = np.array(obj)
                results[name] = analyze_array(data, name)
                
                # 打印摘要
                if 'dimensions' in results[name]:
                    print(f"   维度: {results[name]['shape']}")
                    print(f"   总维数: {len(results[name]['dimensions'])}")
                    
                    # 统计问题维度
                    all_zero_dims = [d['index'] for d in results[name]['dimensions'] if d['is_all_zero']]
                    constant_dims = [d['index'] for d in results[name]['dimensions'] if d['is_constant'] and not d['is_all_zero']]
                    
                    if all_zero_dims:
                        print(f"   ⚠️  全零维度: {all_zero_dims}")
                    if constant_dims:
                        print(f"   ⚠️  常量维度: {constant_dims}")
                    
                    # 打印数值范围摘要
                    all_mins = [d['min'] for d in results[name]['dimensions']]
                    all_maxs = [d['max'] for d in results[name]['dimensions']]
                    print(f"   数值范围: [{min(all_mins):.3f}, {max(all_maxs):.3f}]")
                else:
                    stats = results[name]['stats']
                    print(f"   维度: {results[name]['shape']}")
                    print(f"   数值范围: [{stats['min']:.3f}, {stats['max']:.3f}]")
                    if stats['is_all_zero']:
                        print(f"   ⚠️  全零数据")
                    elif stats['is_constant']:
                        print(f"   ⚠️  常量数据 (值={stats['mean']:.3f})")
        
        f.visititems(visit_datasets)
    
    return results

def generate_report(results: dict, output_path: Path):
    """生成Markdown格式的详细报告"""
    
    lines = [
        "# Leju Waibu数据集深度数值分析报告",
        "",
        "**分析时间**: 2025-10-22",
        "**数据文件**: proprio_stats.hdf5",
        "",
        "---",
        "",
        "## 📊 数值分析总览",
        ""
    ]
    
    # 按类别组织数据
    state_fields = {k: v for k, v in results.items() if k.startswith('state/')}
    action_fields = {k: v for k, v in results.items() if k.startswith('action/')}
    imu_fields = {k: v for k, v in results.items() if k.startswith('imu/')}
    other_fields = {k: v for k, v in results.items() if not (k.startswith('state/') or k.startswith('action/') or k.startswith('imu/'))}
    
    # State字段分析
    lines.extend([
        "### State字段分析",
        "",
        "| 字段 | 维度 | Min | Max | Mean | Std | 非零率 | 问题 |",
        "|------|------|-----|-----|------|-----|--------|------|"
    ])
    
    for name, data in sorted(state_fields.items()):
        if 'dimensions' in data:
            for dim in data['dimensions']:
                issues = []
                if dim['is_all_zero']:
                    issues.append("全零")
                elif dim['is_constant']:
                    issues.append("常量")
                
                issue_str = ", ".join(issues) if issues else "-"
                
                lines.append(
                    f"| `{name}[{dim['index']}]` | 1 | "
                    f"{dim['min']:.3f} | {dim['max']:.3f} | "
                    f"{dim['mean']:.3f} | {dim['std']:.3f} | "
                    f"{dim['non_zero_ratio']*100:.1f}% | {issue_str} |"
                )
        else:
            stats = data['stats']
            issues = []
            if stats['is_all_zero']:
                issues.append("全零")
            elif stats['is_constant']:
                issues.append("常量")
            
            issue_str = ", ".join(issues) if issues else "-"
            
            lines.append(
                f"| `{name}` | {data['shape'][0]} | "
                f"{stats['min']:.3f} | {stats['max']:.3f} | "
                f"{stats['mean']:.3f} | {stats['std']:.3f} | "
                f"{stats['non_zero_ratio']*100:.1f}% | {issue_str} |"
            )
    
    lines.extend(["", "---", ""])
    
    # Action字段分析
    lines.extend([
        "### Action字段分析",
        "",
        "| 字段 | 维度 | Min | Max | Mean | Std | 非零率 | 问题 |",
        "|------|------|-----|-----|------|-----|--------|------|"
    ])
    
    for name, data in sorted(action_fields.items()):
        if 'dimensions' in data:
            for dim in data['dimensions']:
                issues = []
                if dim['is_all_zero']:
                    issues.append("全零")
                elif dim['is_constant']:
                    issues.append("常量")
                
                issue_str = ", ".join(issues) if issues else "-"
                
                lines.append(
                    f"| `{name}[{dim['index']}]` | 1 | "
                    f"{dim['min']:.3f} | {dim['max']:.3f} | "
                    f"{dim['mean']:.3f} | {dim['std']:.3f} | "
                    f"{dim['non_zero_ratio']*100:.1f}% | {issue_str} |"
                )
    
    lines.extend(["", "---", ""])
    
    # IMU和其他字段
    if imu_fields:
        lines.extend([
            "### IMU字段分析",
            "",
            "| 字段 | 维度 | Min | Max | Mean | Std | 非零率 |",
            "|------|------|-----|-----|------|-----|--------|"
        ])
        
        for name, data in sorted(imu_fields.items()):
            if 'dimensions' in data:
                for dim in data['dimensions']:
                    lines.append(
                        f"| `{name}[{dim['index']}]` | 1 | "
                        f"{dim['min']:.3f} | {dim['max']:.3f} | "
                        f"{dim['mean']:.3f} | {dim['std']:.3f} | "
                        f"{dim['non_zero_ratio']*100:.1f}% |"
                    )
    
    lines.extend(["", "---", ""])
    
    # 问题汇总
    lines.extend([
        "## ⚠️ 数据质量问题汇总",
        "",
        "### 全零字段"
    ])
    
    all_zero_fields = []
    for name, data in results.items():
        if 'dimensions' in data:
            zero_dims = [d['index'] for d in data['dimensions'] if d['is_all_zero']]
            if zero_dims:
                all_zero_fields.append(f"- `{name}`: 维度 {zero_dims}")
        else:
            if data['stats']['is_all_zero']:
                all_zero_fields.append(f"- `{name}`: 全部数据")
    
    if all_zero_fields:
        lines.extend(all_zero_fields)
    else:
        lines.append("无全零字段 ✅")
    
    lines.extend(["", "### 常量字段", ""])
    
    constant_fields = []
    for name, data in results.items():
        if 'dimensions' in data:
            const_dims = [d['index'] for d in data['dimensions'] if d['is_constant'] and not d['is_all_zero']]
            if const_dims:
                constant_fields.append(f"- `{name}`: 维度 {const_dims}")
        else:
            if data['stats']['is_constant'] and not data['stats']['is_all_zero']:
                constant_fields.append(f"- `{name}`: 值={data['stats']['mean']:.3f}")
    
    if constant_fields:
        lines.extend(constant_fields)
    else:
        lines.append("无常量字段 ✅")
    
    # 写入文件
    output_path.write_text("\n".join(lines))
    print(f"\n\n✅ 报告已生成: {output_path}")

if __name__ == "__main__":
    h5_path = Path("/home/liu/program/robocoin-dataset/data/leju_robot:waibu_version/febbeddb-e90e-42b8-bc1d-db2b333e1af1/proprio_stats/proprio_stats.hdf5")
    
    if not h5_path.exists():
        print(f"❌ 文件不存在: {h5_path}")
        exit(1)
    
    # 分析数据
    results = analyze_h5_file(h5_path)
    
    # 生成报告
    output_path = Path("docs/LEJU_WAIBU_NUMERICAL_ANALYSIS.md")
    generate_report(results, output_path)

