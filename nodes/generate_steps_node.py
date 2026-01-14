"""
生成测试意图的 Node
根据 intent.txt 中的内容，参考 gen_intent.jinja 的需求，生成测试意图
"""
from typing import TYPE_CHECKING, List, Dict, Any, Tuple, Optional
from utils.logger import get_logger
from utils.file_process import save_json_file
from config import get_config
from nodes.shared import (
    create_api_title_to_id_mapping,
    format_api_capabilities,
    load_api_capabilities,
)
from chains import create_generate_steps_chain

if TYPE_CHECKING:
    from schemas.state import AgentState

logger = get_logger(__name__)
config = get_config()



def _extract_intent_data_from_steps(
    steps_json: List[Dict[str, Any]], 
    api_title_to_id: Dict[str, str]
) -> Tuple[List[str], List[List[str]]]:
    """
    从步骤 JSON 中提取 intent_list 和 candidate_api_ids
    
    Args:
        steps_json: 步骤 JSON 列表
        api_title_to_id: API title 到 ID 的映射
        
    Returns:
        (intent_list, candidate_api_ids_list) 元组
    """
    intent_lines = []
    candidate_api_ids_list = []
    
    for step in steps_json:
        if isinstance(step, dict):
            # 使用步骤的 name 或 description 作为 intent
            step_intent = step.get("description", step.get("name", ""))
            if step_intent:
                intent_lines.append(step_intent)
            else:
                # 如果没有 intent，使用空字符串占位，确保长度一致
                intent_lines.append("")
            
            # 解析 related_capability 字段
            related_capability = step.get("related_capability", "")
            if related_capability:
                # related_capability 可能是单个 API title 或多个 API title（用逗号分隔）
                capability_titles = [cap.strip() for cap in related_capability.split(",")]
                temp_api_ids = []
                for title in capability_titles:
                    if title in api_title_to_id:
                        api_id = api_title_to_id[title]
                        temp_api_ids.append(api_id)
                        logger.debug(f"Found API ID {api_id} for capability: {title}")
                    else:
                        logger.warning(f"API title not found in mapping: {title}")
                candidate_api_ids_list.append(temp_api_ids)
            else:
                # 如果没有 related_capability，添加空列表
                candidate_api_ids_list.append([])
    
    logger.debug(f"Extracted {len(intent_lines)} intents and {len(candidate_api_ids_list)} API ID lists")
    return intent_lines, candidate_api_ids_list


def generate_steps_node(state: "AgentState") -> dict:
    """
    根据 state 中的 intent，参考 gen_intent.jinja 的需求，生成测试步骤
    传递给 generate_testcase_node，并保存在 steps.json 中
    """
    logger.info("Starting steps generation")
    
    # 1. 从 state 中读取测试意图
    intent_list = state.get("intent_list")
    current_intent_index = state.get("current_intent_index")
    if not intent_list or current_intent_index is None or current_intent_index >= len(intent_list):
        logger.warning("intent_list is None or empty, or current_intent_index is out of range")
        return {
            "intent_list": [],
            "current_intent_index": current_intent_index,
            "candidate_api_ids": []
        }
    current_intent = intent_list[current_intent_index]
    
    # 2. 加载 API 能力描述
    api_capabilities = load_api_capabilities()
    if not api_capabilities:
        return {
            "intent_list": [],
            "current_intent_index": 0,
            "candidate_api_ids": []
        }
    
    # 3. 格式化 API 能力描述
    api_capabilities_str = format_api_capabilities(api_capabilities)
    
    # 4. 使用 chain 生成测试步骤计划
    logger.info("Calling LLM to generate test steps plan")
    
    try:
        # 获取或创建 chain
        chain = create_generate_steps_chain()
        
        # 调用 chain
        steps_json = chain.invoke({
            "test_intent": current_intent,
            "api_capabilities": api_capabilities_str
        })
        
        if steps_json is None:
            logger.warning("Failed to parse LLM response as JSON")
            return {

            }
        
        logger.info(f"Successfully parsed {len(steps_json)} test steps")
        
        # 7. 保存到 steps.json
        steps_output_file = config.files.generated_steps_file
        save_json_file(steps_json, steps_output_file)
        
        # 8. 创建 API title 到 ID 的映射
        api_title_to_id = create_api_title_to_id_mapping(api_capabilities)
        logger.debug(f"Created API title to ID mapping with {len(api_title_to_id)} entries")
        
        # 9. 提取 intent_list 和 candidate_api_ids
        intent_lines, candidate_api_ids_list = _extract_intent_data_from_steps(
            steps_json, 
            api_title_to_id
        )
        
        logger.info(f"Extracted {len(intent_lines)} intents from generated steps")
        logger.debug(f"API ID lists: {candidate_api_ids_list}")
        
        # 10. 返回 delta，更新 intent_list 和 candidate_api_ids
        return {
            "intent_list": intent_lines,
            "candidate_api_ids": candidate_api_ids_list
        }
        
    except Exception as e:
        logger.error(f"Error generating intent: {e}", exc_info=True)
        return {
            "intent_list": [],
            "current_intent_index": 0,
            "candidate_api_ids": []
        }
