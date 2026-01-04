"""
从 merged4.jsonl 中提取每个 API 的参数，整理成指定格式
"""
import json
from typing import Dict, List, Any


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


def build_step_map(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """构建 step 到 row 的映射"""
    return {row["step"]: row for row in rows}




def normalize_api_path(title: str) -> str:
    """规范化 API 路径"""
    if title.startswith("paths."):
        return title.replace("paths.", "")
    return title


def extract_parameters_recursive(
    step: str,
    step_map: Dict[str, Dict[str, Any]],
    visited: set,
    parent_path: str = "",
    direction: str = "input"
) -> List[Dict[str, Any]]:
    """
    递归提取参数
    
    Args:
        step: 当前步骤
        step_map: step 到 row 的映射
        visited: 已访问的 step 集合（避免循环引用）
        parent_path: 父路径（如 "body", "result"）
        direction: "input" 或 "output"
    """
    if step in visited:
        return []
    
    if step not in step_map:
        return []
    
    visited.add(step)
    row = step_map[step]
    content = row.get("content", {})
    parameters = content.get("parameters", [])
    
    results = []
    
    for param in parameters:
        param_name = param.get("name", "")
        if not param_name:
            continue
        
        # 构建 full_path
        if parent_path:
            full_path = f"{parent_path}.{param_name}"
        else:
            full_path = param_name
        
        # 确定 location
        location = param.get("in", "body")
        if direction == "output":
            location = "body"  # 输出参数通常在 body 中
        
        # 确定 type
        param_type = param.get("type", "string")
        if "$ref" in param:
            param_type = "object"  # 引用类型视为 object
        
        # 确定 required
        required = param.get("required", False)
        
        # 获取描述
        desc = param.get("description", "")
        
        # 如果是引用类型，需要递归处理
        if "$ref" in param:
            ref = param["$ref"]
            # 查找对应的 step（通过 ref_from 字段）
            ref_step = None
            for s, r in step_map.items():
                if r.get("ref_from") == ref:
                    ref_step = s
                    break
            
            if ref_step:
                # 递归提取嵌套参数
                nested_params = extract_parameters_recursive(
                    ref_step, step_map, visited.copy(), full_path, direction
                )
                results.extend(nested_params)
        else:
            # 普通参数
            results.append({
                "name": param_name,
                "full_path": full_path,
                "location": location,
                "type": param_type,
                "required": required,
                "desc": desc
            })
    
    return results


def extract_api_params(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    提取所有 API 的参数
    """
    step_map = build_step_map(rows)
    results = []
    
    # 找到所有 API 路径（step 为单个数字，title 以 paths. 开头）
    api_rows = []
    for row in rows:
        step = row.get("step", "")
        title = row.get("title", "")
        
        # 判断是否为 API 路径行（step 是单个数字，title 以 paths. 开头）
        if step.isdigit() and title.startswith("paths."):
            api_rows.append(row)
    
    print(f"找到 {len(api_rows)} 个 API")
    
    for api_row in api_rows:
        step = api_row["step"]
        title = api_row["title"]
        content = api_row.get("content", {})
        
        # 规范化 API 路径
        api_path = normalize_api_path(title)
        
        # 提取 HTTP 方法（简化处理，实际应该从 content 中获取）
        http_method = "POST"  # 默认
        if "get" in content:
            http_method = "GET"
        elif "post" in content:
            http_method = "POST"
        elif "put" in content:
            http_method = "PUT"
        elif "delete" in content:
            http_method = "DELETE"
        
        api_id = f"{http_method} {api_path}"
        
        # 提取输入参数
        input_params = []
        parameters = content.get("parameters", [])
        
        for param in parameters:
            param_name = param.get("name", "")
            param_in = param.get("in", "query")
            
            if param_in == "body":
                # body 参数，需要递归提取
                schema = param.get("schema", {})
                if "$ref" in schema:
                    ref = schema["$ref"]
                    # 查找对应的 step
                    ref_step = None
                    for s, r in step_map.items():
                        if r.get("ref_from") == ref:
                            ref_step = s
                            break
                    
                    if ref_step:
                        nested = extract_parameters_recursive(
                            ref_step, step_map, set(), "request.body", "input"
                        )
                        input_params.extend(nested)
                else:
                    # 直接 body 参数
                    input_params.append({
                        "name": param_name,
                        "full_path": f"request.body.{param_name}",
                        "location": "body",
                        "type": param.get("type", "object"),
                        "required": param.get("required", False),
                        "desc": param.get("description", "")
                    })
            else:
                # query, path, header 参数
                input_params.append({
                    "name": param_name,
                    "full_path": f"request.{param_in}.{param_name}",
                    "location": param_in,
                    "type": param.get("type", "string"),
                    "required": param.get("required", False),
                    "desc": param.get("description", "")
                })
        
        # 提取输出参数
        output_params = []
        responses = content.get("responses", {})
        
        if "200" in responses:
            response_200 = responses["200"]
            schema = response_200.get("schema", {})
            
            if "$ref" in schema:
                ref = schema["$ref"]
                # 查找对应的 step
                ref_step = None
                for s, r in step_map.items():
                    if r.get("ref_from") == ref:
                        ref_step = s
                        break
                
                if ref_step:
                    nested = extract_parameters_recursive(
                        ref_step, step_map, set(), "response.body", "output"
                    )
                    output_params.extend(nested)
            else:
                # 直接响应
                output_params.append({
                    "name": "body",
                    "full_path": "response.body",
                    "location": "body",
                    "type": schema.get("type", "object"),
                    "required": True,
                    "desc": response_200.get("description", "")
                })
        
        # 生成结果
        for param in input_params:
            results.append({
                "api_id": api_id,
                "direction": "input",
                **param
            })
        
        for param in output_params:
            results.append({
                "api_id": api_id,
                "direction": "output",
                **param
            })
    
    return results


def main():
    input_file = "outputs/merged4.jsonl"
    output_file = "outputs/api_params.jsonl"
    
    print(f"正在读取 {input_file}...")
    rows = load_jsonl(input_file)
    print(f"已加载 {len(rows)} 行数据")
    
    print("正在提取 API 参数...")
    params = extract_api_params(rows)
    print(f"提取了 {len(params)} 个参数")
    
    # 保存结果
    with open(output_file, "w", encoding="utf-8") as f:
        for param in params:
            f.write(json.dumps(param, ensure_ascii=False) + "\n")
    
    print(f"结果已保存到 {output_file}")


if __name__ == "__main__":
    main()

