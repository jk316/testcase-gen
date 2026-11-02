"""信而泰测试代码生成系统（codegen）。

输入：测试意图（或需求文档拆分的意图）→ 结构化需求 TestRequirement
    → 测试计划 TestPlan → 可执行 Python 代码。

分层见 docs/代码生成系统设计.md。
"""
from codegen.ir import (
    AttackSpec,
    BusinessSpec,
    PlanStep,
    Ref,
    TestRequirement,
    allocate_bandwidth,
    parse_bandwidth_mbps,
    validate_plan,
)
from codegen.parser import parse_intent
from codegen.planner import plan_test
from codegen.synthesizer import synthesize

__all__ = [
    "AttackSpec",
    "BusinessSpec",
    "PlanStep",
    "Ref",
    "TestRequirement",
    "allocate_bandwidth",
    "parse_bandwidth_mbps",
    "parse_intent",
    "plan_test",
    "synthesize",
    "validate_plan",
]
