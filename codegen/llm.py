"""LLM 工厂与调用工具。"""
from __future__ import annotations

import json
import os
from typing import Any, Optional


def get_llm(provider: Optional[str] = None, model: Optional[str] = None) -> Any:
    """按 provider 返回 LangChain chat model，默认通义 qwen-plus。"""
    provider = (provider or os.getenv("LLM_PROVIDER", "tongyi")).lower()

    if provider == "tongyi":
        from langchain_community.chat_models.tongyi import ChatTongyi

        return ChatTongyi(model=model or os.getenv("QWEN_MODEL", "qwen-plus"))

    if provider == "glm":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model or "glm-4.7",
            base_url="https://open.bigmodel.cn/api/paas/v4/",
            openai_api_key=os.getenv("GLM_API_KEY"),
        )

    if provider == "deepseek":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model or "deepseek-chat",
            base_url="https://api.deepseek.com",
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        )

    raise ValueError(f"未知 LLM provider: {provider}")


def ask_llm(llm: Any, prompt: str) -> str:
    """调用 LLM 并返回文本内容。"""
    resp = llm.invoke(prompt)
    if hasattr(resp, "content"):
        return resp.content
    return str(resp)


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


__all__ = ["get_llm", "ask_llm", "extract_json"]
