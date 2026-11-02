"""端到端生成入口：测试意图 → 可执行 Python 脚本。

用法::

    python -m codegen.generate "测试 udp flood 和 http get flood 混合攻击，攻击总带宽1Gbps，时长200秒"
    python -m codegen.generate              # 读 inputs/intent.txt 逐条生成
"""
from __future__ import annotations

import sys
from typing import Any, List, Optional

from codegen.ir import PlanStep, TestRequirement
from codegen.llm import get_llm
from codegen.parser import parse_intent
from codegen.planner import plan_test
from codegen.synthesizer import synthesize


def generate_from_intent(
    intent_text: str, llm: Optional[Any] = None
) -> tuple[TestRequirement, List[PlanStep], str]:
    """意图 → (需求, 计划, 生成代码)。"""
    llm = llm or get_llm()
    requirement = parse_intent(intent_text, llm)
    plan = plan_test(requirement, llm)
    code = synthesize(requirement, plan)
    return requirement, plan, code


def _format_requirement(req: TestRequirement) -> str:
    attacks = ", ".join(f"{a.type}={a.bandwidth_mbps}Mbps" for a in req.attacks)
    businesses = ", ".join(f"{b.type}={b.bandwidth_mbps}Mbps" for b in req.businesses)
    return f"name={req.name!r} duration={req.duration_sec}s attacks=[{attacks}] businesses=[{businesses}]"


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and not argv[0].endswith(".txt"):
        intents = [" ".join(argv)]
    else:
        intent_file = argv[0] if argv else "inputs/intent.txt"
        with open(intent_file, encoding="utf-8") as f:
            intents = [line.strip() for line in f if line.strip()]

    for idx, intent in enumerate(intents):
        print(f"\n=== 意图 {idx + 1}: {intent} ===")
        req, plan, code = generate_from_intent(intent)
        print(f"需求: {_format_requirement(req)}")
        print(f"计划: {' -> '.join(s.capability for s in plan)}")
        out_path = f"outputs/generated_testcase_{idx + 1}.py"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"已生成: {out_path}")
        print("-" * 60)
        print(code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
