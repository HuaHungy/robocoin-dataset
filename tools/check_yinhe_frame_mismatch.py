#!/usr/bin/env python3
"""
检查银河通用数据集中 JSON 和 MP4 帧数不一致的问题

该脚本会：
1. 读取转换器配置文件，了解哪些字段会被使用
2. 扫描银河数据集的所有 episodes
3. 对每个 episode：
   - 使用 ffprobe 检测所有 MP4 视频的帧数
   - 读取 data.json 中**配置使用的字段**的数据长度
   - 模拟转换器逻辑，计算最小帧数
   - 检查是否会导致转换失败
4. 生成详细的问题报告

Usage:
    # 测试单个任务（快速测试脚本是否工作）
    python check_yinhe_frame_mismatch.py --test
    
    # 批量检查所有任务（完整扫描，需要较长时间）
    python check_yinhe_frame_mismatch.py --full
    
    # 指定自定义路径和配置
    python check_yinhe_frame_mismatch.py --full --base-path /path/to/dataset --config /path/to/config.yaml

输出：
    - 控制台：实时显示检查进度和发现的问题
    - yinhe_frame_check_results.json：详细的 JSON 报告文件
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Set
import argparse
from collections import defaultdict
import yaml


def load_used_json_fields(config_path: Path) -> Set[str]:
    """从配置文件中提取所有使用的 JSON 字段名
    
    Returns:
        Set of JSON field names that are actually used in the conversion
    """
    used_fields = set()
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 从 observation.state 提取
        if 'features' in config and 'observation' in config['features']:
            if 'state' in config['features']['observation']:
                for sub_state in config['features']['observation']['state'].get('sub_state', []):
                    if 'args' in sub_state and 'json_path' in sub_state['args']:
                        json_path = sub_state['args']['json_path']
                        # 只取第一个路径元素（顶层字段名）
                        field_name = json_path.split('/')[0]
                        used_fields.add(field_name)
        
        # 从 action 提取
        if 'features' in config and 'action' in config['features']:
            for sub_action in config['features']['action'].get('sub_action', []):
                if 'args' in sub_action and 'json_path' in sub_action['args']:
                    json_path = sub_action['args']['json_path']
                    # 只取第一个路径元素（顶层字段名）
                    field_name = json_path.split('/')[0]
                    used_fields.add(field_name)
        
        # 添加 camera 字段（这些字段在 JSON 中也是列表）
        if 'features' in config and 'observation' in config['features']:
            if 'images' in config['features']['observation']:
                for image_config in config['features']['observation']['images']:
                    if 'args' in image_config and 'cam_name' in image_config['args']:
                        cam_name = image_config['args']['cam_name']
                        used_fields.add(cam_name)
        
        return used_fields
    
    except Exception as e:
        print(f"⚠️  Warning: Failed to load config file {config_path}: {e}")
        return set()


def get_video_frame_count(video_path: Path) -> int:
    """使用 ffprobe 获取视频帧数"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-count_packets',
            '-show_entries', 'stream=nb_read_packets',
            '-of', 'csv=p=0',
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
        
        # 备用方法：使用 nb_frames
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=nb_frames',
            '-of', 'default=nokey=1:noprint_wrappers=1',
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
        
        return -1
    except Exception as e:
        print(f"  ⚠️  Error reading video {video_path.name}: {e}")
        return -1


def get_json_frame_counts(json_path: Path) -> Dict[str, int]:
    """获取 JSON 文件中各个字段的帧数"""
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        if 'data' not in data:
            return {}
        
        frame_counts = {}
        for field_name, field_data in data['data'].items():
            if isinstance(field_data, list):
                frame_counts[field_name] = len(field_data)
            elif isinstance(field_data, dict):
                # 对于字典类型，可能是 {timestamp: value} 格式
                frame_counts[field_name] = len(field_data)
        
        return frame_counts
    except Exception as e:
        print(f"  ⚠️  Error reading JSON {json_path.name}: {e}")
        return {}


