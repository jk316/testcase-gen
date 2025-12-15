import json
from jinja2 import Template

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


def main():
    jsonl_path = "inputs/merged3.jsonl"
    template_path = "testcase_prompt.jinja"
    root_steps = ["1","2","3"]  # 需要包含的根步骤前缀列表

    rows = load_jsonl(jsonl_path)
    step_map = build_step_map(rows)
    template = load_prompt_template(template_path)

    llm = ChatTongyi(model="qwen-max")

    output_path = "outputs/llm_output_all_steps.jsonl"

    open(output_path, "w", encoding="utf-8").close()

    for root in root_steps:
        subtree_rows = collect_subtree(root, step_map)
        ordered_rows = postorder_sort(subtree_rows)

        for row in ordered_rows:
            step = row["step"]

            prompt = build_prompt(template, [row])
            resp = llm.invoke(prompt)
            resp_text = resp.content if hasattr(resp, "content") else str(resp)

            write_jsonl(output_path, resp_text)


if __name__ == "__main__":
    main()
