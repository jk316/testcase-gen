"""端到端生成入口：测试意图 → 可执行 Python 脚本。

用法::

    python -m codegen.generate "测试 udp flood 和 http get flood 混合攻击，攻击总带宽1Gbps，时长200秒"
    python -m codegen.generate              # 读 inputs/intent.txt 逐条生成
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any, List, Optional

from codegen.ir import PlanStep, TestRequirement
from codegen.llm import get_llm
from codegen.metrics import GenerationMetrics, summarize
from codegen.parser import parse_intent
from codegen.planner import plan_test
from codegen.synthesizer import synthesize


def generate_from_intent(
    intent_text: str, llm: Optional[Any] = None
) -> tuple[Optional[TestRequirement], List[PlanStep], str, GenerationMetrics]:
    """意图 → (需求, 计划, 生成代码, 统计)。

    失败时需求/代码可能为 ``None`` / 空，错误记录在 ``metrics.error``。
    """
    llm = llm or get_llm()
    m = GenerationMetrics(intent=intent_text)
    t_start = time.perf_counter()

    # ① 需求解析
    requirement: Optional[TestRequirement] = None
    t = time.perf_counter()
    try:
        requirement, usage = parse_intent(intent_text, llm)
        m.parse_ok = True
        m.llm_calls += 1
        m.prompt_tokens += usage.prompt_tokens
        m.completion_tokens += usage.completion_tokens
        m.n_attacks = len(requirement.attacks)
        m.n_businesses = len(requirement.businesses)
    except Exception as e:
        m.error = f"解析失败: {e}"
    finally:
        m.duration_parse_ms = (time.perf_counter() - t) * 1000

    # ② 意图编排
    plan: List[PlanStep] = []
    if requirement is not None and m.error is None:
        t = time.perf_counter()
        try:
            plan, usage, retries, first_try = plan_test(requirement, llm)
            m.plan_ok = True
            m.plan_valid_first_try = first_try
            m.plan_retries = retries
            m.llm_calls += retries + 1
            m.prompt_tokens += usage.prompt_tokens
            m.completion_tokens += usage.completion_tokens
        except Exception as e:
            m.error = f"编排失败: {e}"
        finally:
            m.duration_plan_ms = (time.perf_counter() - t) * 1000

    # ③ 代码合成（确定性，无 LLM）
    code = ""
    if requirement is not None and m.error is None:
        t = time.perf_counter()
        try:
            code = synthesize(requirement, plan)
            m.synthesize_ok = True
        except Exception as e:
            m.error = f"合成失败: {e}"
        finally:
            m.duration_synthesize_ms = (time.perf_counter() - t) * 1000

    m.duration_total_ms = (time.perf_counter() - t_start) * 1000
    return requirement, plan, code, m


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

    all_metrics: List[GenerationMetrics] = []
    for idx, intent in enumerate(intents):
        print(f"\n=== 意图 {idx + 1}: {intent} ===")
        req, plan, code, m = generate_from_intent(intent)
        all_metrics.append(m)

        if m.error:
            print(f"生成失败: {m.error}")
            print(f"耗时 {m.duration_total_ms / 1000:.2f}s | {m.total_tokens} tokens")
            continue

        print(f"需求: {_format_requirement(req)}")
        print(f"计划: {' -> '.join(s.capability for s in plan)}")
        os.makedirs("outputs", exist_ok=True)
        out_path = f"outputs/generated_testcase_{idx + 1}.py"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"已生成: {out_path}")
        print(
            f"耗时 {m.duration_total_ms / 1000:.2f}s | {m.total_tokens} tokens | "
            f"LLM 调用 {m.llm_calls} 次 | 重试 {m.plan_retries} 次"
        )
        print("-" * 60)
        print(code)

    print("\n" + summarize(all_metrics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
