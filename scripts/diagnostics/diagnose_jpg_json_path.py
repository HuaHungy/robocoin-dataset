#!/usr/bin/env python3
"""
诊断 JPG+JSON 数据集路径问题

检查指定路径及其周边目录，找到真正的 episode 位置
"""

import sys
from pathlib import Path
from collections import deque


def check_is_episode(path: Path) -> bool:
    """检查路径是否是 JPG+JSON episode（包含 arm/ 和 camera/）"""
    if not path.is_dir():
        return False
    
    try:
        subdirs = {d.name for d in path.iterdir() if d.is_dir()}
        return 'arm' in subdirs and 'camera' in subdirs
    except Exception:
        return False


def find_episodes_around(start_path: Path, levels_up: int = 3, levels_down: int = 3):
    """在指定路径周围查找 episodes
    
    Args:
        start_path: 起始路径
        levels_up: 向上查找的层数
        levels_down: 向下查找的层数
    """
    print("=" * 80)
    print(f"诊断 JPG+JSON 路径问题")
    print("=" * 80)
    print(f"\n📂 问题路径: {start_path}")
    print(f"   存在: {start_path.exists()}")
    
    if not start_path.exists():
        print(f"\n❌ 路径不存在！")
        return
    
    # 检查当前路径
    print(f"\n" + "-" * 80)
    print(f"1️⃣  检查当前路径")
    print("-" * 80)
    
    is_ep = check_is_episode(start_path)
    print(f"   是否为 episode: {'✅ 是' if is_ep else '❌ 否'}")
    
    if start_path.is_dir():
        try:
            subdirs = [d.name for d in start_path.iterdir() if d.is_dir()]
            print(f"   子目录 ({len(subdirs)} 个):")
            for d in subdirs[:15]:
                print(f"     - {d}")
            if len(subdirs) > 15:
                print(f"     ... 还有 {len(subdirs) - 15} 个")
        except Exception as e:
            print(f"   ❌ 无法读取子目录: {e}")
    
    # 向上查找
    print(f"\n" + "-" * 80)
    print(f"2️⃣  向上查找 (最多 {levels_up} 层)")
    print("-" * 80)
    
    current = start_path
    for level in range(1, levels_up + 1):
        parent = current.parent
        if parent == current:  # 已到根目录
            break
        
        print(f"\n   Level -{level}: {parent}")
        is_ep = check_is_episode(parent)
        print(f"   是否为 episode: {'✅ 是' if is_ep else '❌ 否'}")
        
        if parent.is_dir():
            try:
                siblings = [d.name for d in parent.iterdir() if d.is_dir()]
                print(f"   兄弟目录 ({len(siblings)} 个):")
                for d in siblings[:10]:
                    indicator = " ← 当前路径" if parent / d == current else ""
                    print(f"     - {d}{indicator}")
                if len(siblings) > 10:
                    print(f"     ... 还有 {len(siblings) - 10} 个")
            except Exception as e:
                print(f"   ❌ 无法读取兄弟目录: {e}")
        
        current = parent
    
    # 向下查找（BFS）
    print(f"\n" + "-" * 80)
    print(f"3️⃣  向下查找 (最多 {levels_down} 层)")
    print("-" * 80)
    
    episodes_found = []
    queue = deque([(start_path, 0)])
    visited = set()
    
    while queue:
        path, depth = queue.popleft()
        
        if path in visited or depth > levels_down:
            continue
        visited.add(path)
        
        if check_is_episode(path):
            episodes_found.append((path, depth))
            continue  # 找到 episode 后不再向下
        
        if path.is_dir():
            try:
                for item in path.iterdir():
                    if item.is_dir() and not item.name.startswith('.') and item.name != '@eaDir':
                        queue.append((item, depth + 1))
            except Exception:
                pass
    
    if episodes_found:
        print(f"\n   ✅ 找到 {len(episodes_found)} 个 episodes:")
        for ep, depth in episodes_found[:20]:
            rel_path = ep.relative_to(start_path) if start_path in ep.parents else ep
            print(f"     - 深度 {depth}: {rel_path}")
            # 显示子目录
            try:
                subdirs = [d.name for d in ep.iterdir() if d.is_dir()]
                print(f"       子目录: {', '.join(subdirs[:8])}")
            except Exception:
                pass
        if len(episodes_found) > 20:
            print(f"     ... 还有 {len(episodes_found) - 20} 个")
    else:
        print(f"\n   ❌ 在向下 {levels_down} 层内未找到任何 episodes")
    
    # 建议
    print(f"\n" + "=" * 80)
    print("💡 建议")
    print("=" * 80)
    
    if is_ep:
        print("\n✅ 当前路径本身就是 episode！")
        print("   → 数据库配置的 task_path 应该是它的父目录")
    elif episodes_found:
        # 找到最近的 episode
        closest_ep, closest_depth = min(episodes_found, key=lambda x: x[1])
        print(f"\n✅ 找到 episodes（最近的在深度 {closest_depth}）")
        
        if closest_depth == 1:
            print(f"   → 当前路径正确，episodes 在其直接子目录")
        else:
            # 找到应该的 task_path
            suggested_path = closest_ep
            for _ in range(closest_depth - 1):
                suggested_path = suggested_path.parent
            print(f"   → 建议修改数据库中的 task_path 为:")
            print(f"     {suggested_path}")
    else:
        # 向上查找
        found_up = False
        current = start_path.parent
        for level in range(1, levels_up + 1):
            if check_is_episode(current):
                print(f"\n✅ 在父级目录（向上 {level} 层）找到 episode:")
                print(f"   {current}")
                print(f"   → 数据库配置的路径可能多了 {level} 层")
                found_up = True
                break
            if current.parent == current:
                break
            current = current.parent
        
        if not found_up:
            print(f"\n❌ 在上下 {max(levels_up, levels_down)} 层内都未找到 episodes")
            print(f"   → 可能原因:")
            print(f"      1. 数据还未上传")
            print(f"      2. 路径配置完全错误")
            print(f"      3. 数据集格式不是 JPG+JSON (arm/ 和 camera/)")


def main():
    if len(sys.argv) < 2:
        print("用法: python diagnose_jpg_json_path.py <path>")
        print("\n示例:")
        print("  python diagnose_jpg_json_path.py /mnt/nas/.../pour_sprite/data/chunk-000")
        sys.exit(1)
    
    path = Path(sys.argv[1])
    find_episodes_around(path, levels_up=4, levels_down=4)


if __name__ == "__main__":
    main()

