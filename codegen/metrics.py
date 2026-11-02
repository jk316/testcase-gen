"""生成流水线的统计指标：单条意图的指标 + 批次汇总。

一条意图 → 一份 ``GenerationMetrics``；一批意图 → ``summarize`` 聚合输出。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class GenerationMetrics:
    """一条测试意图 → 代码 的生成指标。"""

    intent: str = ""
    # 耗时（毫秒）
    duration_total_ms: float = 0.0
    duration_parse_ms: float = 0.0
    duration_plan_ms: float = 0.0
    duration_synthesize_ms: float = 0.0
    # token
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # 调用与重试
    llm_calls: int = 0
    plan_retries: int = 0
    # 各阶段成败
    parse_ok: bool = False
    plan_ok: bool = False
    plan_valid_first_try: bool = False
    synthesize_ok: bool = False
    # 输入复杂度
    n_attacks: int = 0
    n_businesses: int = 0
    # 失败原因（None 表示成功）
    error: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def success(self) -> bool:
        return self.error is None


def summarize(metrics: List[GenerationMetrics]) -> str:
    """把一批意图的指标聚合成汇总文本。"""
    n = len(metrics)
    if n == 0:
        return "（无统计数据）"

    ok = [m for m in metrics if m.success]
    n_ok = len(ok)
    first_try = [m for m in ok if m.plan_valid_first_try]

    total_ms = sum(m.duration_total_ms for m in metrics)
    avg_ms = total_ms / n
    prompt = sum(m.prompt_tokens for m in metrics)
    completion = sum(m.completion_tokens for m in metrics)
    calls = sum(m.llm_calls for m in metrics)
    retries = sum(m.plan_retries for m in metrics)

    lines = [
        f"=== 统计汇总（{n} 条意图）===",
        f"成功率: {n_ok}/{n} ({n_ok / n * 100:.1f}%)",
    ]
    if n_ok:
        lines.append(
            f"计划首轮通过率: {len(first_try)}/{n_ok} ({len(first_try) / n_ok * 100:.1f}%)"
        )
    else:
        lines.append("计划首轮通过率: -")
    lines.append(f"总耗时: {total_ms / 1000:.2f}s（平均 {avg_ms / 1000:.2f}s/条）")
    lines.append(f"总 token: {prompt + completion}（prompt {prompt} / completion {completion}）")
    lines.append(f"LLM 调用: {calls} 次（编排重试 {retries} 次）")

    failures = [m for m in metrics if not m.success]
    if failures:
        lines.append("失败明细:")
        for m in failures:
            lines.append(f"  - {m.intent[:50]}... => {m.error}")
    return "\n".join(lines)


__all__ = ["GenerationMetrics", "summarize"]
