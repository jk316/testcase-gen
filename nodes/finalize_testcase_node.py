"""
最终化测试用例的 Node
根据生成的测试用例和标准格式，生成最终格式化的测试用例
"""
from datetime import datetime
from typing import TYPE_CHECKING
import json
from utils.logger import get_logger
from utils.file_process import save_json_file
from config import get_config
from chains.finalize_testcase_chain import create_finalize_testcase_chain

if TYPE_CHECKING:   
    from schemas.state import AgentState

logger = get_logger(__name__)
config = get_config()


def finalize_testcase_node(state: "AgentState") -> dict:
    """
    根据 state 中的 params_reasoning，参考 final_testcase.jinja 的需求，生成最终测试用例
    
    Args:
        state: AgentState 对象，必须包含 params_reasoning 字段
        
    Returns:
        更新后的 AgentState delta，包含 finalized_testcase 字段
    """
    logger.info("Starting testcase finalization")
    
    # 1. 从 state 中读取参数
    params_reasoning = state.get("params_reasoning", []) # 参数推理结果列表
    if not params_reasoning:
        logger.warning("params_reasoning is None or empty")
        return {
            "finalized_testcase": None,
        }
    
    # 2. 加载标准格式文件
    try:
        with open(config.files.standard_format_file, "r", encoding="utf-8") as f:
            standard_format = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load standard format file: {e}", exc_info=True)
        return {
            "finalized_testcase": None,
        }
    
    if not standard_format:
        logger.warning("standard_format is None or empty")
        return {
            "finalized_testcase": None,
        }

    
    # 3. 使用 chain 生成最终测试用例
    logger.info("Calling LLM to generate final testcase")
    
    try:
        # 获取或创建 chain
        chain = create_finalize_testcase_chain()
        
        # 调用 chain，传入原始测试用例和标准格式
        # chain 会自动将 JSON 对象转换为字符串
        finalized_testcase = chain.invoke({
            "params_reasoning": params_reasoning, # 参数推理结果列表
            "standard_format": standard_format, # 标准格式
        })
        
        if finalized_testcase is None:
            logger.warning("Failed to parse LLM response as JSON")
            return {
                "finalized_testcase": None,
            }
        
        logger.info("Successfully generated finalized testcase")
        logger.debug(f"Finalized testcase content: {json.dumps(finalized_testcase, ensure_ascii=False, indent=2)}")
        
        # 4. 保存最终测试用例到文件
        file_name = f"{config.files.finalized_testcases_dir}/testcase_finalized_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        save_json_file(finalized_testcase, file_name)
        logger.info(f"Successfully saved finalized testcase to {file_name}")
        
        return {
            "finalized_testcase": finalized_testcase,
        }
        
    except Exception as e:
        logger.error(f"Error finalizing testcase: {e}", exc_info=True)
        return {
            "finalized_testcase": None,
        }
