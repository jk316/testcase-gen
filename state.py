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
from utils.file_process import load_api_jsonl, load_jinja_template
from dotenv import load_dotenv

load_dotenv()

logger = get_logger("AgentState")
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

    # 当前目标 API
    target_api: str | None
    candidate_api_ids: List[str]

    # 已处理 API
    used_apis: Set[str]

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

def get_steps_node(state: AgentState) -> dict:
    """
    初始化步骤列表，读取所有 intent 并设置初始状态
    """
    steps_file = "steps.txt"
    logger.info("Reading steps from %s", steps_file)

    intent_lines = []
    if os.path.exists(steps_file):
        with open(steps_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    intent_lines.append(line)
    else:
        logger.warning("Steps file %s not found", steps_file)

    logger.info("Loaded %d steps", len(intent_lines))

    # 返回 delta，初始化步骤列表和索引
    return {
        "intent_list": intent_lines,
        "current_intent_index": 0
    }



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
        api_jsonl = load_api_jsonl("inputs/xrt_openapi.jsonl")
        apis = [ApiItem(id=api_dict["id"], title=api_dict["title"], content=api_dict["content"]) 
                for api_dict in api_jsonl]
        logger.info(f"Loaded {len(apis)} APIs")
        
        # 初始化 LLM 和 Embeddings
        llm = ChatTongyi(model="qwen-max")
        embeddings = DashScopeEmbeddings(model="text-embedding-v1")
        
        # 加载 prompt 模板
        template_str = load_jinja_template("prompts/intent.jinja")
        
        # 创建索引实例
        _api_index = ApiIntentIndexNew(
            llm=llm,
            embedding=embeddings,
            prompt_template=template_str,
            experience_data_path="outputs/experience_pool.jsonl",
            experience_label_path="outputs/experience_pool_label.jsonl",
            experience_similarity_threshold=0.9,
            experience_model_version="qwen-max-v1",
            top_k=3  # 确保返回 Top 3
        )
        
        # 加载或构建索引
        INDEX_DIR = "indexes/api_intent_faiss"
        FORCE_REBUILD = False
        
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
        api_jsonl = load_api_jsonl("inputs/xrt_openapi.jsonl")
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
        _llm = ChatTongyi(model="qwen-max")
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
        template_str = load_jinja_template("prompts/testcase.jinja")
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
    intent = state.get("intent", "")
    current_index = state.get("current_intent_index", 0)
    
    logger.info(f"[generate_testcase_node] Received candidate_api_ids: {candidate_api_ids}")
    logger.info(f"[generate_testcase_node] Received intent: {intent}")
    
    if not candidate_api_ids:
        logger.warning("No candidate API IDs, skipping testcase generation")
        return {
            "generated_testcase": None
        }
    
    # 取第一个候选 API ID（可以根据需要修改为遍历所有）
    api_id = candidate_api_ids[0]
    logger.info(f"Generating testcase for API ID: {api_id}, intent: {intent}")
    
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
        testcase_json["intent"] = intent
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


def process_intent_node(state: AgentState) -> dict:
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
        logger.warning("No more intents to process")
        return {
            "intent": ""
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
    
    if current_index < len(intent_list):
        logger.info(f"Continuing: {current_index}/{len(intent_list)} intents processed")
        return "continue"
    else:
        logger.info("All intents processed, ending")
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

builder.add_node("get_steps", get_steps_node)
builder.add_node("process_intent", process_intent_node)
builder.add_node("search_apis", search_apis_node)
builder.add_node("generate_testcase", generate_testcase_node)

builder.set_entry_point("get_steps")

# 从 get_steps 到 process_intent 的边
builder.add_edge("get_steps", "process_intent")

# 从 process_intent 到 search_apis 的边
builder.add_edge("process_intent", "search_apis")

# 从 search_apis 到 generate_testcase 的边
builder.add_edge("search_apis", "generate_testcase")

## Test用
builder.add_edge("generate_testcase", END)

# # 从 generate_testcase 使用条件边：根据是否还有更多步骤决定继续循环或结束
# builder.add_conditional_edges(
#     "generate_testcase",
#     should_continue,
#     {
#         "continue": "process_intent",  # 还有更多步骤，继续处理下一个 intent
#         "end": END  # 所有步骤处理完毕，结束
#     }
# )

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
        "target_api": None,
        "candidate_api_ids": [],
        "used_apis": set(),
        "required_input_fields": set(),
        "available_output_fields": set(),
        "api_input_fields": {},
        "api_output_fields": {},
        "missing_fields": set(),
        "step_count": 0,
        "max_steps": 100,
        "generated_testcase": None
    }
    
    logger.info("Invoking graph with initial state...")
    logger.debug("Initial state keys: %s", list(initial_state.keys()))
    
    try:
        logger.info("Starting graph execution")
        # 使用 stream 模式来追踪执行过程
        for event in graph.stream(initial_state):
            logger.info("Graph event: %s", event)
            for node_name, node_output in event.items():
                logger.info("  Node '%s' output keys: %s", node_name, list(node_output.keys()) if isinstance(node_output, dict) else type(node_output))
        
        # 获取最终状态
        result = graph.invoke(initial_state)
        logger.info("Graph execution completed successfully")
        logger.info("Final generated_testcase: %s", "Present" if result.get("generated_testcase") else "None")
        logger.debug("Final state: %s", result)
    except Exception as e:
        logger.error("Graph execution failed: %s", e, exc_info=True)