"""
生成测试意图的 Node
根据 intent.txt 中的内容，参考 gen_intent.jinja 的需求，生成测试意图
"""
from typing import TYPE_CHECKING, List, Dict, Any, Tuple, Optional
from utils.logger import get_logger
from utils.file_process import load_api_jsonl, load_text_file, save_json_file
from config import get_config
from nodes.shared import (
    create_api_title_to_id_mapping,
    format_api_capabilities,
)
from chains import create_generate_intent_chain

if TYPE_CHECKING:
    from state import AgentState

logger = get_logger("GenerateIntentNode")
config = get_config()


def _load_test_intent() -> Optional[str]:
    """
    读取 intent.txt 文件
    
    Returns:
        测试意图字符串，如果文件不存在则返回 None
    """
    intent_file = config.files.intent_file
    test_intent = load_text_file(intent_file)
    if test_intent is not None:
        logger.info(f"[_load_test_intent] Loaded test intent from {intent_file}: {test_intent}")
    else:
        logger.warning(f"[_load_test_intent] Intent file {intent_file} not found")
    return test_intent


def _load_api_capabilities() -> List[Dict[str, Any]]:
    """
    加载 API 能力描述
    
    Returns:
        API 能力描述列表
    """
    api_descriptions_file = config.files.api_descriptions_file
    try:
        api_capabilities = load_api_jsonl(api_descriptions_file)
        logger.info(f"[_load_api_capabilities] Loaded {len(api_capabilities)} API capabilities")
        return api_capabilities
    except FileNotFoundError:
        logger.warning(f"[_load_api_capabilities] API descriptions file {api_descriptions_file} not found")
        return []
    except Exception as e:
        logger.error(f"[_load_api_capabilities] Error loading API capabilities: {e}")
        return []


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
                        logger.debug(f"[_extract_intent_data_from_steps] Found API ID {api_id} for capability: {title}")
                    else:
                        logger.warning(f"[_extract_intent_data_from_steps] API title not found in mapping: {title}")
                candidate_api_ids_list.append(temp_api_ids)
            else:
                # 如果没有 related_capability，添加空列表
                candidate_api_ids_list.append([])
    
    logger.info(f"[_extract_intent_data_from_steps] Extracted {len(intent_lines)} intents and {len(candidate_api_ids_list)} API ID lists")
    return intent_lines, candidate_api_ids_list


def generate_intent_node(state: "AgentState") -> dict:
    """
    根据 intent.txt 中的内容，参考 gen_intent.jinja 的需求，生成测试意图
    传递给 get_steps Node，并保存在 intent.json 中
    """
    logger.info("[generate_intent_node] Starting execution")
    
    # 1. 读取测试意图
    test_intent = _load_test_intent()
    if test_intent is None:
        return {
            "intent_list": [],
            "current_intent_index": 0,
            "candidate_api_ids": []
        }
    
    # 2. 加载 API 能力描述
    api_capabilities = _load_api_capabilities()
    if not api_capabilities:
        return {
            "intent_list": [],
            "current_intent_index": 0,
            "candidate_api_ids": []
        }
    
    # 3. 格式化 API 能力描述
    api_capabilities_str = format_api_capabilities(api_capabilities)
    
    # 4. 使用 chain 生成测试步骤计划
    logger.info("[generate_intent_node] Calling LLM to generate test steps plan")
    
    try:
        # 获取或创建 chain
        chain = create_generate_intent_chain()
        
        # 调用 chain
        steps_json = chain.invoke({
            "test_intent": test_intent,
            "api_capabilities": api_capabilities_str
        })
        
        if steps_json is None:
            logger.warning("[generate_intent_node] Failed to parse LLM response as JSON")
            return {
                "intent_list": [],
                "current_intent_index": 0,
                "candidate_api_ids": []
            }
        
        logger.info(f"[generate_intent_node] Successfully parsed {len(steps_json)} test steps")
        
        # 7. 保存到 intent.json
        intent_output_file = config.files.intent_json_file
        save_json_file(steps_json, intent_output_file)
        
        # 8. 创建 API title 到 ID 的映射
        api_title_to_id = create_api_title_to_id_mapping(api_capabilities)
        logger.info(f"[generate_intent_node] Created API title to ID mapping with {len(api_title_to_id)} entries")
        
        # 9. 提取 intent_list 和 candidate_api_ids
        intent_lines, candidate_api_ids_list = _extract_intent_data_from_steps(
            steps_json, 
            api_title_to_id
        )
        
        logger.info(f"[generate_intent_node] Extracted {len(intent_lines)} intents from generated steps")
        logger.info(f"[generate_intent_node] Found {len(candidate_api_ids_list)} API ID lists: {candidate_api_ids_list}")
        
        # 10. 返回 delta，更新 intent_list 和 candidate_api_ids
        return {
            "intent_list": intent_lines,
            "current_intent_index": 0,
            "candidate_api_ids": candidate_api_ids_list
        }
        
    except Exception as e:
        logger.error(f"[generate_intent_node] Error generating intent: {e}", exc_info=True)
        return {
            "intent_list": [],
            "current_intent_index": 0,
            "candidate_api_ids": []
        }
