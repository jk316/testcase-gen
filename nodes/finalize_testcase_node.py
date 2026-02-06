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


async def finalize_testcase_node(state: "AgentState") -> dict:
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
    finalized_testcases = state.get("finalized_testcases", []) # 每一步的testcase结果列表（按步骤顺序）
    current_step_index = state.get("current_step_index", 0)

    current_params_reasoning = params_reasoning[current_step_index] # 当前步骤的参数推理结果
    
    if not current_params_reasoning:
        logger.error(f"current_params_reasoning is None or empty for step {current_step_index}")
        return {
            "finalized_testcases": finalized_testcases,
        }
    
    # 3. 使用 chain 生成最终测试用例
    logger.info("Calling LLM to generate final testcase")
    
    try:
        # 获取或创建 chain
        chain = create_finalize_testcase_chain()
        
        # 调用 chain，传入原始测试用例和标准格式
        # chain 会自动将 JSON 对象转换为字符串
        finalized_testcase = await chain.ainvoke({
            "current_params_reasoning": current_params_reasoning, # 当前步骤的参数推理结果
        })
        
        if finalized_testcase is None:
            logger.error(f"Failed to parse LLM response as JSON for step {current_step_index}")
            return {
                "finalized_testcases": finalized_testcases,
            }
        
        logger.info(f"Successfully generated finalized testcase for step {current_step_index}")
        logger.debug(f"step {current_step_index} finalized testcase content: {json.dumps(finalized_testcase, ensure_ascii=False, indent=2)}")
        
        # 4. 保存最终测试用例到文件
        file_name = f"{config.files.finalized_testcases_dir}/testcase_step_{current_step_index}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        save_json_file(finalized_testcase, file_name)
        logger.info(f"Successfully saved step {current_step_index} finalized testcase to {file_name}")
        logger.debug(f"finalized_testcases length: {len(finalized_testcases)}")
        return {
            "finalized_testcases": finalized_testcases + [finalized_testcase], # 每一步的testcase结果列表（按步骤顺序）
        }
        
    except Exception as e:
        logger.error(f"Error finalizing testcase: {e}", exc_info=True)
        return {
            "finalized_testcases": finalized_testcases,
        }
