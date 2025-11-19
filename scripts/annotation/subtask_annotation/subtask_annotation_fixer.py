import json
import argparse
import re

def fix_jsonl_fully(input_path, output_path):
    """修复JSONL文件中的格式错误，包括：
    1. 值中未转义的双引号
    2. 截断的行（以 > 结尾）
    3. 键名格式错误
    4. 冒号格式错误
    """
    with open(input_path, 'r', encoding='utf-8') as f_in, \
         open(output_path, 'w', encoding='utf-8') as f_out:
        
        line_num = 0
        fixed_count = 0
        error_count = 0
        
        for line in f_in:
            line_num += 1
            original_line = line.strip()
            if not original_line:
                continue  # 跳过空行

            try:
                # 步骤1：检查并移除截断标记
                is_truncated = False
                if original_line.endswith('>'):
                    print(f"⚠ 第 {line_num} 行被截断，尝试修复...")
                    original_line = original_line[:-1]  # 移除截断标记
                    is_truncated = True
                
                # 步骤2：修复键名格式（确保键用双引号包裹）
                fixed_line = re.sub(
                    r'(?<=[{,\s])(subtask_index|subtask|episode_idx|start_frame_idx|end_frame_idx)(?=\s*:)',
                    r'"\1"',
                    original_line
                )
                
                # 步骤3：修复冒号错误（将 :: 改为 :）
                fixed_line = re.sub(r'::', ':', fixed_line)
                
                # 步骤4：修复值中的未转义双引号
                # 使用更智能的方法来处理嵌套引号
                def fix_subtask_value(line):
                    # 查找 "subtask": 后的值
                    match = re.search(r'"subtask"\s*:\s*"', line)
                    if not match:
                        return line
                    
                    start_pos = match.end()
                    # 从起始位置开始查找结束引号（考虑到可能有未转义的引号）
                    value_chars = []
                    i = start_pos
                    quote_count = 0
                    
                    while i < len(line):
                        char = line[i]
                        
                        if char == '"':
                            # 检查这是否是值的结束引号
                            # 如果后面是 } 或 , 说明是结束引号
                            next_chars = line[i+1:i+3].strip()
                            if next_chars.startswith('}') or next_chars.startswith(','):
                                # 这是结束引号
                                break
                            else:
                                # 这是值内部的引号，需要转义
                                value_chars.append('\\"')
                        else:
                            value_chars.append(char)
                        i += 1
                    
                    # 重新构建行
                    new_value = ''.join(value_chars)
                    before = line[:start_pos]
                    after = line[i:] if i < len(line) else '"}'
                    
                    return f'{before}{new_value}{after}'
                
                fixed_line = fix_subtask_value(fixed_line)
                
                # 步骤5：确保行完整（有闭合的 }）
                if not fixed_line.rstrip().endswith('}'):
                    if is_truncated:
                        # 尝试补全截断的行
                        fixed_line = fixed_line.rstrip() + '"}'
                        print(f"  已补全截断的行")
                
                # 步骤6：验证并写入
                try:
                    # 尝试解析修复后的行
                    data = json.loads(fixed_line)
                    
                    # 确保输出格式正确
                    json.dump(data, f_out, ensure_ascii=False)
                    f_out.write('\n')
                    
                    if is_truncated or original_line != line.strip():
                        print(f"✓ 已修复第 {line_num} 行")
                        print(f"  原始: {original_line[:80]}...")
                        print(f"  修复: {json.dumps(data, ensure_ascii=False)[:80]}...")
                        fixed_count += 1
                    
                except json.JSONDecodeError as e:
                    # 如果还是失败，尝试更激进的修复
                    print(f"✗ 第 {line_num} 行修复失败，尝试备用方案...")
                    
                    # 备用方案：手动提取值
                    subtask_index_match = re.search(r'"subtask_index"\s*:\s*(\d+)', original_line)
                    subtask_match = re.search(r'"subtask"\s*:\s*"(.+?)(?:"\s*}|$)', original_line)
                    
                    if subtask_index_match and subtask_match:
                        subtask_index = int(subtask_index_match.group(1))
                        subtask_value = subtask_match.group(1)
                        
                        # 清理值（移除截断标记和额外的引号）
                        subtask_value = subtask_value.rstrip('>').rstrip('"')
                        
                        # 构建新的字典
                        data = {
                            "subtask_index": subtask_index,
                            "subtask": subtask_value
                        }
                        
                        json.dump(data, f_out, ensure_ascii=False)
                        f_out.write('\n')
                        print(f"✓ 使用备用方案修复第 {line_num} 行")
                        print(f"  结果: {json.dumps(data, ensure_ascii=False)}")
                        fixed_count += 1
                    else:
                        print(f"✗✗ 第 {line_num} 行无法修复")
                        print(f"  原始: {original_line}")
                        print(f"  错误: {e}")
                        error_count += 1
                        
            except Exception as e:
                print(f"✗✗ 第 {line_num} 行处理出错: {e}")
                print(f"  原始: {original_line}")
                error_count += 1
        
        print(f"\n" + "="*60)
        print(f"处理完成！")
        print(f"  总行数: {line_num}")
        print(f"  修复数: {fixed_count}")
        print(f"  错误数: {error_count}")
        print(f"  成功率: {(line_num - error_count) / line_num * 100:.1f}%")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='全面修复JSONL格式错误（引号、键名、冒号等）')
    parser.add_argument('--input', required=True, help='输入JSONL文件路径')
    parser.add_argument('--output', required=True, help='输出修复后JSONL文件路径')
    args = parser.parse_args()
    
    fix_jsonl_fully(args.input, args.output)
    print(f"修复完成，结果已保存至 {args.output}")

"""
# usage:
python scripts/annotation/subtask_annotation/subtask_annotation_fixer.py \
--input /mnt/nas/synnas/docker2/robocoin-datasets/Cobot_Magic_five_in_one_board_storage_qced_hardlink/annotations/subtask_annotations.jsonl \
--output /mnt/nas/synnas/docker2/robocoin-datasets/Cobot_Magic_five_in_one_board_storage_qced_hardlink/annotations/subtask_annotations_fixed.jsonl

# check result
cat /mnt/nas/synnas/docker2/robocoin-datasets/Cobot_Magic_five_in_one_board_storage_qced_hardlink/annotations/subtask_annotations_fixed.jsonl | jq .
"""