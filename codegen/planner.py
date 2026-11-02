"""意图理解：把 TestRequirement 编排为 TestPlan，并做依赖闭环校验。

编排交给 LLM，校验交给确定性代码；校验失败时把错误反馈回 LLM 重试。
"""
from __future__ import annotations

import json
from typing import Any, List, Optional

from codegen.ir import PlanStep, Ref, TestRequirement, validate_plan
from codegen.llm import ask_llm, extract_json, get_llm
from examples.sdk.capabilities import CAPABILITIES

_PLAN_PROMPT = """你是测试计划编排器。根据结构化需求与可用能力，编排一份测试计划。

可用能力（name: 描述 | 输入: [...] | 输出: [...]）：
{capabilities}

测试需求：
{requirement}

输出 JSON 数组，每步格式：
{{"step_id": "唯一id", "capability": "能力名", "inputs": {{"参数名": 值}}, "outputs": ["产出字段"]}}

参数值规则：
- 若参数来源于前面某步的产出，用 {{"ref": "前一步的step_id", "field": "字段名"}} 表示。
- 否则用字面值（字符串/整数）。

编排要求：
- 第一步必须是 login，最后一步必须是 logout。
- 每个攻击类型各调用一次 ensure_attack_profile（profile_name 用攻击类型名）。
- 每个业务类型各调用一次 ensure_load_profile。
- 依次 reserve_port → create_testcase → build_testcase_info → save_testcase → run_testcase → get_stats_overview。
- build_testcase_info 需要 testcase_id、testcase_name、profile_id、profile_name；混合攻击时把多个 profile 都传入。
- 只使用上面列出的能力。
- 只输出 JSON 数组。"""


def _format_capabilities() -> str:
    lines = []
    for cap in CAPABILITIES.values():
        ins = ", ".join(cap.input_fields) or "-"
        outs = ", ".join(cap.output_fields) or "-"
        lines.append(f"- {cap.name}: {cap.description} | 输入: [{ins}] | 输出: [{outs}]")
    return "\n".join(lines)


def _build_plan(data: Any) -> List[PlanStep]:
    steps: List[PlanStep] = []
    for item in data:
        inputs: dict[str, Any] = {}
        for name, val in (item.get("inputs") or {}).items():
            if isinstance(val, dict) and "ref" in val:
                inputs[name] = Ref(step=val["ref"], field=val["field"])
            else:
                inputs[name] = val
        steps.append(
            PlanStep(
                step_id=item["step_id"],
                capability=item["capability"],
                inputs=inputs,
                outputs=list(item.get("outputs") or []),
            )
        )
    return steps


def plan_test(
    requirement: TestRequirement,
    llm: Optional[Any] = None,
    max_retries: int = 3,
) -> List[PlanStep]:
    """编排 TestPlan，校验失败时回炉重试。"""
    llm = llm or get_llm()
    prompt = _PLAN_PROMPT.format(
        capabilities=_format_capabilities(),
        requirement=json.dumps(
            {
                "name": requirement.name,
                "duration_sec": requirement.duration_sec,
                "attacks": [
                    {"type": a.type, "bandwidth_mbps": a.bandwidth_mbps, "target": a.target}
                    for a in requirement.attacks
                ],
                "businesses": [
                    {"type": b.type, "bandwidth_mbps": b.bandwidth_mbps}
                    for b in requirement.businesses
                ],
            },
            ensure_ascii=False,
        ),
    )

    last_errors: List[str] = []
    for _ in range(max_retries):
        raw = ask_llm(llm, prompt)
        plan = _build_plan(extract_json(raw))
        last_errors = validate_plan(plan, CAPABILITIES)
        if not last_errors:
            return plan
        prompt = _PLAN_PROMPT.format(
            capabilities=_format_capabilities(),
            requirement=json.dumps(
                {
                    "name": requirement.name,
                    "duration_sec": requirement.duration_sec,
                    "attacks": [
                        {"type": a.type, "bandwidth_mbps": a.bandwidth_mbps, "target": a.target}
                        for a in requirement.attacks
                    ],
                    "businesses": [
                        {"type": b.type, "bandwidth_mbps": b.bandwidth_mbps}
                        for b in requirement.businesses
                    ],
                },
                ensure_ascii=False,
            ),
        ) + "\n\n上次生成的计划校验失败，错误如下（请修正后重新输出 JSON 数组）：\n" + "\n".join(
            f"- {e}" for e in last_errors
        )

    raise ValueError(f"测试计划校验失败: {last_errors}")


__all__ = ["plan_test"]
