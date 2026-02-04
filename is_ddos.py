import json

from langchain_community.chat_models import ChatTongyi
from langchain.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from utils.file_process import save_as_json, read_json

load_dotenv()



def collect_contents(node, result):
    ## 收集所有需要被判断的内容
    # 如果 node 是一个列表，则对每个元素递归
    if isinstance(node, list):
        for item in node:
            collect_contents(item, result)
        return result

    # node 是 dict 的情况
    if isinstance(node, dict):
        target_titles = ["安全技术要求", "测试评价方法"]
        # 如果包含章节标题但不在目标列表中，跳过该节点
        if "章节标题" in node and node["章节标题"] not in target_titles:
            return result

        if node.get("content"):
            merged_contents = " ".join(node.get("content"))
            # print(node.get("content"))
            result.append(merged_contents)

        # 处理子节点
        for child in node.get("children", []):
            collect_contents(child, result)
    return result


def get_content():
    ## 从测试文档中获取所有的content
    data = read_json("output_json")
    contents = collect_contents(data, []) 
    save_as_json(contents, "contents.json")
    # for c in all_contents:
    #     print(c)


async def judge():
    ### 读取contents.json中的内容，然后判断是否包含已知的ddos攻击
    ## 1. 读取需要被判断的内容
    content = read_json("contents.json")

    ## 2. 读取已知的攻击类型
    with open("inputs/known_xinertel_attacks.md", "r", encoding="utf-8") as f:
        known_attacks_text = f.read()

    # 2. LangChain 模型
    # llm = ChatTongyi(model="qwen-max", temperature=0)
    llm = ChatTongyi(model="qwen-flash", temperature=0)  #问题简单,换小模型

    # 3. Prompt 模板
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "你是一个测试标准分析助手，任务是从文本中识别已知攻击类型。\n\n"
            "=== 已知攻击类型列表（仅可从中选择） ===\n"
            "{known_attacks}\n"
            "========================================\n\n"
            "【严格判断规则】\n"
            "1. 只能在给定的“已知攻击类型列表”中进行匹配。\n"
            "2. 匹配必须基于文本中出现的**具体攻击名称**，不得基于泛化概念进行推断，例如：\n"
            "   - 文本中仅出现“拒绝服务攻击”或“DoS”时，不得推断为任何具体类型（如 SYN Flood、ICMP Flood 等），必须返回 Unknown。\n"
            "   - 只有当文本中明确写出某个已知攻击类型（例如“ICMP洪水攻击”）时，才可以返回对应的攻击。\n"
            "3. 不允许返回未出现的攻击类型。\n"
            "4. 如果文本中出现多个具体攻击类型，可返回多个；否则返回 Unknown。\n\n"
            "【输出要求】只返回 JSON 格式：\n"
            "{{\n"
            "  \"attacks\": [...],\n"
            "  \"category\": ...\n"
            "}}\n"
        ),
        ("user", "{attack}")
    ])


    chain = prompt | llm

    # 4. 循环判断每条 content
    results = []
    for i, attack in enumerate(content):
        try:
            print(f"处理第 {i+1}/{len(content)} 个攻击: {attack}")
            res = await chain.ainvoke({"known_attacks": known_attacks_text, "attack": attack})

            # print(f"原始响应: {res}")
            # print(f"响应类型: {type(res)}")
            print(f"响应内容: {res.content}")
            results.append(json.loads(res.content))

        except Exception as e:
            print(f"处理失败: {e}")
            results.append({"error": str(e), "attack": attack})
    # 5. 输出到文件
    save_as_json(results, "judged_ddos_attacks.json")
    return results


def collect_unique_attacks():
    # 攻击类型去重
    results = read_json("judged_ddos_attacks.json")
    seen = set()
    unique_attacks = []
    for item in results:
        for attack in item.get("attacks", []):
            if attack not in seen and attack != "Unknown":
                seen.add(attack)
                unique_attacks.append(attack)

    save_as_json(unique_attacks, "unique_attacks.json")



if __name__ == "__main__":
    # get_content()
    # asyncio.run(judge())
    collect_unique_attacks()