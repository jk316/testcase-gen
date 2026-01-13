import json
import os
from typing import Any, Dict, Optional, List


def load_jinja_template(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def load_api_jsonl(path):
    apis = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            apis.append(json.loads(line))
    return apis

def write_testcase_jsonl(testcase: Optional[Dict[str, Any]], output_path: str, append: bool = True):
    """
    将生成的 testcase 写入到 jsonl 文件中
    
    Args:
        testcase: 要写入的 testcase 字典，如果为 None 则跳过
        output_path: 输出文件路径
        append: 是否追加模式（默认 True），如果为 False 则覆盖文件
    """
    if testcase is None:
        return
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # 写入文件
    mode = "a" if append else "w"
    with open(output_path, mode, encoding="utf-8") as f:
        json_str = json.dumps(testcase, ensure_ascii=False)
        f.write(json_str)
        f.write("\n")


def load_text_file(file_path: str, strip: bool = True) -> Optional[str]:
    """
    读取文本文件内容
    
    Args:
        file_path: 文件路径
        strip: 是否去除首尾空白字符（默认 True）
        
    Returns:
        文件内容字符串，如果文件不存在则返回 None
    """
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            return content.strip() if strip else content
    else:
        return None


def save_json_file(data: Any, file_path: str, indent: int = 2, ensure_ascii: bool = False) -> None:
    """
    保存 JSON 数据到文件
    
    Args:
        data: 要保存的 JSON 可序列化数据（字典、列表等）
        file_path: 输出文件路径
        indent: JSON 缩进空格数（默认 2）
        ensure_ascii: 是否确保 ASCII 编码（默认 False，允许非 ASCII 字符）
    """
    # 确保输出目录存在
    output_dir = os.path.dirname(file_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # 保存 JSON 文件
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)