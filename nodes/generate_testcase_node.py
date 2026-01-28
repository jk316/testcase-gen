from nodes.shared import get_api_data_cache
from chains.generate_testcase_chain import create_generate_testcase_chain
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from schemas.state import AgentState
from utils.logger import get_logger
from config import get_config
from tools.redis_api_params_tool import query_api_params_from_redis
import json

logger = get_logger(__name__)
config = get_config()


def generate_testcase_node(state: "AgentState") -> dict:
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
    api_index = get_api_data_cache()
    for api_id in current_candidate_api_ids:
        logger.info(f"Generating testcase for API ID: {api_id}, step: {current_step}")
    
        try:
            # 获取当前的 all_input_fields 和 all_output_fields（在循环开始前初始化）
            all_input_fields = state.get("all_input_fields", [])
            all_output_fields = state.get("all_output_fields", [])
            
            # 确保列表长度足够
            while len(all_input_fields) <= current_step_index:
                all_input_fields.append([])
            while len(all_output_fields) <= current_step_index:
                all_output_fields.append([])
            
            # 获取 API 数据缓存
            if api_id not in api_index:
                logger.error(f"API ID {api_id} not found in api_index")
                return {
                    "generated_testcases": generated_testcases,
                    "all_input_fields": all_input_fields,
                    "all_output_fields": all_output_fields,
                }
            api_data = api_index[api_id]
            
            # 解析 content（可能是字符串或已经是 dict）
            api_content = api_data.get("content", {})
            if isinstance(api_content, str):
                try:
                    api_content = json.loads(api_content)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse API content for ID {api_id}")
                    return {
                        "generated_testcases": generated_testcases,
                        "all_input_fields": all_input_fields,
                        "all_output_fields": all_output_fields,
                    }
            
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
            logger.info(f"查询 Redis API 参数: {http_method} {url_path}")
            try:
                params_result = query_api_params_from_redis(http_method, url_path)
                input_params = params_result.get("input_params", [])
                output_params = params_result.get("output_params", [])
                
                logger.info(
                    f"从 Redis 获取到 {len(input_params)} 个输入参数, "
                    f"{len(output_params)} 个输出参数"
                )
            except Exception as e:
                logger.error(f"从 Redis 查询 API 参数失败: {e}", exc_info=True)
                input_params = []
                output_params = []
            
            # 设置当前步骤的参数
            all_input_fields[current_step_index] = input_params
            all_output_fields[current_step_index] = output_params
            
            logger.info(
                f"已设置步骤 {current_step_index} 的参数: "
                f"输入参数 {len(input_params)} 个, 输出参数 {len(output_params)} 个"
            )
            
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

            testcase_json = generate_testcase_chain.invoke({
                "api_json_here": api_json_here,
                "current_step_index": current_step_index,
                "current_step": current_step
            })
            if testcase_json is None:
                logger.error(f"Failed to generate testcase for API ID {api_id}")
                return {
                    "generated_testcases": generated_testcases,
                    "all_input_fields": all_input_fields,
                    "all_output_fields": all_output_fields,
                }
            
            logger.info(f"Successfully generated testcase for API ID: {api_id}")
            logger.debug(f"Generated testcase content: {json.dumps(testcase_json, ensure_ascii=False, indent=2)}")
            
            return {
                "generated_testcases": generated_testcases + [testcase_json],
                "all_input_fields": all_input_fields,
                "all_output_fields": all_output_fields,
            }
        except Exception as e:
            logger.error(f"Error generating testcase for API ID {api_id}: {e}", exc_info=True)
            # 确保在错误情况下也返回状态
            all_input_fields = state.get("all_input_fields", [])
            all_output_fields = state.get("all_output_fields", [])
            # 确保列表长度足够
            while len(all_input_fields) <= current_step_index:
                all_input_fields.append([])
            while len(all_output_fields) <= current_step_index:
                all_output_fields.append([])
            return {
                "generated_testcases": generated_testcases,
                "all_input_fields": all_input_fields,
                "all_output_fields": all_output_fields,
            }