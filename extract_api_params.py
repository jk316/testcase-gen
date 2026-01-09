"""
从 intent_search_results.jsonl 读取 result_index=1 的 title，
然后在 xrt_openapi.jsonl 中查找并解析对应 API 的所有参数
"""
import json
from typing import Dict, List, Any, Set, Optional


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    """加载 JSONL 文件"""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_api_data(path: str = "inputs/xrt_openapi.jsonl") -> Dict[str, Dict[str, Any]]:
    """
    加载原始 API 数据
    返回 title 到完整 item 的映射（包括 id, title, content）
    """
    api_data = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            title = item.get("title", "")
            content_str = item.get("content", "{}")
            try:
                content = json.loads(content_str)
                api_data[title] = {
                    "id": item.get("id"),
                    "title": title,
                    "content": content
                }
            except json.JSONDecodeError:
                continue
    return api_data


def parse_ref(ref: str) -> str:
    """
    解析 $ref，转换为 title 格式
    例如: "#/definitions/alps.UserLoginRequest" -> "definitions.alps.UserLoginRequest"
    """
    if ref.startswith("#/"):
        return ref[2:].replace("/", ".")
    return ref


# 需要忽略的 title 列表（参考 high_api_extractor.py）
IGNORE_TITLES = {
    "definitions.testcase.AppReplay",
    "definitions.api.AppReplay",
    "definitions.testcase.AppSimulator",    
    "definitions.api.AppSimulator",
    "definitions.testcase.Criteria",
    "definitions.api.Criteria",
    "definitions.testcase.IPSecSimulator",
    "definitions.api.IPSecSimulator",
    "definitions.testcase.Layer2Replay",
    "definitions.api.Layer2Replay",
    "definitions.testcase.Malware",
    "definitions.api.Malware",
    "definitions.testcase.ItfPing",
    "definitions.api.ItfPing",
    "definitions.testcase.Security",
    "definitions.api.Security",
    "definitions.testcase.SessionSender",
    "definitions.api.SessionSender",
    "definitions.testcase.XAppSimulator",
    "definitions.api.XAppSimulator"
}


