"""
生成测试意图的 Node
根据 intent.txt 中的内容，参考 gen_intent.jinja 的需求，生成测试意图
"""
from typing import TYPE_CHECKING, List, Dict, Any, Tuple
from utils.logger import get_logger
from utils.file_process import save_json_file
from config import get_config
from nodes.shared import (
    create_api_title_to_id_mapping,
    format_api_capabilities,
    load_api_capabilities,
    get_api_data_cache,
)
from chains import create_generate_steps_chain
from tools.redis_api_params_tool import query_api_params_from_redis
import json

if TYPE_CHECKING:
    from schemas.state import AgentState

logger = get_logger(__name__)
config = get_config()



def _extract_steps_data_from_json(
    steps_json: List[Dict[str, Any]], 
    api_title_to_id: Dict[str, str]
) -> Tuple[List[str], List[List[str]]]:
    """
    从步骤 JSON 中提取 steps_list 和 candidate_api_ids
    
    Args:
        steps_json: 步骤 JSON 列表
        api_title_to_id: API title 到 ID 的映射
        
    Returns:
        (steps_list, candidate_api_ids_list) 元组
    """
    steps_list = []
    candidate_api_ids_list = []
    
    for step in steps_json:
        if isinstance(step, dict):
            # 使用步骤的 name 或 description 作为 intent
            step_intent = step.get("description", step.get("name", ""))
            if step_intent:
                steps_list.append(step_intent)
            else:
                # 如果没有 intent，使用空字符串占位，确保长度一致
                steps_list.append("")
            
            # 解析 related_capability 字段
            related_capability = step.get("related_capability", "")
            if related_capability:
                # related_capability 可能是单个 API title 或多个 API title（用逗号分隔）
                capability_titles = [cap.strip() for cap in related_capability.split(",")]
                temp_api_ids = []
                for title in capability_titles:
                    logger.debug(f"Checking capability: {title}")
                    matched_id = None
                    for known_title, api_id in api_title_to_id.items():
                        if known_title in title:  # 或者 title in known_title
                            matched_id = api_id
                            break

                    if matched_id:
                        temp_api_ids.append(matched_id)
                        logger.debug(f"Found API ID {matched_id} for capability: {title}")
                    else:
                        logger.error(f"API title not found in mapping: {title}")
                        temp_api_ids.append(None)
                candidate_api_ids_list.append(temp_api_ids)
            else:
                # 如果没有 related_capability，添加空列表
                candidate_api_ids_list.append([])
    
    logger.debug(f"Extracted {len(steps_list)} steps and {len(candidate_api_ids_list)} API ID lists")
    return steps_list, candidate_api_ids_list


