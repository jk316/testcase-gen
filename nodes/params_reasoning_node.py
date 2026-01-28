from chains.params_reasoning_chain import create_params_reasoning_chain
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from schemas.state import AgentState
from utils.logger import get_logger
from config import get_config
from utils.file_process import load_file,save_json_file
from nodes.shared import get_api_data_cache

import json

logger = get_logger(__name__)
config = get_config()


def params_reasoning_node(state: "AgentState") -> dict:
    """
    分析当前步骤的参数依赖关系
    
    Args:
        state: AgentState 对象，必须包含 candidate_api_ids、steps_list、all_input_fields 和 all_output_fields 字段
        
    Returns:
        更新后的 AgentState delta，包含 params_reasoning 字段
    """
    logger.info("Starting params reasoning")
    steps_list = state.get("steps_list", [])
    candidate_api_ids = state.get("candidate_api_ids", [])
    current_step_index = state.get("current_step_index", 0)

    all_input_fields = state.get("all_input_fields", [])
    all_output_fields = state.get("all_output_fields", [])
    logger.debug(f"Received current_step_index: {current_step_index}")
    logger.info(f"Received all_input_fields length: {len(all_input_fields)}")
    logger.info(f"Received all_output_fields length: {len(all_output_fields)}")

    experience_pool = load_file(config.files.experience_pool_md_file)
    current_step = steps_list[current_step_index] # 当前步骤
    current_input_fields = all_input_fields[current_step_index]
    current_api_id = candidate_api_ids[current_step_index][0]
    api_index = get_api_data_cache()
    if current_api_id not in api_index:
        logger.error(f"API ID {current_api_id} not found in api_index")
        return {
            "params_reasoning": None,
        }
    api_data = api_index[current_api_id]
    api_title = api_data.get("title", "")
    if api_title is None:
        logger.error(f"API title not found for API ID {current_api_id}")
        return {
            "params_reasoning": None,
        }

    previous_steps_outputs_fields = all_output_fields[:current_step_index]
    current_step_output_fields = all_output_fields[current_step_index]
    logger.debug(f"Received current_step_output_fields: {current_step_output_fields}")

    try:
        params_reasoning_chain = create_params_reasoning_chain()

        params_reasoning_json = params_reasoning_chain.invoke({
            "current_step_id": current_step_index,
            "testcase": current_step,
            "input_parameters_json": current_input_fields,
            "previous_steps_outputs_json": previous_steps_outputs_fields,
            "experience_pool": experience_pool,
            "output_parameters_json": current_step_output_fields,
        })
        if params_reasoning_json is None:
            logger.error(f"Failed to generate params reasoning for step {current_step_index}")
            return {
                "params_reasoning": None,
            }
        logger.info(f"Successfully generated params reasoning for step {current_step_index}")
        save_json_file(params_reasoning_json, config.files.params_reasoning_jsonl_file, append=True)
        logger.info(f"Successfully saved params reasoning to {config.files.params_reasoning_jsonl_file}")
        logger.debug(f"Params reasoning content: {json.dumps(params_reasoning_json, ensure_ascii=False, indent=2)}")
        return {
            "params_reasoning": params_reasoning_json,
        }
    except Exception as e:
        logger.error(f"Error generating params reasoning for step {current_step_index}: {e}", exc_info=True)
        return {
            "params_reasoning": None,
        }