def check_episode(episode_dir: Path, used_json_fields: Set[str] = None) -> Dict:
    """检查单个 episode 是否有真正的问题
    
    转换器策略：取所有数据源的最小帧数，允许帧数不一致
    
    真正的问题：
    1. 所有数据源的最小帧数为 0（会导致转换失败）
    2. 某些关键视频文件缺失或无法读取
    3. JSON 文件格式错误或缺少必要字段
    
    Args:
        episode_dir: Episode 目录路径
        used_json_fields: 配置中使用的 JSON 字段集合，如果为 None 则检查所有字段
    """
    result = {
        'episode_path': str(episode_dir),
        'has_problem': False,
        'json_frames': {},
        'json_frames_used': {},  # 仅配置中使用的字段
        'json_frames_unused': {},  # 未使用的字段
        'video_frames': {},
        'min_frames': 0,
        'min_frames_all': 0,  # 包含未使用字段的最小帧数（用于对比）
        'problems': [],
        'warnings': []
    }
    
    # 查找 data.json
    json_files = list(episode_dir.glob('*data.json'))
    if not json_files:
        result['has_problem'] = True
        result['problems'].append({
            'type': 'missing_json',
            'severity': 'error',
            'details': 'No data.json found'
        })
        return result
    
    json_path = json_files[0]
    
    # 获取 JSON 各字段的帧数
    json_frame_counts = get_json_frame_counts(json_path)
    result['json_frames'] = json_frame_counts
    
    if not json_frame_counts:
        result['has_problem'] = True
        result['problems'].append({
            'type': 'invalid_json',
            'severity': 'error',
            'details': 'Failed to read JSON or no data fields'
        })
        return result
    
    # 分离使用和未使用的字段
    if used_json_fields:
        json_frames_used = {k: v for k, v in json_frame_counts.items() if k in used_json_fields}
        json_frames_unused = {k: v for k, v in json_frame_counts.items() if k not in used_json_fields}
        result['json_frames_used'] = json_frames_used
        result['json_frames_unused'] = json_frames_unused
    else:
        # 如果没有提供配置，则假设所有字段都使用
        json_frames_used = json_frame_counts
        json_frames_unused = {}
        result['json_frames_used'] = json_frames_used
    
    # 获取所有视频的帧数
    video_files = list(episode_dir.glob('*.mp4'))
    video_frame_counts = {}
    
    for video_file in video_files:
        frame_count = get_video_frame_count(video_file)
        video_frame_counts[video_file.name] = frame_count
    
    result['video_frames'] = video_frame_counts
    
    # 计算最小帧数（模拟转换器逻辑）
    # 只考虑配置中使用的字段
    all_frame_counts = list(json_frames_used.values()) + [v for v in video_frame_counts.values() if v > 0]
    all_frame_counts_with_unused = list(json_frame_counts.values()) + [v for v in video_frame_counts.values() if v > 0]
    
    if not all_frame_counts:
        result['has_problem'] = True
        result['problems'].append({
            'type': 'no_valid_frames',
            'severity': 'error',
            'details': 'No valid frame counts found in used JSON fields or videos'
        })
        return result
    
    min_frames = min(all_frame_counts)
    result['min_frames'] = min_frames
    
    # 也计算包含未使用字段的最小帧数（用于对比）
    if all_frame_counts_with_unused:
        result['min_frames_all'] = min(all_frame_counts_with_unused)
    
    # 问题1: 最小帧数为 0（会导致转换失败）
    if min_frames == 0:
        result['has_problem'] = True
        bottleneck_sources = []
        for key, count in json_frames_used.items():
            if count == 0:
                bottleneck_sources.append(f"JSON(used):{key}")
        for key, count in video_frame_counts.items():
            if count == 0:
                bottleneck_sources.append(f"Video:{key}")
        
        result['problems'].append({
            'type': 'zero_frames',
            'severity': 'error',
            'details': f"Minimum frame count is 0, will cause conversion failure. Bottleneck: {', '.join(bottleneck_sources)}"
        })
    
    # 特别说明：如果包含未使用字段时最小帧数也是 0，但配置字段最小帧数不是 0
    if used_json_fields and result['min_frames_all'] == 0 and min_frames > 0:
        unused_zero_fields = [k for k, v in json_frames_unused.items() if v == 0]
        result['warnings'].append({
            'type': 'unused_fields_zero',
            'severity': 'info',
            'details': f"Unused fields have 0 frames (OK to ignore): {', '.join(unused_zero_fields)}"
        })
    
    # 问题2: 视频文件读取失败（帧数为 -1）
    failed_videos = [name for name, count in video_frame_counts.items() if count == -1]
    if failed_videos:
        result['has_problem'] = True
        result['problems'].append({
            'type': 'video_read_error',
            'severity': 'error',
            'details': f"Failed to read video files: {', '.join(failed_videos)}"
        })
    
    # 问题3: 缺少预期的视频文件（银河数据集应该有3个视频）
    expected_cameras = ['camera_front_head_rgb.mp4', 'camera_left_wrist.mp4', 'camera_right_wrist.mp4']
    missing_videos = [cam for cam in expected_cameras if cam not in video_frame_counts]
    if missing_videos:
        result['has_problem'] = True
        result['problems'].append({
            'type': 'missing_videos',
            'severity': 'error',
            'details': f"Missing expected video files: {', '.join(missing_videos)}"
        })
    
    # 问题4: 视频帧数与预期帧数不匹配（模拟 _prevalidate_files 的验证）
    # 预期帧数应该是最小帧数（转换器的策略）
    if min_frames > 0 and not failed_videos:
        for video_name, video_frame_count in video_frame_counts.items():
            if video_frame_count > 0 and video_frame_count != min_frames:
                # 视频帧数与最小帧数不同
                # 这可能不是问题（转换器会截断到最小值），但值得记录
                result['warnings'].append({
                    'type': 'video_frame_mismatch',
                    'severity': 'warning',
                    'details': f"Video '{video_name}' has {video_frame_count} frames, but minimum is {min_frames}. Converter will truncate to {min_frames}."
                })
    
    # 警告1: 帧数差异过大（超过 10%）
    if min_frames > 0:
        max_frames = max(all_frame_counts)
        if (max_frames - min_frames) / min_frames > 0.1:  # 差异超过 10%
            result['warnings'].append({
                'type': 'large_frame_difference',
                'severity': 'warning',
                'details': f"Large frame count difference: min={min_frames}, max={max_frames}, diff={max_frames - min_frames} ({(max_frames - min_frames) / min_frames * 100:.1f}%)"
            })
    
    # 警告2: 某些 JSON 字段帧数异常少（可能是数据收集问题）
    if min_frames > 0:
        for field, count in json_frame_counts.items():
            if count > 0 and count < min_frames * 0.5:  # 少于最小值的一半
                result['warnings'].append({
                    'type': 'low_frame_count',
                    'severity': 'warning',
                    'details': f"Field '{field}' has unusually low frame count: {count} (min is {min_frames})"
                })
    
    return result


