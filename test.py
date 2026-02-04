import asyncio
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="glm-4.7",
    temperature=0.7,
    openai_api_key="d8df7202bc034b24bf9680e348cddb26.g9Soe1eM99PjjQWH",
    base_url="https://open.bigmodel.cn/api/coding/paas/v4"  # 智谱 OpenAI 兼容端点
)


async def main():
    resp = await llm.ainvoke("用一句话解释什么是 OpenAI 协议")
    print(resp.content)


if __name__ == "__main__":
    asyncio.run(main())
