"""代码合成：把 TestPlan 渲染为可执行 Python 脚本。

变量约定：
- 步骤 X 的原始 SDK 返回值赋给 ``_r_X``；
- 步骤 X 的输出字段 F 赋给 ``v_X_F``；
- ``Ref(step, field)`` 解析为 ``v_step_field``。

``build_testcase_info`` 的 attacks/businesses 从前序
``ensure_attack_profile`` / ``ensure_load_profile`` 步骤自动收集（fan-in）。
"""
from __future__ import annotations

from typing import Any, List

from jinja2 import Template

from codegen.ir import PlanStep, Ref, TestRequirement
from examples.sdk.capabilities import CAPABILITIES

_HEADER = '''from examples.sdk import AlpsClient, ApiError

BASE_URL = {base_url!r}
NAME = {username!r}
PASSWORD = {password!r}


def main():
    client = AlpsClient(base_url=BASE_URL, name=NAME, password=PASSWORD, verify=False)
    try:
{body}
    finally:
        client.logout()


if __name__ == "__main__":
    main()
'''


def _py_expr(value: Any) -> str:
    """把参数值转成 Python 源码片段：Ref 转变量名，其余用 repr。"""
    if isinstance(value, Ref):
        return f"v_{value.step}_{value.field}"
    return repr(value)


def _bandwidth_for(items: Any, name: str) -> int:
    """按 type 名从需求里取带宽（Mbps），找不到返回 0。"""
    for item in items:
        if getattr(item, "type", None) == name:
            return getattr(item, "bandwidth_mbps", 0)
    return 0


def _profile_list_literal(items: List[dict]) -> str:
    """把 profile 条目列表渲染成 Python list[dict] 字面量。"""
    dicts = []
    for item in items:
        entries = []
        for key, val in item.items():
            if isinstance(val, str) and val.startswith("v_"):
                entries.append(f"{key!r}: {val}")
            else:
                entries.append(f"{key!r}: {repr(val)}")
        dicts.append("{" + ", ".join(entries) + "}")
    return "[" + ", ".join(dicts) + "]"


def _collect_profiles(
    plan: List[PlanStep], requirement: TestRequirement
) -> tuple[List[dict], List[dict]]:
    """从 plan 收集攻击与业务 profile 条目（含带宽/时长）。"""
    attacks: List[dict] = []
    businesses: List[dict] = []
    for step in plan:
        name = step.inputs.get("profile_name")
        if step.capability == "ensure_attack_profile":
            attacks.append(
                {
                    "profile_id": f"v_{step.step_id}_profile_id",
                    "profile_name": f"v_{step.step_id}_profile_name",
                    "bandwidth_mbps": _bandwidth_for(requirement.attacks, name),
                    "duration_sec": requirement.duration_sec,
                }
            )
        elif step.capability == "ensure_load_profile":
            businesses.append(
                {
                    "profile_id": f"v_{step.step_id}_profile_id",
                    "profile_name": f"v_{step.step_id}_profile_name",
                    "bandwidth_mbps": _bandwidth_for(requirement.businesses, name),
                    "duration_sec": requirement.duration_sec,
                }
            )
    return attacks, businesses


def _render_call(
    step: PlanStep, requirement: TestRequirement, attacks: List[dict], businesses: List[dict]
) -> List[str]:
    """渲染一个步骤的调用与输出提取，返回行列表（不含缩进）。"""
    cap = CAPABILITIES[step.capability]
    lines: List[str] = []

    ctx: dict[str, Any] = {"out": f"_r_{step.step_id}"}
    for name, val in step.inputs.items():
        ctx[name] = _py_expr(val)

    if step.capability == "build_testcase_info":
        lines.append(f"ATTACKS = {_profile_list_literal(attacks)}")
        lines.append(f"BUSINESSES = {_profile_list_literal(businesses)}")

    lines.append(Template(cap.template).render(**ctx))

    for field, expr in cap.output_expr.items():
        var = f"v_{step.step_id}_{field}"
        lines.append(f"{var} = {Template(expr).render(out=f'_r_{step.step_id}')}")

    return lines


def _render_body(plan: List[PlanStep], requirement: TestRequirement) -> List[str]:
    attacks, businesses = _collect_profiles(plan, requirement)
    lines: List[str] = []
    for step in plan:
        lines.extend(_render_call(step, requirement, attacks, businesses))
    return lines


def synthesize(requirement: TestRequirement, plan: List[PlanStep]) -> str:
    """把 TestPlan 渲染成完整 Python 脚本源码。"""
    body = _render_body(plan, requirement)
    indented = "\n".join("        " + line for line in body)
    return _HEADER.format(
        base_url=requirement.base_url,
        username=requirement.username,
        password=requirement.password,
        body=indented,
    )


__all__ = ["synthesize"]
