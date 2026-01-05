"""
聚合 api_params.jsonl 中的参数，按 api_id 分组
为每个 api_id 生成包含 ALL_INPUT_FIELDS 和 ALL_OUTPUT_FIELDS 的记录
"""
import json
from typing import Dict, List, Any
from collections import defaultdict


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


def aggregate_api_params(input_file: str, output_file: str):
    """
    聚合 API 参数
    
    Args:
        input_file: 输入的 api_params.jsonl 文件路径
        output_file: 输出的聚合结果文件路径
    """
    # 1. 读取所有记录
    print(f"正在读取 {input_file}...")
    all_params = load_jsonl(input_file)
    print(f"共读取 {len(all_params)} 条记录")
    
    # 2. 按 api_id 分组
    api_groups = defaultdict(list)
    for param in all_params:
        api_id = param.get("api_id")
        if api_id:
            api_groups[api_id].append(param)
    
    print(f"找到 {len(api_groups)} 个不同的 api_id")
    
    # 3. 聚合字段
    aggregated_results = []
    for api_id, params in api_groups.items():
        # 收集必填输入字段
        all_input_fields = []
        # 收集所有输出字段
        all_output_fields = []
        
        for param in params:
            direction = param.get("direction", "")
            full_path = param.get("full_path", "")
            required = param.get("required", False)
            
            if direction == "input" and required == True:
                if full_path:
                    all_input_fields.append(full_path)
            elif direction == "output":
                if full_path:
                    all_output_fields.append(full_path)
        
        # 去重并排序（保持一致性）
        all_input_fields = sorted(list(set(all_input_fields)))
        all_output_fields = sorted(list(set(all_output_fields)))
        
        aggregated_results.append({
            "api_id": api_id,
            "ALL_INPUT_FIELDS": all_input_fields,
            "ALL_OUTPUT_FIELDS": all_output_fields
        })
    
    # 4. 按 api_id 排序输出
    aggregated_results.sort(key=lambda x: x["api_id"])
    
    # 5. 保存结果
    print(f"\n正在保存结果到 {output_file}...")
    with open(output_file, "w", encoding="utf-8") as f:
        for result in aggregated_results:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    
    print(f"成功聚合 {len(aggregated_results)} 个 API")
    print(f"结果已保存到 {output_file}")
    
    # 打印一些统计信息
    total_input_fields = sum(len(r["ALL_INPUT_FIELDS"]) for r in aggregated_results)
    total_output_fields = sum(len(r["ALL_OUTPUT_FIELDS"]) for r in aggregated_results)
    print(f"\n统计信息:")
    print(f"  总必填输入字段数: {total_input_fields}")
    print(f"  总输出字段数: {total_output_fields}")


def main():
    input_file = "outputs/api_params.jsonl"
    output_file = "outputs/api_params_aggregated.jsonl"
    aggregate_api_params(input_file, output_file)


if __name__ == "__main__":
    main()

