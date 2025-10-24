#!/usr/bin/env python3
"""MMK2 debugging script"""
import sys
sys.path.insert(0, 'src')

from pathlib import Path
import yaml
import bson
import numpy as np

# 加载配置
config_path = Path("scripts/format_converters/tolerobot/configs/converter_config_discover_robotics_aitbot_mmk2_third_view.yaml")
with open(config_path) as f:
    config = yaml.safe_load(f)

# 读取数据文件
episode_dir = Path("data/discover_robotics_aitbot_mmk2:third_view/episode_24")
main_bson = episode_dir / "episode_0.bson"
xhand_bson = episode_dir / "xhand_control_data.bson"

# 读取主BSON
with open(main_bson, 'rb') as f:
    main_doc = bson.decode_all(f.read())[0]

# 读取手部BSON
with open(xhand_bson, 'rb') as f:
    xhand_doc = bson.decode_all(f.read())[0]

print("="*60)
print("配置文件中定义的 observation.state 字段：")
print("="*60)

total_dims = 0
hand_fields = []
for i, sub_state in enumerate(config['features']['observation']['state']['sub_state']):
    bson_file = sub_state['args']['bson_file']
    data_path = sub_state['args']['data_path']
    range_from = sub_state['args']['range_from']
    range_to = sub_state['args']['range_to']
    dims = len(sub_state['names'])
    
    print(f"\n{i+1}. {data_path}")
    print(f"   - bson_file: {bson_file}")
    print(f"   - range: [{range_from}:{range_to}]")
    print(f"   - dims: {dims}")
    
    if bson_file == 'xhand_control_data.bson':
        hand_fields.append((data_path, range_from, range_to, dims))
        print(f"   - ⚠️  这是手部数据")
    
    total_dims += dims

print(f"\n总维度: {total_dims}")

print("\n" + "="*60)
print("尝试从实际数据中提取手部字段：")
print("="*60)

frames = xhand_doc.get('frames', [])
print(f"\nxhand_control_data.bson 总帧数: {len(frames)}")

if frames:
    frame0 = frames[0]
    print(f"第一帧的键: {list(frame0.keys())}")
    
    for data_path, range_from, range_to, expected_dims in hand_fields:
        print(f"\n尝试提取: {data_path} [{range_from}:{range_to}]")
        
        # 模拟converter的解析逻辑
        path_parts = data_path.split(".")
        data = frame0
        for part in path_parts:
            if isinstance(data, dict) and part in data:
                data = data[part]
                print(f"  → 找到 {part}: {type(data)}")
            else:
                print(f"  ❌ 未找到 {part}")
                print(f"     可用键: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
                data = None
                break
        
        if data is not None:
            if isinstance(data, (list, tuple)):
                actual_len = len(data)
                extracted = data[range_from:range_to]
                print(f"  ✅ 成功提取: 长度={actual_len}, 提取={len(extracted)}维")
                print(f"     数据: {extracted}")
            else:
                print(f"  ❌ 数据类型错误: {type(data)}")

print("\n" + "="*60)
print("主BSON数据结构：")
print("="*60)
if 'data' in main_doc:
    for key in sorted(main_doc['data'].keys()):
        frames = main_doc['data'][key]
        print(f"  • {key}: {len(frames)} 帧")

