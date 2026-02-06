from nodes.shared import get_api_data_cache
from chains.generate_testcase_chain import create_generate_testcase_chain
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from schemas.state import AgentState
from utils.logger import get_logger
from config import get_config
import json

logger = get_logger(__name__)
config = get_config()


async def generate_testcase_node(state: "AgentState") -> dict:
    """
    根据 candidate_api_ids 查询 API 定义，填充模板，使用 LLM 生成 testcase
    
    Args:
        state: AgentState 对象，必须包含 candidate_api_ids 和 intent 字段
        
    Returns:
        更新后的 AgentState delta，包含 generated_testcase 字段
    """
    logger.info("Starting testcase generation")
    candidate_api_ids = state.get("candidate_api_ids", [])
    steps_list = state.get("steps_list", [])
    current_step_index = state.get("current_step_index", 0)
    generated_testcases = state.get("generated_testcases", [])
    logger.debug(f"Received candidate_api_ids: {candidate_api_ids}")
    logger.debug(f"Received steps_list: {steps_list}")  
    logger.debug(f"Received current_step_index: {current_step_index}")
    if not candidate_api_ids:
        logger.warning("No candidate API IDs, skipping testcase generation")
        return {
            "generated_testcases": generated_testcases
        }
    
    current_step = steps_list[current_step_index] # 当前步骤
    # 取第一个候选 API ID（可以根据需要修改为遍历所有）
    current_candidate_api_ids = candidate_api_ids[current_step_index]
    # 获取预计算的 all_input_fields 和 all_output_fields
    all_input_fields = state.get("all_input_fields", [])
    all_output_fields = state.get("all_output_fields", [])
    
    # 验证参数已预计算（fail-fast）
    if len(all_input_fields) <= current_step_index:
        error_msg = (
            f"步骤 {current_step_index} 的输入参数未预计算，"
            f"期望长度至少为 {current_step_index + 1}，实际为 {len(all_input_fields)}。"
            "请检查 generate_steps_node 是否正确执行。"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)
    if len(all_output_fields) <= current_step_index:
        error_msg = (
            f"步骤 {current_step_index} 的输出参数未预计算，"
            f"期望长度至少为 {current_step_index + 1}，实际为 {len(all_output_fields)}。"
            "请检查 generate_steps_node 是否正确执行。"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    api_index = get_api_data_cache()
    for api_id in current_candidate_api_ids:
        logger.info(f"Generating testcase for API ID: {api_id}, step: {current_step}")
    
        try:

            api_data = api_index[api_id]
            
            # 解析 content（可能是字符串或已经是 dict）
            api_content = api_data.get("content", {})
            if isinstance(api_content, str):
                try:
                    api_content = json.loads(api_content)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse API content for ID {api_id}")
                    return {
                        "generated_testcases": generated_testcases
                    }
            
            # 构建 API JSON（包含 id, title, content）
            api_json = {
                "id": api_data.get("id"),
                "title": api_data.get("title"),
                "content": api_content
            }
            
            # 将字典转换为格式化的 JSON 字符串
            api_json_here = json.dumps(api_json, ensure_ascii=False, indent=2)
            
            # 获取模板和 LLM
            generate_testcase_chain = create_generate_testcase_chain()

            testcase_json = await generate_testcase_chain.ainvoke({
                "api_json_here": api_json_here,
                "current_step_index": current_step_index,
                "current_step": current_step
            })
            if testcase_json is None:
                logger.error(f"Failed to generate testcase for API ID {api_id}")
                return {
                    "generated_testcases": generated_testcases
                }
            
            logger.info(f"Successfully generated testcase for API ID: {api_id}")
            logger.debug(f"Generated testcase content: {json.dumps(testcase_json, ensure_ascii=False, indent=2)}")
            
            return {
                "generated_testcases": generated_testcases + [testcase_json],
            }
        except Exception as e:
            logger.error(f"Error generating testcase for API ID {api_id}: {e}", exc_info=True)
            return {
                "generated_testcases": generated_testcases,
            }