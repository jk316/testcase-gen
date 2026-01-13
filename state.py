from typing import List, Dict, Set, TypedDict, Optional, Any
import os
import json
from jinja2 import Template
import logging
from utils.logger import get_logger
from langgraph.graph import StateGraph, END
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.prompts import PromptTemplate
from api_intent_index_new import ApiIntentIndexNew
from schemas.dto import ApiItem
from utils.file_process import load_api_jsonl, load_jinja_template, write_testcase_jsonl
from dotenv import load_dotenv
from config import get_config

load_dotenv()

logger = get_logger("AgentState")
config = get_config()
# logger.setLevel(logging.DEBUG)


# 模块级别的索引实例（延迟初始化）
_api_index: Optional[ApiIntentIndexNew] = None

# 模块级别的 API 数据缓存（延迟初始化）
_api_data_cache: Optional[Dict[str, Dict[str, Any]]] = None

# 模块级别的 LLM 实例（延迟初始化）
_llm: Optional[ChatTongyi] = None

# 模块级别的模板实例（延迟初始化）
_testcase_template: Optional[Template] = None

class AgentState(TypedDict):
    intent: str

    # 循环控制
    intent_list: List[str]
    current_intent_index: int

    # 当前候选 API ID 列表
    candidate_api_ids: List[List[str]]

    # 字段信息
    required_input_fields: Set[str]
    available_output_fields: Set[str]

    # 中间产物
    api_input_fields: Dict[str, Set[str]]
    api_output_fields: Dict[str, Set[str]]

    # 控制信息
    missing_fields: Set[str]
    step_count: int
    max_steps: int

    # 生成的 testcase
    generated_testcase: Optional[Dict[str, Any]]

