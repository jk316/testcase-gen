"""LLM 工厂与调用工具（仅 DeepSeek）。

模型名与 base_url 从环境变量（.env）加载：
- DEEPSEEK_API_KEY（必需）
- MODEL_NAME（默认 deepseek-flash）
- BASE_URL（默认 https://api.deepseek.com）
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()


def get_llm(model: Optional[str] = None) -> Any:
    """返回 DeepSeek chat model。"""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model or os.getenv("MODEL_NAME") or os.getenv("DEEPSEEK_MODEL") or "deepseek-flash",
        base_url=os.getenv("BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com",
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
    )


@dataclass
class TokenUsage:
    """一次 LLM 调用的 token 用量。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __iadd__(self, other: "TokenUsage") -> "TokenUsage":
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        return self

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def _extract_usage(resp: Any) -> TokenUsage:
    """从 LangChain 响应中提取 token 用量。

    兼容两种结构：``usage_metadata``（新版 AIMessage）与
    ``response_metadata["token_usage"]``（OpenAI 原生）。
    """
    usage = TokenUsage()
    um = getattr(resp, "usage_metadata", None)
    if um:
        usage.prompt_tokens = int(um.get("input_tokens") or um.get("prompt_tokens") or 0)
        usage.completion_tokens = int(um.get("output_tokens") or um.get("completion_tokens") or 0)
        if usage.prompt_tokens or usage.completion_tokens:
            return usage
    tu = (getattr(resp, "response_metadata", None) or {}).get("token_usage") or {}
    if tu:
        usage.prompt_tokens = int(tu.get("prompt_tokens") or tu.get("input_tokens") or 0)
        usage.completion_tokens = int(tu.get("completion_tokens") or tu.get("output_tokens") or 0)
    return usage


def ask_llm(llm: Any, prompt: str) -> tuple[str, TokenUsage]:
    """调用 LLM，返回 (文本内容, token 用量)。"""
    resp = llm.invoke(prompt)
    usage = _extract_usage(resp)
    content = resp.content if hasattr(resp, "content") else str(resp)
    return content, usage


def extract_json(text: str) -> Any:
    """从 LLM 响应中提取 JSON（容忍 ```json 代码块包裹）。"""
    s = text.strip()
    if s.startswith("```"):
        # 去掉首行 ```json 与末尾 ```
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # 退而求其次：提取第一个 [ 或 { 到最后一个 ] 或 }
        start = min((i for i in (s.find("["), s.find("{")) if i != -1), default=-1)
        if start == -1:
            raise
        end = max(s.rfind("]"), s.rfind("}"))
        return json.loads(s[start : end + 1])


__all__ = ["get_llm", "ask_llm", "extract_json", "TokenUsage"]