def extract_parameters_from_definition(
    definition_title: str,
    api_data: Dict[str, Dict[str, Any]],
    visited: Set[str],
    parent_path: str = "",
    direction: str = "input",
    ignore_titles: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    从对象定义中递归提取参数，完全展开所有 $ref 引用
    
    Args:
        definition_title: 对象定义的 title（如 "definitions.alps.UserLoginRequest"）
        api_data: API 数据映射
        visited: 已访问的定义集合（避免循环引用）
        parent_path: 父路径
        direction: "input" 或 "output"
        ignore_titles: 需要忽略的 title 集合，如果 title 在其中则直接跳过
    """
    if definition_title in visited:
        return []
    
    if definition_title not in api_data:
        return []
    
    # 检查是否在 ignore_titles 中
    ignore_set = ignore_titles if ignore_titles is not None else IGNORE_TITLES
    if definition_title in ignore_set:
        return []
    
    visited.add(definition_title)
    definition_item = api_data[definition_title]
    content = definition_item.get("content", {})
    
    # 获取 required 数组
    required_fields = set(content.get("required", []))
    
    # 获取 properties
    properties = content.get("properties", {})
    
    results = []
    
    for prop_name, prop_value in properties.items():
        if not prop_name:
            continue
        
        # 构建 full_path
        if parent_path:
            full_path = f"{parent_path}.{prop_name}"
        else:
            full_path = prop_name
        
        # 确定 location（对象定义中的字段通常在 body 中）
        location = "body"
        
        # 确定 required
        required = prop_name in required_fields
        
        # 获取描述
        desc = prop_value.get("description", "")
        
        # 获取类型
        prop_type = prop_value.get("type", "string")
        
        # 处理数组类型
        if prop_type == "array":
            items = prop_value.get("items", {})
            if "$ref" in items:
                # 先添加数组元素类型本身的记录
                results.append({
                    "name": prop_name,
                    "full_path": full_path,
                    "location": location,
                    "type": "array[object]",  # 数组元素是对象类型
                    "required": required,  # 数组本身的 required
                    "desc": desc
                })
                # 然后展开数组元素类型的字段
                ref = items["$ref"]
                ref_title = parse_ref(ref)
                # 检查 ref_title 是否在 ignore_titles 中
                ignore_set = ignore_titles if ignore_titles is not None else IGNORE_TITLES
                if ref_title not in ignore_set:
                    nested_params = extract_parameters_from_definition(
                        ref_title, api_data, visited.copy(), full_path, direction, ignore_titles
                    )
                    results.extend(nested_params)
            else:
                # 数组元素是基本类型
                items_type = items.get("type", "object")
                results.append({
                    "name": prop_name,
                    "full_path": full_path,
                    "location": location,
                    "type": f"array[{items_type}]",
                    "required": required,
                    "desc": desc
                })
        # 处理 $ref 引用
        elif "$ref" in prop_value:
            # 先添加中间对象本身的记录
            results.append({
                "name": prop_name,
                "full_path": full_path,
                "location": location,
                "type": "object",
                "required": required,  # 中间对象本身的 required
                "desc": desc
            })
            # 然后递归展开该对象的字段
            ref = prop_value["$ref"]
            ref_title = parse_ref(ref)
            # 检查 ref_title 是否在 ignore_titles 中
            ignore_set = ignore_titles if ignore_titles is not None else IGNORE_TITLES
            if ref_title not in ignore_set:
                nested_params = extract_parameters_from_definition(
                    ref_title, api_data, visited.copy(), full_path, direction, ignore_titles
                )
                results.extend(nested_params)
        else:
            # 基本类型
            results.append({
                "name": prop_name,
                "full_path": full_path,
                "location": location,
                "type": prop_type,
                "required": required,
                "desc": desc
            })
    
    return results


def extract_api_params_from_title(
    api_title: str,
    api_data: Dict[str, Dict[str, Any]],
    ignore_titles: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    从 API title 提取所有参数
    
    Args:
        api_title: API 的 title（如 "paths./v1/cl/user/login"）
        api_data: API 数据映射
    """
    if api_title not in api_data:
        return []
    
    api_item = api_data[api_title]
    content = api_item.get("content", {})
    
    # 规范化 API 路径
    api_path = api_title.replace("paths.", "")
    
    # 提取 HTTP 方法
    http_method = "POST"  # 默认
    operation = None
    for method in ["get", "post", "put", "delete", "patch"]:
        if method in content:
            http_method = method.upper()
            operation = content[method]
            break
    
    if not operation:
        return []
    
    api_id = f"{http_method} {api_path}"
    results = []
    
    # 提取输入参数
    parameters = operation.get("parameters", [])
    for param in parameters:
        param_name = param.get("name", "")
        param_in = param.get("in", "query")
        
        if param_in == "body":
            # body 参数，需要展开 schema
            schema = param.get("schema", {})
            if "$ref" in schema:
                ref = schema["$ref"]
                ref_title = parse_ref(ref)
                ignore_set = ignore_titles if ignore_titles is not None else IGNORE_TITLES
                if ref_title not in ignore_set:
                    nested_params = extract_parameters_from_definition(
                        ref_title, api_data, set(), "request.body", "input", ignore_titles
                    )
                    for p in nested_params:
                        results.append({
                            "api_id": api_id,
                            "direction": "input",
                            **p
                        })
            else:
                # 直接 body 参数
                results.append({
                    "api_id": api_id,
                    "direction": "input",
                    "name": param_name,
                    "full_path": f"request.body.{param_name}",
                    "location": "body",
                    "type": schema.get("type", "object"),
                    "required": param.get("required", False),
                    "desc": param.get("description", "")
                })
        else:
            # query, path, header 参数
            results.append({
                "api_id": api_id,
                "direction": "input",
                "name": param_name,
                "full_path": f"request.{param_in}.{param_name}",
                "location": param_in,
                "type": param.get("type", "string"),
                "required": param.get("required", True),
                "desc": param.get("description", "")
            })
    
    # 提取输出参数
    responses = operation.get("responses", {})
    if "200" in responses:
        response_200 = responses["200"]
        schema = response_200.get("schema", {})
        
        if "$ref" in schema:
            ref = schema["$ref"]
            ref_title = parse_ref(ref)
            ignore_set = ignore_titles if ignore_titles is not None else IGNORE_TITLES
            if ref_title not in ignore_set:
                nested_params = extract_parameters_from_definition(
                    ref_title, api_data, set(), "response", "output", ignore_titles
                )
                for p in nested_params:
                    results.append({
                        "api_id": api_id,
                        "direction": "output",
                        **p
                    })
        else:
            # 直接响应
            results.append({
                "api_id": api_id,
                "direction": "output",
                "name": "body",
                "full_path": "response.body",
                "location": "body",
                "type": schema.get("type", "object"),
                "required": True,
                "desc": response_200.get("description", "")
            })
    
    return results


def main():
    intent_results_file = "outputs/intent_search_results.jsonl"
    api_data_file = "inputs/xrt_openapi.jsonl"
    output_file = "outputs/api_params.jsonl"
    
    # 1. 从 intent_search_results.jsonl 读取 result_index=1 的 title
    print(f"正在读取 {intent_results_file}...")
    intent_results = load_jsonl(intent_results_file)
    top_titles = []
    for item in intent_results:
        if item.get("result_index") == 1:
            title = item.get("title", "")
            if title:
                top_titles.append(title)
    
    print(f"找到 {len(top_titles)} 个 API title (result_index=1)")
    for title in top_titles:
        print(f"  - {title}")
    
    # 2. 加载原始 API 数据
    print(f"\n正在加载原始 API 数据 {api_data_file}...")
    api_data = load_api_data(api_data_file)
    print(f"已加载 {len(api_data)} 个 API 定义")
    
    # 3. 解析每个 API 的参数
    print("\n正在提取 API 参数...")
    all_params = []
    for title in top_titles:
        params = extract_api_params_from_title(title, api_data)
        all_params.extend(params)
        print(f"  {title}: 提取了 {len(params)} 个参数")
    
    print(f"\n总共提取了 {len(all_params)} 个参数")
    
    # 4. 保存结果
    with open(output_file, "w", encoding="utf-8") as f:
        for param in all_params:
            f.write(json.dumps(param, ensure_ascii=False) + "\n")
    
    print(f"结果已保存到 {output_file}")


if __name__ == "__main__":
    main()