def generate_intent_node(state: AgentState) -> dict:
    """
    根据 intent.txt 中的内容，参考 gen_intent.jinja 的需求，生成测试意图
    传递给 get_steps Node，并保存在 intent.json 中
    """
    logger.info("[generate_intent_node] Starting execution")
    
    # 读取 intent.txt
    intent_file = config.files.intent_file
    test_intent = ""
    if os.path.exists(intent_file):
        with open(intent_file, "r", encoding="utf-8") as f:
            test_intent = f.read().strip()
        logger.info(f"[generate_intent_node] Loaded test intent from {intent_file}: {test_intent}")
    else:
        logger.warning(f"[generate_intent_node] Intent file {intent_file} not found")
        return {
            "intent_list": [],
            "current_intent_index": 0,
            "candidate_api_ids": []
        }
    
    # 加载 API 能力描述
    api_descriptions_file = config.files.api_descriptions_file
    api_capabilities = []
    if os.path.exists(api_descriptions_file):
        api_capabilities = load_api_jsonl(api_descriptions_file)
        logger.info(f"[generate_intent_node] Loaded {len(api_capabilities)} API capabilities")
    else:
        logger.warning(f"[generate_intent_node] API descriptions file {api_descriptions_file} not found")
        return {
            "intent_list": [],
            "current_intent_index": 0,
            "candidate_api_ids": []
        }
    
    # 格式化 API 能力描述为字符串
    api_capabilities_str = "\n".join([
        f"- {item.get('title', 'N/A')}: {item.get('description', 'N/A')}"
        for item in api_capabilities
    ])
    
    # 加载模板
    template_str = load_jinja_template(config.files.gen_intent_template)
    template = Template(template_str)
    
    # 格式化 prompt
    formatted_prompt = template.render(
        TEST_INTENT=test_intent,
        API_CAPABILITIES=api_capabilities_str
    )
    
    # 调用 LLM 生成测试步骤计划
    llm = _get_llm()
    logger.info("[generate_intent_node] Calling LLM to generate test steps plan")
    
    try:
        response = llm.invoke(formatted_prompt)
        resp_text = response.content if hasattr(response, "content") else str(response)
        logger.info(f"[generate_intent_node] LLM response received, length: {len(resp_text)}")
        
        # 尝试解析 JSON
        steps_json = None
        try:
            # 尝试提取 JSON（可能被 ```json 包裹）
            if "```json" in resp_text:
                json_start = resp_text.find("```json") + 7
                json_end = resp_text.find("```", json_start)
                resp_text = resp_text[json_start:json_end].strip()
            elif "```" in resp_text:
                json_start = resp_text.find("```") + 3
                json_end = resp_text.find("```", json_start)
                resp_text = resp_text[json_start:json_end].strip()
            
            steps_json = json.loads(resp_text)
            logger.info(f"[generate_intent_node] Successfully parsed {len(steps_json)} test steps")
        except json.JSONDecodeError as e:
            logger.error(f"[generate_intent_node] Failed to parse LLM response as JSON: {e}")
            logger.error(f"[generate_intent_node] LLM response: {resp_text[:500]}...")
            return {
                "intent_list": [],
                "current_intent_index": 0,
                "candidate_api_ids": []
            }
        
        # 保存到 intent.json
        intent_output_file = config.files.intent_json_file
        with open(intent_output_file, "w", encoding="utf-8") as f:
            json.dump(steps_json, f, ensure_ascii=False, indent=2)
        logger.info(f"[generate_intent_node] Saved test steps to {intent_output_file}")
        
        # 提取步骤描述作为 intent_list（用于后续处理）
        # 根据模板，每个步骤有 description 字段，我们可以用它作为 intent
        intent_lines = []
        candidate_api_ids_list = []  # 使用 list 保持顺序，允许重复
        
        # 创建 API title 到 id 的映射
        api_title_to_id = {}
        for api_item in api_capabilities:
            title = api_item.get("title", "")
            api_id = api_item.get("id", "")
            if title and api_id:
                api_title_to_id[title] = api_id
        
        logger.info(f"[generate_intent_node] Created API title to ID mapping with {len(api_title_to_id)} entries")
        
        for step in steps_json:
            if isinstance(step, dict):
                # 使用步骤的 name 或 description 作为 intent
                step_intent = step.get("description", step.get("name", ""))
                if step_intent:
                    intent_lines.append(step_intent)
                
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
                            logger.debug(f"[generate_intent_node] Found API ID {api_id} for capability: {title}")
                        else:
                            logger.warning(f"[generate_intent_node] API title not found in mapping: {title}")
                    candidate_api_ids_list.append(temp_api_ids)
        
        logger.info(f"[generate_intent_node] Extracted {len(intent_lines)} intents from generated steps")
        logger.info(f"[generate_intent_node] Found {len(candidate_api_ids_list)} API IDs from related_capability: {candidate_api_ids_list}")
        
        # 返回 delta，更新 intent_list 和 candidate_api_ids
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


# def get_steps_node(state: AgentState) -> dict:
#     """
#     初始化步骤列表，如果 intent_list 已存在则使用它，否则从 intent.json 或 steps.txt 读取
#     """
#     # 如果 state 中已经有 intent_list，直接使用
#     intent_list = state.get("intent_list", [])
    
#     if intent_list:
#         logger.info("[get_steps_node] Using intent_list from state, %d steps", len(intent_list))
#         return {
#             "current_intent_index": 0
#         }
    
#     # 尝试从 intent.json 读取（由 generate_intent_node 生成）
#     intent_json_file = config.files.intent_json_file
#     if os.path.exists(intent_json_file):
#         logger.info("[get_steps_node] Reading steps from %s", intent_json_file)
#         try:
#             with open(intent_json_file, "r", encoding="utf-8") as f:
#                 steps_json = json.load(f)
            
#             # 提取步骤描述作为 intent_list
#             intent_lines = []
#             for step in steps_json:
#                 if isinstance(step, dict):
#                     step_intent = step.get("description", step.get("name", ""))
#                     if step_intent:
#                         intent_lines.append(step_intent)
            
#             logger.info("[get_steps_node] Loaded %d steps from intent.json", len(intent_lines))
#             return {
#                 "intent_list": intent_lines,
#                 "current_intent_index": 0
#             }
#         except Exception as e:
#             logger.warning("[get_steps_node] Failed to read intent.json: %s", e)
    
#     # 否则从 steps.txt 读取（向后兼容）
#     steps_file = config.files.steps_file
#     logger.info("[get_steps_node] Reading steps from %s", steps_file)

