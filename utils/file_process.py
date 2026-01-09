import json
import os
from typing import Any, Dict, Optional

def save_as_json(contents: list[str], filename: str):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(contents, f, ensure_ascii=False, indent=2)
        print(f"成功写入{filename}.json文件...")

def read_json(filename: str) -> Any:
    with open(filename, "r", encoding="utf-8") as f:
        print(f"读取{filename}.json中...")
        return json.load(f)

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