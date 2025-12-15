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

def write_output(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def main():
    jsonl_path = "merged3.jsonl"
    template_path = "testcase_prompt.jinja"
    root_steps = ["1","2","3","4","5"]  # 需要包含的根步骤前缀列表

    print("Loading jsonl...")
    rows = load_jsonl(jsonl_path)

    print("Filtering steps:", root_steps)
    matched_rows = match_steps(rows, root_steps)
    print(f"Matched {len(matched_rows)} jsonl lines")

    print("Loading prompt template...")
    template = load_prompt_template(template_path)

    print("Rendering prompt...")
    final_prompt = build_prompt(template, matched_rows)

    llm = ChatTongyi(model="qwen-max")

    print("Calling LLM...")
    resp = llm.invoke(final_prompt)

    print("LLM Output:")
    print(resp)


    if hasattr(resp, "content"):
        resp_text = resp.content
    else:
        resp_text = str(resp)

    output_path = "llm_output.txt"       # 输出文件路径
    print("Writing LLM output to file:", output_path)
    write_output(output_path, resp_text)


if __name__ == "__main__":
    main()
