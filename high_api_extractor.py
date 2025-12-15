import json
import os
from typing import Dict, Any, List, Set


class HierarchicalAPIExtractor:
    def __init__(self, api_file: str, ignore_titles=None):
        self.api_file = api_file
        self.data = self._load_jsonl()
        self.title_map = {item["title"]: item for item in self.data}

        # 忽略标题的关键字（模糊匹配）
        self.ignore_titles = set(ignore_titles or [])

    def _load_jsonl(self) -> List[Dict[str, Any]]:
        items = []
        with open(self.api_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
        return items

    def parse_ref(self, ref: str) -> str:
        cleaned = ref.lstrip("#/")
        cleaned = cleaned.replace("/", ".")
        return cleaned

    def find_json_by_title_contains(self, keyword: str) -> Dict[str, Any]:
        for item in self.data:
            if keyword in item["title"]:
                return item
        raise ValueError(f"JSON with title containing '{keyword}' not found.")

    def extract_recursive(
        self,
        json_item: Dict[str, Any],
        step: str,
        result_lines: List[Dict[str, Any]],
        visited: Set[str],
        ref_from: str = None
    ):
        title = json_item["title"]

        # 如果标题匹配 ignore_titles 则直接跳过（既不输出，也不递归）
        for ignore_key in self.ignore_titles:
            if ignore_key in title:
                return

        # 解析内容并映射为过滤后的结构
        raw_content = json.loads(json_item["content"])
        filtered = self.filter_content(raw_content)

        # 记录当前节点
        line_obj = {
            "step": step,
            "title": title,
            "content": filtered
        }
        if ref_from:
            line_obj["ref_from"] = ref_from
        result_lines.append(line_obj)

        # 避免环引用死循环
        if title in visited:
            return
        visited.add(title)

        # 递归子引用
        sub_refs = self._collect_refs(raw_content)

        child_idx = 1
        for ref in sub_refs:
            ref_title = self.parse_ref(ref)

            try:
                sub_json = self.find_json_by_title_contains(ref_title)
            except:
                continue

            # 记录递归前输出节点数
            before = len(result_lines)

            # 递归
            self.extract_recursive(
                sub_json,
                f"{step}.{child_idx}",
                result_lines,
                visited,
                ref_from=ref
            )

            # 若递归产生了新节点，说明有效，递增 child_idx
            if len(result_lines) > before:
                child_idx += 1

    def filter_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        if "post" in content:
            post = content["post"]
            return {
                "summary": post.get("summary"),
                "parameters": post.get("parameters", []),
                "responses": post.get("responses", {})
            }

        if "get" in content:
            get_ = content["get"]
            return {
                "summary": get_.get("summary"),
                "parameters": get_.get("parameters", []),
                "responses": get_.get("responses", {})
            }

        if "properties" in content:
            return {
                "summary": None,
                "parameters": [{
                    "name": name,
                    **value
                } for name, value in content.get("properties", {}).items()],
                "responses": {}
            }

        return {"summary": None, "parameters": [], "responses": {}}

    def _collect_refs(self, node: Any) -> List[str]:
        refs = []

        if isinstance(node, dict):
            for k, v in node.items():
                if k == "$ref" and isinstance(v, str):
                    refs.append(v)
                else:
                    refs.extend(self._collect_refs(v))

        elif isinstance(node, list):
            for item in node:
                refs.extend(self._collect_refs(item))

        return refs

    def extract(self, api_path: str, root_step: int = 1):
        root_json = self.find_json_by_title_contains(api_path)
        result_lines = []
        visited = set()

        self.extract_recursive(
            root_json,
            step=str(root_step),
            result_lines=result_lines,
            visited=visited
        )
        return result_lines

    def save_jsonl(self, result_lines: List[Dict[str, Any]], out_file: str):
        with open(out_file, "w", encoding="utf-8") as f:
            for obj in result_lines:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def extract_io_params(self, result_lines):
        inputs = set()
        outputs = set()

        for line in result_lines:
            step = line["step"]
            params = line["content"].get("parameters", [])

            if step == "1":
                for p in params:
                    if "name" in p:
                        inputs.add(p["name"])
            else:
                for p in params:
                    if "name" in p:
                        outputs.add(p["name"])

        return sorted(inputs), sorted(outputs)

    def extract_multiple(self, api_paths: list) -> list:
        all_lines = []
        root_step = 1

        for api in api_paths:
            single = self.extract(api, root_step=root_step)
            all_lines.extend(single)
            root_step += 1

        return all_lines

    def save_list(self, items, filename):
        with open(filename, "w", encoding="utf-8") as f:
            for item in items:
                f.write(item + "\n")


if __name__ == "__main__":
    
    ignore_titles = {
        "definitions.testcase.AppReplay",
        "definitions.testcase.AppSimulator",
        "definitions.testcase.Criteria",
        "definitions.testcase.IPSecSimulator",
        "definitions.testcase.Layer2Replay",
        "definitions.testcase.Malware",
        "definitions.testcase.ItfPing",
        "definitions.testcase.Security",
        "definitions.testcase.SessionSender",
        "definitions.testcase.XAppSimulator"
    }

    extractor = HierarchicalAPIExtractor("inputs/xrt_openapi.jsonl", ignore_titles=ignore_titles)

    apis = [
        "/v1/cl/user/login",
        "/v1/cl/testcase/create",
        "/v1/cl/network/list",
        "/v1/cl/testcase/save",
        "/v1/cl/testcase/run"
    ]

    result = extractor.extract_multiple(apis)
    extractor.save_jsonl(result, "merged3.jsonl")

    # New: extract input & output lists
    inputs, outputs = extractor.extract_io_params(result)

    extractor.save_list(inputs, "inputs.txt")
    extractor.save_list(outputs, "outputs.txt")

    print("Done. Saved hierarchical JSONL, inputs.txt, outputs.txt.")