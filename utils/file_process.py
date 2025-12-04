import json
from typing import Any

def save_as_json(contents: list[str], filename: str):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(contents, f, ensure_ascii=False, indent=2)
        print(f"成功写入{filename}.json文件...")

def read_json(filename: str) -> Any:
    with open(filename, "r", encoding="utf-8") as f:
        print(f"读取{filename}.json中...")
        return json.load(f)