def find_all_episodes(base_path: Path, max_tasks: int = None) -> List[Path]:
    """查找所有 episode 目录
    
    支持两种结构：
    1. task/batch/episode (如 fold_clothe)
    2. task/subtask/batch/episode (如 use_dryer)
    """
    episodes = []
    
    skip_dirs = {'.', '@', 'System Volume Information', 'error'}
    tasks = [d for d in base_path.iterdir() 
             if d.is_dir() 
             and not any(d.name.startswith(skip) for skip in ['.', '@'])
             and d.name not in skip_dirs]
    tasks = sorted(tasks)
    
    if max_tasks:
        tasks = tasks[:max_tasks]
    
    for task_dir in tasks:
        print(f"  📦 扫描任务: {task_dir.name}")
        
        # 第一层子目录（可能是 batch 或 subtask）
        level1_dirs = [d for d in task_dir.iterdir() 
                       if d.is_dir() 
                       and not d.name.startswith('.') 
                       and not d.name.startswith('@')
                       and not d.name.endswith('.yaml')]
        
        for level1_dir in level1_dirs:
            # 检查是否直接包含 episode（结构1: task/batch/episode）
            level2_dirs = [d for d in level1_dir.iterdir() 
                          if d.is_dir() 
                          and not d.name.startswith('.') 
                          and not d.name.startswith('@')]
            
            # 如果 level2 中有 data.json，说明 level2 是 episode
            has_episodes = any((d / 'data.json').exists() for d in level2_dirs)
            
            if has_episodes:
                # 结构1: task/batch/episode
                for episode_dir in level2_dirs:
                    if (episode_dir / 'data.json').exists():
                        episodes.append(episode_dir)
            else:
                # 结构2: task/subtask/batch/episode
                # level1_dir 是 subtask, level2_dirs 是 batch
                for batch_dir in level2_dirs:
                    episode_dirs = [d for d in batch_dir.iterdir() 
                                   if d.is_dir() 
                                   and not d.name.startswith('.') 
                                   and not d.name.startswith('@')]
                    for episode_dir in episode_dirs:
                        if (episode_dir / 'data.json').exists():
                            episodes.append(episode_dir)
    
    return episodes