async def _precompute_api_params(
    candidate_api_ids_list: List[List[str]]
) -> Tuple[List[List[Dict[str, Any]]], List[List[Dict[str, Any]]]]:
    """
    提前计算所有步骤的 API 参数（从 Redis 查询）
    
    Args:
        candidate_api_ids_list: 每个步骤的候选 API ID 列表
        
    Returns:
        (all_input_fields, all_output_fields) 元组
        每个字段是一个列表，索引对应步骤索引
    """
    all_input_fields = []
    all_output_fields = []
    api_index = get_api_data_cache()
    
    for step_index, api_ids in enumerate(candidate_api_ids_list):
        # 为每个步骤的第一个 API ID 查询参数（当前逻辑只处理第一个）
        if not api_ids:
            logger.warning(f"步骤 {step_index} 没有候选 API ID，使用空参数列表")
            all_input_fields.append([])
            all_output_fields.append([])
            continue
        
        # 取第一个 API ID
        api_id = api_ids[0]
        
        if api_id not in api_index:
            logger.error(f"步骤 {step_index} 的 API ID {api_id} 不在缓存中，使用空参数列表")
            all_input_fields.append([])
            all_output_fields.append([])
            continue
        
        api_data = api_index[api_id]
        
        # 解析 content（可能是字符串或已经是 dict）
        api_content = api_data.get("content", {})
        if isinstance(api_content, str):
            try:
                api_content = json.loads(api_content)
            except json.JSONDecodeError:
                logger.error(f"步骤 {step_index} 的 API ID {api_id} 的 content 解析失败，使用空参数列表")
                all_input_fields.append([])
                all_output_fields.append([])
                continue
        
        # 从 API 数据中提取 HTTP 方法和 URL 路径
        api_title = api_data.get("title", "")
        if api_title.startswith("paths."):
            url_path = api_title.replace("paths.", "")
        else:
            url_path = api_title
        
        # 确保 URL 路径以 / 开头
        if not url_path.startswith("/"):
            url_path = "/" + url_path
        
        # 从 content 中提取 HTTP 方法
        http_method = "POST"  # 默认值
        for method in ["get", "post", "put", "delete", "patch"]:
            if method in api_content:
                http_method = method.upper()
                break
        
        # 从 Redis 查询 API 参数
        logger.info(f"步骤 {step_index}: 查询 Redis API 参数: {http_method} {url_path}")
        try:
            params_result = query_api_params_from_redis(http_method, url_path)
            input_params = params_result.get("input_params", [])
            output_params = params_result.get("output_params", [])
            
            logger.info(
                f"步骤 {step_index}: 从 Redis 获取到 {len(input_params)} 个输入参数, "
                f"{len(output_params)} 个输出参数"
            )
        except Exception as e:
            logger.error(f"步骤 {step_index}: 从 Redis 查询 API 参数失败: {e}", exc_info=True)
            input_params = []
            output_params = []
        
        all_input_fields.append(input_params)
        all_output_fields.append(output_params)
    
    logger.info(f"已为 {len(all_input_fields)} 个步骤预计算参数")
    return all_input_fields, all_output_fields


async def generate_steps_node(state: "AgentState") -> dict:
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
            "steps_list": [],
            "candidate_api_ids": []
        }
    current_intent = intent_list[current_intent_index]
    
    # 2. 加载 API 能力描述
    api_capabilities = load_api_capabilities()
    if not api_capabilities:
        return {
            "steps_list": [],
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
        steps_json = await chain.ainvoke({
            "test_intent": current_intent,
            "api_capabilities": api_capabilities_str
        })
        
        if steps_json is None:
            logger.warning("Failed to parse LLM response as JSON")
            return {
                "steps_list": [],
                "candidate_api_ids": []
            }
        
        logger.info(f"Successfully parsed {len(steps_json)} test steps")
        
        # 7. 保存到 steps.json
        steps_output_file = config.files.generated_steps_file
        save_json_file(steps_json, steps_output_file)
        
        # 8. 创建 API title 到 ID 的映射
        api_title_to_id = create_api_title_to_id_mapping(api_capabilities)
        logger.debug(f"Created API title to ID mapping with {len(api_title_to_id)} entries")
        
        # 9. 提取 steps_list 和 candidate_api_ids
        steps_list, candidate_api_ids_list = _extract_steps_data_from_json(
            steps_json, 
            api_title_to_id
        )
        
        logger.info(f"Extracted {len(steps_list)} steps from generated steps")
        logger.debug(f"API ID lists: {candidate_api_ids_list}")
        
        # 10. 提前计算所有步骤的 API 参数
        logger.info("Precomputing API parameters for all steps")
        all_input_fields, all_output_fields = await _precompute_api_params(candidate_api_ids_list)
        
        # 11. 返回 delta，更新 steps_list、candidate_api_ids 和预计算的参数
        return {
            "steps_list": steps_list,
            "candidate_api_ids": candidate_api_ids_list,
            "all_input_fields": all_input_fields,
            "all_output_fields": all_output_fields
        }
        
    except Exception as e:
        logger.error(f"Error generating steps: {e}", exc_info=True)
        return {
            "steps_list": [],
            "candidate_api_ids": []
        }