#     intent_lines = []
#     if os.path.exists(steps_file):
#         with open(steps_file, "r", encoding="utf-8") as f:
#             for line in f:
#                 line = line.strip()
#                 if line:
#                     intent_lines.append(line)
#     else:
#         logger.warning("[get_steps_node] Steps file %s not found", steps_file)

#     logger.info("[get_steps_node] Loaded %d steps", len(intent_lines))

#     # 返回 delta，初始化步骤列表和索引
#     return {
#         "intent_list": intent_lines,
#         "current_intent_index": 0
#     }



def _get_api_index() -> ApiIntentIndexNew:
    """
    获取或初始化 API 索引实例（单例模式）
    
    Returns:
        ApiIntentIndexNew 实例
    """
    global _api_index
    
    if _api_index is None:
        logger.info("Initializing API index...")
        
        # 加载 API 数据
        api_jsonl = load_api_jsonl(config.files.api_openapi_file)
        apis = [ApiItem(id=api_dict["id"], title=api_dict["title"], content=api_dict["content"]) 
                for api_dict in api_jsonl]
        logger.info(f"Loaded {len(apis)} APIs")
        
        # 初始化 LLM 和 Embeddings
        llm = ChatTongyi(model=config.model.llm_model)
        embeddings = DashScopeEmbeddings(model=config.model.embedding_model)
        
        # 加载 prompt 模板
        template_str = load_jinja_template(config.files.intent_template)
        
        # 创建索引实例
        _api_index = ApiIntentIndexNew(
            llm=llm,
            embedding=embeddings,
            prompt_template=template_str,
            experience_data_path=config.files.experience_pool_file,
            experience_label_path=config.files.experience_pool_label_file,
            experience_similarity_threshold=config.index.experience_similarity_threshold,
            experience_model_version=config.model.llm_model,
            top_k=config.index.top_k
        )
        
        # 加载或构建索引
        INDEX_DIR = config.files.index_dir
        FORCE_REBUILD = config.index.force_rebuild
        
        if os.path.exists(INDEX_DIR) and not FORCE_REBUILD:
            logger.info("Loading FAISS index from disk...")
            _api_index.load(INDEX_DIR)
        else:
            logger.info("Building FAISS index...")
            _api_index.build_from_apis(apis, force_rebuild=FORCE_REBUILD)
            _api_index.save(INDEX_DIR)
        
        logger.info("API index initialized successfully")
    
    return _api_index


def _get_api_data_cache() -> Dict[str, Dict[str, Any]]:
    """
    获取或初始化 API 数据缓存（按 id 索引）
    
    Returns:
        Dict[str, Dict[str, Any]]: id -> API 数据的映射
    """
    global _api_data_cache
    
    if _api_data_cache is None:
        logger.info("Loading API data cache...")
        api_jsonl = load_api_jsonl(config.files.api_openapi_file)
        _api_data_cache = {}
        for api_dict in api_jsonl:
            api_id = api_dict.get("id")
            if api_id:
                _api_data_cache[api_id] = api_dict
        logger.info(f"Loaded {len(_api_data_cache)} APIs into cache")
    
    return _api_data_cache


def _get_llm() -> ChatTongyi:
    """
    获取或初始化 LLM 实例（单例模式）
    
    Returns:
        ChatTongyi 实例
    """
    global _llm
    
    if _llm is None:
        logger.info("Initializing LLM...")
        _llm = ChatTongyi(model=config.model.llm_model)
        logger.info("LLM initialized successfully")
    
    return _llm


def _get_testcase_template() -> PromptTemplate:
    """
    获取或初始化 testcase 模板（单例模式）
    
    Returns:
        Template 实例
    """
    global _testcase_template
    
    if _testcase_template is None:
        logger.info("Loading testcase template...")
        template_str = load_jinja_template(config.files.testcase_template)
        _testcase_template = PromptTemplate(
            input_variables=["API_JSON_HERE"],
            template=template_str,
            template_format="jinja2"
        )
        logger.info("Testcase template loaded successfully")
    
    return _testcase_template

