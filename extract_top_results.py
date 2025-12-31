"""
从 intent_search_results.jsonl 中提取每个 query_index 的 result_index=1 的 title
去除 "paths." 前缀并打印
"""
import json
from pathlib import Path


def extract_top_results(input_file: str = "outputs/intent_search_results.jsonl", print_output: bool = True):
    """
    从 JSONL 文件中提取每个 query_index 的 result_index=1 的 title
    
    Args:
        input_file: 输入文件路径
        print_output: 是否打印输出，默认为 True
    """
    results = []
    
    if not Path(input_file).exists():
        if print_output:
            print(f"文件不存在: {input_file}")
        return []
    
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
                # 只取 result_index 为 1 的行
                if data.get("result_index") == 1:
                    title = data.get("title", "")
                    # 去除开头的 "paths." 前缀
                    if title.startswith("paths."):
                        title = title.replace("paths.", "", 1)
                    results.append({
                        "query_index": data.get("query_index"),
                        "query": data.get("query"),
                        "title": title
                    })
            except json.JSONDecodeError as e:
                if print_output:
                    print(f"解析 JSON 失败: {line[:50]}... 错误: {e}")
                continue
    
    # 按 query_index 排序
    results.sort(key=lambda x: x["query_index"])

    if print_output:
        for item in results:
            print(item['title'])
    
    return results


def get_title_list(input_file: str = "outputs/intent_search_results.jsonl") -> list[str]:
    """
    从 JSONL 文件中提取每个 query_index 的 result_index=1 的 title 列表
    返回 title 字符串列表（已去除 paths. 前缀）
    """
    results = extract_top_results(input_file, print_output=False)
    return [item['title'] for item in results]


if __name__ == "__main__":
    extract_top_results()

