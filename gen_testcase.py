import asyncio
import json
from jinja2 import Template
import time

from langchain_community.chat_models import ChatTongyi
from dotenv import load_dotenv

load_dotenv()


def load_jsonl(path):
    """Load jsonl file into Python list."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def match_steps(rows, root_steps):
    """
    Get all jsonl rows whose step starts with any prefix in root_steps.
    """
    results = []
    for row in rows:
        step = row.get("step", "")
        for rs in root_steps:
            if step == rs or step.startswith(rs + "."):
                results.append(row)
                break
    return results


def load_prompt_template(template_path):
    """Load prompt.jinja and return Template object."""
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()
    return Template(content)


def build_prompt(template: Template, rows):
    """Render final prompt using Jinja2 template."""
    jsonl_text = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    return template.render(jsonl_data=jsonl_text)

def write_output(path, content, append=False):
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as f:
        f.write(content)
        f.write("\n")  # 保证不同 step 之间有换行

def write_jsonl(path, content):
    """
    content 必须是一个合法 JSON 字符串（object 或 array）
    """
    with open(path, "a", encoding="utf-8") as f:
        f.write(content.strip())
        f.write("\n")

def build_step_map(rows):
    return {row["step"]: row for row in rows}

def collect_subtree(step, step_map):
    """
    Collect all rows whose step == step or starts with step + '.'
    """
    result = []
    prefix = step + "."
    for s, row in step_map.items():
        if s == step or s.startswith(prefix):
            result.append(row)
    return result

def postorder_sort(rows):
    """
    Sort rows by step depth descending (post-order)
    """
    return sorted(
        rows,
        key=lambda r: len(r["step"].split(".")),
        reverse=True
    )


async def main():
    jsonl_path = "outputs/merged4.jsonl"
    template_path = "prompts/testcase_prompt.jinja"
    root_steps = ["1","2","3"]  # 需要包含的根步骤前缀列表

    print("=" * 80)
    print("开始生成测试用例")
    print("=" * 80)
    print(f"输入文件: {jsonl_path}")
    print(f"模板文件: {template_path}")
    print(f"根步骤: {root_steps}")
    print("-" * 80)
    
    start_time = time.time()
    
    print("正在加载 JSONL 文件...")
    rows = load_jsonl(jsonl_path)
    print(f"✓ 已加载 {len(rows)} 行数据")
    
    step_map = build_step_map(rows)
    template = load_prompt_template(template_path)
    print("✓ 已加载模板文件")

    llm = ChatTongyi(model="qwen-max")
    print("✓ LLM 模型已初始化")
    print("-" * 80)

    output_path = "outputs/llm_output_all_steps_1231.jsonl"
    open(output_path, "w", encoding="utf-8").close()
    print(f"输出文件: {output_path}")
    print("=" * 80)

    # 统计总行数
    total_rows = 0
    for root in root_steps:
        subtree_rows = collect_subtree(root, step_map)
        total_rows += len(subtree_rows)
    
    print(f"\n总共需要处理 {total_rows} 行数据")
    print("=" * 80)
    
    processed_count = 0
    
    for root_idx, root in enumerate(root_steps, 1):
        print(f"\n[Root Step {root_idx}/{len(root_steps)}] 处理根步骤: {root}")
        subtree_rows = collect_subtree(root, step_map)
        ordered_rows = postorder_sort(subtree_rows)
        
        print(f"  找到 {len(ordered_rows)} 行需要处理")
        print("-" * 80)

        for row_idx, row in enumerate(ordered_rows, 1):
            step = row["step"]
            processed_count += 1
            
            print(f"  [{processed_count}/{total_rows}] 处理步骤: {step} (Root {root}, 第 {row_idx}/{len(ordered_rows)} 行)")
            
            step_start_time = time.time()
            
            prompt = build_prompt(template, [row])
            resp = await llm.ainvoke(prompt)
            resp_text = resp.content if hasattr(resp, "content") else str(resp)

            write_jsonl(output_path, resp_text)
            
            step_elapsed = time.time() - step_start_time
            progress_pct = (processed_count / total_rows) * 100
            print(f"    ✓ 完成 (耗时: {step_elapsed:.2f}秒, 总进度: {progress_pct:.1f}%)")
        
        print(f"\n✓ Root Step {root} 处理完成")
        print("-" * 80)
    
    total_elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print("处理完成!")
    print(f"总共处理: {processed_count} 行")
    print(f"总耗时: {total_elapsed:.2f} 秒 ({total_elapsed/60:.2f} 分钟)")
    print(f"平均每行: {total_elapsed/processed_count:.2f} 秒")
    print(f"结果已保存到: {output_path}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
