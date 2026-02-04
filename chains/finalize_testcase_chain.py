"""
生成测试意图的 LangChain Chain
负责加载模板、调用 LLM 并解析 JSON 响应
"""
from typing import Dict, Any, Optional
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from nodes.shared import get_llm, parse_json_from_llm_response
from utils.file_process import load_jinja_template
from utils.logger import get_logger
from config import get_config

logger = get_logger(__name__)
config = get_config()

# 模块级别的 chain 缓存（单例模式）
_finalize_testcase_chain: Optional[Any] = None


def _parse_json_output(response: Any) -> Optional[Dict[str, Any]]:
    """
    解析 LLM 响应的 JSON 输出
    
    Args:
        response: LLM 返回的响应对象
        
    Returns:
        解析后的 JSON 对象（Dict），如果解析失败则返回 None
    """
    resp_text = response.content if hasattr(response, "content") else str(response)
    logger.debug(f"[_parse_json_output] Parsing LLM response, length: {len(resp_text)}")
    return parse_json_from_llm_response(resp_text)


def create_finalize_testcase_chain():
    """
    创建生成最终测试用例的 LangChain chain
    
    Chain 流程：
    1. 加载 Jinja2 模板并创建 PromptTemplate
    2. 调用 LLM 生成响应
    3. 解析 JSON 响应
    
    Returns:
        配置好的 LangChain chain
        - 输入：{"params_reasoning": List[Dict[str, Any]]}
        - 输出：Dict[str, Any] 或 None
    """
    global _finalize_testcase_chain
    
    if _finalize_testcase_chain is not None:
        return _finalize_testcase_chain
    
    logger.info("[finalize_testcase_chain] Creating finalize testcase chain")
    
    # 1. 加载模板
    template_str = load_jinja_template(config.files.final_testcase_template)
    
    # 2. 创建 PromptTemplate
    prompt_template = PromptTemplate(
        input_variables=["params_reasoning"],
        template=template_str,
        template_format="jinja2"
    )
    
    # 3. 获取 LLM 实例
    llm = get_llm()
    
    # 4. 创建 JSON 解析器
    json_parser = RunnableLambda(_parse_json_output)
    
    # 5. 组合 chain: prompt | llm | json_parser
    # 注意：需要将输入格式转换为 PromptTemplate 期望的格式
    def format_input(input_dict: Dict[str, str]) -> Dict[str, str]:
        """将输入格式转换为 PromptTemplate 期望的格式"""
        return {
            "params_reasoning": input_dict["params_reasoning"],
        }
    
    input_formatter = RunnableLambda(format_input)
    _finalize_testcase_chain = input_formatter | prompt_template | llm | json_parser
    
    logger.info("[finalize_testcase_chain] Chain created successfully")
    return _finalize_testcase_chain