def generate_testcase_node(state: AgentState) -> dict:
    """
    根据 candidate_api_ids 查询 API 定义，填充模板，使用 LLM 生成 testcase
    
    Args:
        state: AgentState 对象，必须包含 candidate_api_ids 和 intent 字段
        
    Returns:
        更新后的 AgentState delta，包含 generated_testcase 字段
    """
    logger.info("[generate_testcase_node] Starting execution")
    candidate_api_ids = state.get("candidate_api_ids", [])
    intent_list = state.get("intent_list", [])
    current_index = state.get("current_intent_index", 0)
    
    logger.info(f"[generate_testcase_node] Received candidate_api_ids: {candidate_api_ids}")
    logger.info(f"[generate_testcase_node] Received intent_list: {intent_list}")
    logger.info(f"[generate_testcase_node] Received current_index: {current_index}")
    if not candidate_api_ids:
        logger.warning("No candidate API IDs, skipping testcase generation")
        return {
            "generated_testcase": None
        }
    
    current_intent = intent_list[current_index]
    # 取第一个候选 API ID（可以根据需要修改为遍历所有）
    current_candidate_api_ids = candidate_api_ids[current_index]
    for api_id in current_candidate_api_ids:
        logger.info(f"Generating testcase for API ID: {api_id}, intent: {current_intent}")
    
        try:
            # 获取 API 数据缓存
            api_cache = _get_api_data_cache()
            
            # 查询对应的 API 定义
            if api_id not in api_cache:
                logger.error(f"API ID {api_id} not found in cache")
                return {
                    "generated_testcase": None
                }
            
            api_data = api_cache[api_id]
            
            # 解析 content（可能是字符串或已经是 dict）
            api_content = api_data.get("content", {})
            if isinstance(api_content, str):
                try:
                    api_content = json.loads(api_content)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse API content for ID {api_id}")
                    return {
                        "generated_testcase": None
                    }
            
            # 构建 API JSON（包含 id, title, content）
            api_json = {
                "id": api_data.get("id"),
                "title": api_data.get("title"),
                "content": api_content
            }
            
            # 将字典转换为格式化的 JSON 字符串
            API_JSON_HERE = json.dumps(api_json, ensure_ascii=False, indent=2)
            
            # 获取模板和 LLM
            prompt_template = _get_testcase_template()
            llm = _get_llm()
            
            # 格式化 prompt
            formatted_prompt = prompt_template.format(API_JSON_HERE=API_JSON_HERE)
            
            # 调用 LLM 生成 testcase
            logger.info(f"Calling LLM to generate testcase for API: {api_data.get('title', 'N/A')}")
            logger.debug(f"API_JSON_HERE length: {len(API_JSON_HERE)} chars")
            logger.debug(f"API_JSON_HERE preview: {API_JSON_HERE[:200]}...")
            
            # 检查 prompt 中是否包含 API_JSON_HERE 的内容
            if "API_JSON_HERE" in formatted_prompt or "<API_SPEC>" in formatted_prompt and API_JSON_HERE not in formatted_prompt:
                logger.error("Template variable not replaced! Prompt still contains placeholder")
                logger.error(f"Prompt preview (first 1000 chars): {formatted_prompt[:1000]}...")
            else:
                logger.debug(f"Prompt formatted successfully. Preview (first 500 chars): {formatted_prompt[:500]}...")
            
            response = llm.invoke(formatted_prompt)
            resp_text = response.content if hasattr(response, "content") else str(response)
            logger.info(f"LLM response: {resp_text}")
            
            # 尝试解析 JSON
            testcase_json = None
            try:
                # 尝试提取 JSON（可能被 ```json 包裹）
                if "```json" in resp_text:
                    json_start = resp_text.find("```json") + 7
                    json_end = resp_text.find("```", json_start)
                    resp_text = resp_text[json_start:json_end].strip()
                elif "```" in resp_text:
                    json_start = resp_text.find("```") + 3
                    json_end = resp_text.find("```", json_start)
                    resp_text = resp_text[json_start:json_end].strip()
                
                testcase_json = json.loads(resp_text)
                logger.info(f"Successfully generated testcase for API ID {api_id}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                logger.error(f"LLM response: {resp_text[:500]}...")  # 只记录前500字符
                return {
                    "generated_testcase": None
                }
            
            # 添加元数据
            testcase_json["api_id"] = api_id
            testcase_json["intent"] = current_intent
            testcase_json["step_index"] = current_index
            logger.info(f"Generated testcase for API ID {api_id}: {testcase_json}")
            return {
                "generated_testcase": testcase_json
            }
            
        except Exception as e:
            logger.error(f"Error generating testcase for API ID {api_id}: {e}", exc_info=True)
            return {
                "generated_testcase": None
            }


def write_testcase_node(state: AgentState) -> dict:
    """
    LangGraph Node: 将生成的 testcase 写入到文件
    
    Args:
        state: AgentState 对象，必须包含 generated_testcase 字段
        
    Returns:
        空的 delta（不更新状态）
    """
    logger.info("[write_testcase_node] Starting execution")
    generated_testcase = state.get("generated_testcase")
    
    if generated_testcase is None:
        logger.warning("[write_testcase_node] No testcase to write, skipping")
        return {}
    
    # 默认输出路径
    output_path = config.files.generated_testcases_file
    
    try:
        # 写入 testcase 到文件（追加模式）
        write_testcase_jsonl(generated_testcase, output_path, append=True)
        logger.info(f"[write_testcase_node] Successfully wrote testcase to {output_path}")
        logger.info(f"[write_testcase_node] Testcase: {json.dumps(generated_testcase, ensure_ascii=False)[:200]}...")
    except Exception as e:
        logger.error(f"[write_testcase_node] Error writing testcase: {e}", exc_info=True)
    
    # 返回空字典，不更新状态
    return {}


def update_index_node(state: AgentState) -> dict:
    """
    处理当前 intent：从 intent_list 中取出当前索引的 intent
    """
    intent_list = state.get("intent_list", [])
    current_index = state.get("current_intent_index", 0)
    
    if current_index < len(intent_list):
        current_intent = intent_list[current_index]
        logger.info(f"Processing intent [{current_index + 1}/{len(intent_list)}]: {current_intent}")
        
        # 返回 delta：更新当前 intent 和索引
        return {
            "intent": current_intent,
            "current_intent_index": current_index + 1
        }
    else:
        logger.warning(f"No more intents to process (current_index={current_index}, total={len(intent_list)})")
        # 即使没有更多 intent，也要更新索引，确保 should_continue 能正确判断
        return {
            "intent": "",
            "current_intent_index": current_index  # 保持当前索引，确保 >= len(intent_list)
        }


def should_continue(state: AgentState) -> str:
    """
    条件函数：判断是否还有更多 intent 需要处理
    
    Returns:
        "continue": 还有更多步骤，继续循环
        "end": 所有步骤处理完毕，结束
    """
    intent_list = state.get("intent_list", [])
    current_index = state.get("current_intent_index", 0)
    
    logger.info(f"[should_continue] Checking: current_index={current_index}, intent_list_length={len(intent_list)}")
    
    # 如果 current_index >= len(intent_list)，说明所有 intent 都已处理完
    if current_index < len(intent_list):
        logger.info(f"[should_continue] Continuing: {current_index}/{len(intent_list)} intents processed")
        return "continue"
    else:
        logger.info(f"[should_continue] All intents processed ({current_index}/{len(intent_list)}), ending")
        return "end"


def search_apis_node(state: AgentState) -> dict:
    """
    LangGraph Node: 根据 intent 搜索候选的 Top 3 API，并更新 candidate_apis
    
    Args:
        state: AgentState 对象，必须包含 intent 字段
        
    Returns:
        更新后的 AgentState delta，包含 candidate_api_ids 字段（Top 3 API ID 列表）
    """
    logger.info("[search_apis_node] Starting execution")
    intent = state.get("intent", "")
    
    if not intent:
        logger.warning("[search_apis_node] Intent is empty, skipping API search")
        return {
            "candidate_api_ids": []
        }
    
    logger.info(f"[search_apis_node] Searching APIs for intent: {intent}")
    
    try:
        # 获取索引实例
        index = _get_api_index()
        logger.info("[search_apis_node] API index retrieved, starting search...")
        
        # 搜索 Top 3 API（with_cross_encoder=False 可以加快速度，根据需要调整）
        with_cross_encoder = False
        results = index.search(
            intent=intent,
            with_cross_encoder=with_cross_encoder
        )
        logger.info(f"[search_apis_node] Search completed, got {len(results)} results")
        
        # 提取 API ID 列表（Top 3）
        candidate_api_ids = []
        for result in results[:3]:  # 确保只取前 3 个
            api_id = result.metadata.get("id")
            if api_id:
                candidate_api_ids.append(api_id)
        
        logger.info(f"[search_apis_node] Found {len(candidate_api_ids)} candidate API IDs: {candidate_api_ids}")
        logger.info("[search_apis_node] Returning result, should proceed to generate_testcase")

        return {
            "candidate_api_ids": candidate_api_ids
        }
        
    except Exception as e:
        logger.error(f"[search_apis_node] Error searching API IDs: {e}", exc_info=True)
        logger.error("[search_apis_node] Returning empty list due to error")
        return {
            "candidate_api_ids": []
        }



builder = StateGraph(AgentState)

builder.add_node("generate_intent", generate_intent_node)
# builder.add_node("get_steps", get_steps_node)
builder.add_node("update_index", update_index_node)
builder.add_node("generate_testcase", generate_testcase_node)
builder.add_node("write_testcase", write_testcase_node)

builder.set_entry_point("generate_intent")

# 从 generate_intent 到 generate_testcase 的边
builder.add_edge("generate_intent", "generate_testcase")

# 从 generate_testcase 到 write_testcase 的边
builder.add_edge("generate_testcase", "write_testcase")

builder.add_edge("write_testcase", "update_index")



# 从 generate_testcase 使用条件边：根据是否还有更多步骤决定继续循环或结束
builder.add_conditional_edges(
    "update_index",
    should_continue,
    {
        "continue": "generate_testcase",  # 还有更多步骤，继续生成 testcase
        "end": END  # 所有步骤处理完毕，结束
    }
)

graph = builder.compile()

# 验证图结构
def print_graph_structure():
    """打印图的结构信息用于调试"""
    logger.info("=" * 60)
    logger.info("Graph Structure:")
    logger.info("=" * 60)
    try:
        # 尝试获取图的内部结构
        if hasattr(graph, 'nodes'):
            logger.info("Nodes: %s", list(graph.nodes.keys()))
        if hasattr(graph, 'edges'):
            logger.info("Edges: %s", list(graph.edges))
        if hasattr(graph, '_graph'):
            logger.info("Graph object exists")
    except Exception as e:
        logger.warning("Could not inspect graph structure: %s", e)
    logger.info("=" * 60)

if __name__ == "__main__":
    print_graph_structure()
    
    # 创建初始状态
    initial_state = {
        "intent": "",
        "intent_list": [],
        "current_intent_index": 0,
        "candidate_api_ids": [],
        "current_api_ids": [],
        "used_apis": set(),
        "required_input_fields": set(),
        "available_output_fields": set(),
        "api_input_fields": {},
        "api_output_fields": {},
        "missing_fields": set(),
        "step_count": 0,
        "max_steps": config.graph.max_steps,
        "generated_testcase": None
    }
    
    logger.info("Invoking graph with initial state...")
    logger.debug("Initial state keys: %s", list(initial_state.keys()))
    
    try:
        logger.info("Starting graph execution")
        # 使用 stream 模式来追踪执行过程并获取最终状态
        # 增加递归限制配置
        graph_config = {"recursion_limit": config.graph.recursion_limit}
        final_state = None
        iteration_count = 0
        for event in graph.stream(initial_state, config=graph_config):
            iteration_count += 1
            logger.info(f"Graph event (iteration {iteration_count}): %s", event)
            for node_name, node_output in event.items():
                logger.info("  Node '%s' output keys: %s", node_name, list(node_output.keys()) if isinstance(node_output, dict) else type(node_output))
                # 保存最后一个状态作为最终状态
                if node_output is not None:
                    final_state = node_output
        
        logger.info(f"Graph execution completed successfully after {iteration_count} iterations")
        if final_state:
            logger.info("Final generated_testcase: %s", "Present" if final_state.get("generated_testcase") else "None")
        logger.debug("Final state: %s", final_state)
    except Exception as e:
        logger.error("Graph execution failed: %s", e, exc_info=True)