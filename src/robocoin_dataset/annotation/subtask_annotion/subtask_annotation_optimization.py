import json
import re

import requests


def _detect_language(text: str) -> str:
    """
    检测文本语言
    Returns: 'zh' (中文), 'en' (英文), or 'unknown'
    """
    # 中文检测：包含中文字符
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    # 英文检测：主要包含英文字母
    if re.search(r"[a-zA-Z]", text) and not re.search(r"[\u4e00-\u9fff]", text):
        return "en"
    return "unknown"


def optimize_annotation(annotation_set: set[str], ds_api_key: str) -> dict[str, str]:
    # 分类指令
    zh_annotations = list()
    annotation_list = list(annotation_set)
    result = dict()

    for annotation in annotation_list:
        lang = _detect_language(annotation)
        if lang == "zh":
            zh_annotations.append(annotation)
        else:
            result[annotation] = annotation

    # 准备提示词
    prompt_parts = []

    if zh_annotations:
        zh_text = "\n".join(f"{idx + 1}. {cmd}" for idx, cmd in enumerate(zh_annotations))
        prompt_parts.append(f"""
            请将以下中文动作指令逐条翻译为自然的英文语句，保持语义准确：
            {zh_text}
        """)

    if not prompt_parts:
        return result

    prompt = "\n".join(prompt_parts)
    prompt += "\n\n请按顺序给出处理结果，不要编号，每行一个结果："

    # DeepSeek API配置
    api_url = "https://api.deepseek.com/v1/chat/completions"

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ds_api_key}"}

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "top_p": 0.8,
        "max_tokens": 1024,
        "stream": False,
    }

    try:
        print("Tring to call DeepSeek API to translate Chinese annotations to English")
        response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=100)

        if response.status_code == 200:
            response_data = response.json()
            processed_text = response_data["choices"][0]["message"]["content"].strip()

            # 处理结果
            result_lines = [line.strip() for line in processed_text.split("\n") if line.strip()]

            # 清理可能的编号
            cleaned_results = []
            for line in result_lines:
                if ". " in line and line.split(". ")[0].isdigit():
                    cleaned_results.append(line.split(". ", 1)[-1])
                else:
                    cleaned_results.append(line)

            # 验证结果数量
            expected_count = len(zh_annotations)
            if len(cleaned_results) != expected_count:
                raise ValueError(
                    f"处理结果数量({len(cleaned_results)})与预期数量({expected_count})不匹配"
                )
            result.update(
                {
                    zh_annotation: cleaned_annotation
                    for zh_annotation, cleaned_annotation in zip(zh_annotations, cleaned_results)
                }
            )

            return result

        raise Exception(f"API请求失败: {response.status_code} - {response.text}")

    except Exception as e:
        raise Exception(f"处理指令时出错: {str(e)}")
