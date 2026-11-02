"""需求解析：把一条测试意图文本解析为结构化 TestRequirement。

带宽均分等确定性计算在此完成，不让 LLM 做算术。
"""
from __future__ import annotations

from typing import Any, Optional

from codegen.ir import (
    AttackSpec,
    BusinessSpec,
    TestRequirement,
    allocate_bandwidth,
)
from codegen.llm import TokenUsage, ask_llm, extract_json, get_llm

_INTENT_PROMPT = """你是测试需求解析器。从下面的测试意图中抽取结构化字段，只输出 JSON（不要解释）。

测试意图：
{intent}

输出 JSON，字段如下：
{{
  "name": "测试名称",
  "duration_sec": 200,
  "attack": {{
    "total_bandwidth_mbps": 1000,
    "types": ["udp_flood", "http_get_flood"],
    "targets": {{"udp_flood": {{"dest_ip": "11.0.0.1/24"}}, "http_get_flood": {{"url": "http://x/index.html"}}}}
  }},
  "business": {{
    "total_bandwidth_mbps": 2000,
    "types": ["http_browse"]
  }}
}}

规则：
- 带宽统一换算成 Mbps 整数（1Gbps=1000Mbps）。
- "攻击总带宽"对应 attack.total_bandwidth_mbps，"业务总带宽"对应 business.total_bandwidth_mbps，两者都要提取。
- 提到业务总带宽但没给具体业务类型时，business.types 填 ["business"]。
- 没提业务流量时，business.total_bandwidth_mbps 为 0、types 为空数组。
- 只输出 JSON。"""


def _build_requirement(data: dict) -> TestRequirement:
    """从 LLM 解析结果构造 TestRequirement，并确定性均分带宽。"""
    attack = data.get("attack", {})
    attack_types = [str(t) for t in attack.get("types", [])]
    attack_total = int(attack.get("total_bandwidth_mbps", 0))
    attack_per = allocate_bandwidth(attack_total, len(attack_types))
    targets = attack.get("targets", {}) or {}

    attacks = tuple(
        AttackSpec(
            type=t,
            bandwidth_mbps=b,
            target=targets.get(t, {}) if isinstance(targets, dict) else {},
        )
        for t, b in zip(attack_types, attack_per)
    )

    business = data.get("business", {})
    business_types = [str(t) for t in business.get("types", [])]
    business_total = int(business.get("total_bandwidth_mbps", 0))
    if business_total > 0 and not business_types:
        business_types = ["business_traffic"]  # 有业务带宽但没给类型时的兜底
    business_per = allocate_bandwidth(business_total, len(business_types))
    businesses = tuple(
        BusinessSpec(type=t, bandwidth_mbps=b) for t, b in zip(business_types, business_per)
    )

    return TestRequirement(
        name=data.get("name", "testcase"),
        duration_sec=int(data.get("duration_sec", 60)),
        attacks=attacks,
        businesses=businesses,
        base_url=data.get("base_url", "https://10.99.80.111:7070"),
        username=data.get("username", "admin"),
        password=data.get("password", "admin"),
    )


def parse_intent(
    intent_text: str, llm: Optional[Any] = None
) -> tuple[TestRequirement, TokenUsage]:
    """解析单条测试意图 → (TestRequirement, token 用量)。"""
    llm = llm or get_llm()
    raw, usage = ask_llm(llm, _INTENT_PROMPT.format(intent=intent_text))
    data = extract_json(raw)
    return _build_requirement(data), usage


__all__ = ["parse_intent"]