def print_summary(results: List[Dict]):
    """打印汇总统计"""
    total = len(results)
    with_problems = sum(1 for r in results if r.get('has_problem', False))
    with_warnings = sum(1 for r in results if r.get('warnings', []))
    
    print("\n" + "="*80)
    print("📊 汇总统计")
    print("="*80)
    print(f"总 Episode 数: {total}")
    print(f"✅ 正常（可转换）: {total - with_problems} ({(total - with_problems)/total*100:.1f}%)" if total > 0 else "")
    print(f"❌ 有严重问题（会转换失败）: {with_problems} ({with_problems/total*100:.1f}%)" if total > 0 else "")
    print(f"⚠️  有警告（可转换但有风险）: {with_warnings} ({with_warnings/total*100:.1f}%)" if total > 0 else "")
    
    # 统计不同类型的问题
    problem_types = defaultdict(int)
    warning_types = defaultdict(int)
    
    for result in results:
        if result.get('has_problem', False):
            for problem in result.get('problems', []):
                problem_types[problem['type']] += 1
        
        for warning in result.get('warnings', []):
            warning_types[warning['type']] += 1
    
    if problem_types:
        print("\n❌ 严重问题类型分布:")
        for ptype, count in sorted(problem_types.items(), key=lambda x: -x[1]):
            print(f"  - {ptype}: {count}")
    
    if warning_types:
        print("\n⚠️  警告类型分布:")
        for wtype, count in sorted(warning_types.items(), key=lambda x: -x[1]):
            print(f"  - {wtype}: {count}")
    
    # 打印有严重问题的 episode（会导致转换失败）
    if with_problems > 0:
        print(f"\n❌ 有严重问题的 Episode 列表 (前 20 个):")
        count = 0
        for result in results:
            if result.get('has_problem', False) and count < 20:
                print(f"\n  📁 {result['episode_path']}")
                print(f"     最小帧数: {result.get('min_frames', 'N/A')}")
                for problem in result.get('problems', []):
                    print(f"     ❌ {problem['type']}: {problem['details']}")
                count += 1
    
    # 统计帧数分布
    min_frames_list = [r.get('min_frames', 0) for r in results if not r.get('has_problem', False)]
    if min_frames_list:
        print(f"\n📊 可转换 Episode 的帧数分布:")
        print(f"  - 最小: {min(min_frames_list)}")
        print(f"  - 最大: {max(min_frames_list)}")
        print(f"  - 平均: {sum(min_frames_list) / len(min_frames_list):.1f}")


def main():
    parser = argparse.ArgumentParser(description='检查银河数据集 JSON/MP4 帧数一致性')
    parser.add_argument('--test', action='store_true', help='测试模式：只检查第一个任务')
    parser.add_argument('--full', action='store_true', help='完整模式：检查所有任务')
    parser.add_argument('--base-path', type=str, 
                       default='/mnt/nas/synnas/docker/外部数据/银河通用',
                       help='数据集根目录')
    parser.add_argument('--config', type=str,
                       default='scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml',
                       help='转换器配置文件路径')
    
    args = parser.parse_args()
    
    if not args.test and not args.full:
        parser.print_help()
        return
    
    base_path = Path(args.base_path)
    
    if not base_path.exists():
        print(f"❌ 数据集路径不存在: {base_path}")
        return
    
    # 加载配置文件，获取使用的字段
    config_path = Path(args.config)
    used_json_fields = None
    
    if config_path.exists():
        used_json_fields = load_used_json_fields(config_path)
        print(f"📋 已加载配置文件: {config_path}")
        print(f"   配置中使用的 JSON 字段 ({len(used_json_fields)}个): {sorted(used_json_fields)}")
    else:
        print(f"⚠️  配置文件不存在: {config_path}")
        print(f"   将检查所有 JSON 字段")
    
    print(f"\n🔍 开始检查银河数据集: {base_path}")
    
    # 查找所有 episodes
    max_tasks = 1 if args.test else None
    mode_name = "测试模式 (1个任务)" if args.test else "完整模式 (所有任务)"
    print(f"📦 模式: {mode_name}")
    
    episodes = find_all_episodes(base_path, max_tasks=max_tasks)
    print(f"📂 找到 {len(episodes)} 个 episodes")
    
    if not episodes:
        print("❌ 未找到任何 episode")
        return
    
    # 测试模式只检查前 100 个
    if args.test and len(episodes) > 100:
        print(f"⚠️  测试模式：只检查前 100 个 episodes（共 {len(episodes)} 个）")
        episodes = episodes[:100]
    
    # 检查每个 episode
    results = []
    print(f"\n{'='*80}")
    print("开始检查...")
    print(f"{'='*80}\n")
    
    for i, episode_dir in enumerate(episodes, 1):
        print(f"[{i}/{len(episodes)}] 检查: {episode_dir}")
        result = check_episode(episode_dir, used_json_fields)
        results.append(result)
        
        # 实时显示严重问题
        if result.get('has_problem', False):
            print(f"  ❌ 严重问题（会转换失败）:")
            for problem in result.get('problems', []):
                print(f"     {problem['details']}")
        elif result.get('warnings', []):
            print(f"  ⚠️  有警告，但可转换 (最小帧数: {result.get('min_frames', 'N/A')})")
            if len(result['warnings']) <= 2:  # 只显示前2个警告
                for warning in result['warnings'][:2]:
                    print(f"     {warning['details']}")
        else:
            print(f"  ✅ 正常 (最小帧数: {result.get('min_frames', 'N/A')})")
    
    # 打印汇总
    print_summary(results)
    
    # 保存详细结果到 JSON
    output_file = Path('yinhe_frame_check_results.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 详细结果已保存到: {output_file}")


if __name__ == '__main__':
    main()
