"""中间表示（IR）：结构化需求 TestRequirement 与测试计划 TestPlan。

本模块全部为确定性逻辑（无 LLM 调用），是系统可测试、可校验的地基。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class AttackSpec:
    """一种并发攻击（带宽已均分）。"""

    type: str
    bandwidth_mbps: int
    target: Dict[str, Any] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessSpec:
    """一种合法业务（背景）流量（带宽已均分）。"""

    type: str
    bandwidth_mbps: int
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TestRequirement:
    """结构化测试需求（输入模型）。"""

    name: str
    duration_sec: int
    attacks: Tuple[AttackSpec, ...] = ()
    businesses: Tuple[BusinessSpec, ...] = ()
    base_url: str = "https://10.99.80.111:7070"
    username: str = "admin"
    password: str = "admin"


@dataclass(frozen=True)
class Ref:
    """参数依赖：引用前序某步骤产出的字段。"""

    step: str
    field: str


@dataclass(frozen=True)
class PlanStep:
    """测试计划中的一步：能力 + 参数 + 产出。"""

    step_id: str
    capability: str
    inputs: Dict[str, Any] = field(default_factory=dict)  # value | Ref
    outputs: List[str] = field(default_factory=list)


def parse_bandwidth_mbps(value: str) -> int:
    """把 "1Gbps" / "500Mbps" / "1000" 等解析成 Mbps 整数。"""
    s = str(value).strip().lower().replace(" ", "")
    m = re.match(r"^(\d+(?:\.\d+)?)(gbps|g|mbps|m|kbps|k|bps|b)?$", s)
    if not m:
        raise ValueError(f"无法解析带宽: {value!r}")
    num = float(m.group(1))
    unit = m.group(2) or "mbps"
    factors = {
        "gbps": 1000,
        "g": 1000,
        "mbps": 1,
        "m": 1,
        "kbps": 1 / 1000,
        "k": 1 / 1000,
        "bps": 1 / 1_000_000,
        "b": 1 / 1_000_000,
    }
    return int(num * factors[unit])


def allocate_bandwidth(total_mbps: int, count: int) -> List[int]:
    """平均分配总带宽，余数优先分给靠前的项；返回每个的整数带宽。"""
    if count <= 0:
        return []
    base, rem = divmod(total_mbps, count)
    return [base + (1 if i < rem else 0) for i in range(count)]


def validate_plan(plan: List[PlanStep], capabilities: Dict[str, Any]) -> List[str]:
    """校验 TestPlan：能力存在 + 输入字段合法 + 参数依赖（Ref）闭环。

    Returns:
        错误信息列表；空列表表示合法。
    """
    errors: List[str] = []
    produced: Dict[str, set] = {}

    for step in plan:
        cap = capabilities.get(step.capability)
        if cap is None:
            errors.append(f"步骤 {step.step_id}: 未知能力 {step.capability}")
            continue

        # 输入字段须在能力声明的输入范围内（能力声明了非空 input_fields 才校验）
        declared = set(getattr(cap, "input_fields", ()) or ())
        if declared:
            for name in step.inputs:
                if name not in declared:
                    errors.append(
                        f"步骤 {step.step_id}: 输入 {name} 不在能力 {step.capability} 的输入字段 {sorted(declared)} 中"
                    )

        # 依赖闭环：Ref 必须指向已处理过（前序）的步骤，且字段确实被产出
        for name, val in step.inputs.items():
            if isinstance(val, Ref):
                if val.step not in produced:
                    errors.append(f"步骤 {step.step_id}.{name}: 引用了不存在的步骤 {val.step}")
                elif val.field not in produced[val.step]:
                    errors.append(
                        f"步骤 {step.step_id}.{name}: 步骤 {val.step} 未产出字段 {val.field}"
                    )

        produced[step.step_id] = set(step.outputs)

    return errors


__all__ = [
    "AttackSpec",
    "BusinessSpec",
    "TestRequirement",
    "Ref",
    "PlanStep",
    "parse_bandwidth_mbps",
    "allocate_bandwidth",
    "validate_plan",
]
