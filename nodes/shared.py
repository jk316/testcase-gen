"""
共享工具函数
用于各个 node 之间的共享功能
"""
import json
from typing import Dict, Optional, Any, List
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.prompts import PromptTemplate
from api_intent_index_new import ApiIntentIndexNew
from schemas.dto import ApiItem
from utils.file_process import load_jsonl, load_jinja_template
from utils.logger import get_logger
from config import get_config

logger = get_logger(__name__)
config = get_config()

# 模块级别的单例实例（延迟初始化）
_api_index: Optional[ApiIntentIndexNew] = None
_api_data_cache: Optional[Dict[str, Dict[str, Any]]] = None
_llm: Optional[ChatTongyi] = None
_testcase_template: Optional[PromptTemplate] = None
_api_index_dict: Optional[Dict[str, Dict[str, Any]]] = None


def get_api_index() -> ApiIntentIndexNew:
    """
    获取或初始化 API 索引实例（单例模式）
    
    Returns:
        ApiIntentIndexNew 实例
    """
    global _api_index
    
    if _api_index is None:
        logger.info("Initializing API index...")
        
        # 加载 API 数据
        api_jsonl = load_jsonl(config.files.api_openapi_file)
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
        
        import os
        if os.path.exists(INDEX_DIR) and not FORCE_REBUILD:
            logger.info("Loading FAISS index from disk...")
            _api_index.load(INDEX_DIR)
        else:
            logger.info("Building FAISS index...")
            _api_index.build_from_apis(apis, force_rebuild=FORCE_REBUILD)
            _api_index.save(INDEX_DIR)
        
        logger.info("API index initialized successfully")
    
    return _api_index


def load_api_jsonl_index() -> Dict[str, Dict[str, Any]]:
    """
    加载 API jsonl 文件，并创建 API id 到 API 数据的映射
    """
    try:
        api_jsonl_file = config.files.api_openapi_file
        api_jsonl = load_jsonl(api_jsonl_file)
        _api_index_dict = {}
        for api_dict in api_jsonl:
            api_id = api_dict.get("id")
            if api_id:
                _api_index_dict[api_id] = api_dict
        logger.info(f"[load_api_jsonl_index] Created {len(_api_index_dict)} API index")
        return _api_index_dict
    except FileNotFoundError:
        logger.warning(f"[load_api_jsonl] API jsonl file {api_jsonl_file} not found")
        return {}

def load_api_capabilities() -> List[Dict[str, Any]]:
    """
    加载 API 能力描述
    
    Returns:
        API 能力描述列表
    """
    api_descriptions_file = config.files.api_descriptions_file
    try:
        api_capabilities = load_jsonl(api_descriptions_file)
        logger.info(f"[_load_api_capabilities] Loaded {len(api_capabilities)} API capabilities")
        return api_capabilities
    except FileNotFoundError:
        logger.warning(f"[_load_api_capabilities] API descriptions file {api_descriptions_file} not found")
        return []
    except Exception as e:
        logger.error(f"[_load_api_capabilities] Error loading API capabilities: {e}")
        return []

def get_api_data_cache() -> Dict[str, Dict[str, Any]]:
    """
    获取或初始化 API 数据缓存（按 id 索引）
    
    Returns:
        Dict[str, Dict[str, Any]]: id -> API 数据的映射
    """
    global _api_data_cache
    
    if _api_data_cache is None:
        logger.info("Loading API data cache...")
        api_jsonl = load_jsonl(config.files.api_openapi_file)
        _api_data_cache = {}
        for api_dict in api_jsonl:
            api_id = api_dict.get("id")
            if api_id:
                _api_data_cache[api_id] = api_dict
        logger.info(f"Loaded {len(_api_data_cache)} APIs into cache")
    
    return _api_data_cache


def get_llm() -> ChatTongyi:
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


def get_testcase_template() -> PromptTemplate:
    """
    获取或初始化 testcase 模板（单例模式）
    
    Returns:
        PromptTemplate 实例
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


def parse_json_from_llm_response(resp_text: str) -> Optional[Any]:
    """
    从 LLM 响应中解析 JSON
    
    处理可能被 ```json 代码块包裹的情况
    
    Args:
        resp_text: LLM 返回的文本响应
        
    Returns:
        解析后的 JSON 对象，如果解析失败则返回 None
    """
    try:
        # 尝试提取 JSON（可能被 ```json 包裹）
        if "```json" in resp_text:
            json_start = resp_text.find("```json") + 7
            json_end = resp_text.find("```", json_start)
            if json_end != -1:
                resp_text = resp_text[json_start:json_end].strip()
        elif "```" in resp_text:
            json_start = resp_text.find("```") + 3
            json_end = resp_text.find("```", json_start)
            if json_end != -1:
                resp_text = resp_text[json_start:json_end].strip()
        
        return json.loads(resp_text)
    except json.JSONDecodeError as e:
        logger.error(f"[parse_json_from_llm_response] Failed to parse JSON: {e}")
        logger.error(f"[parse_json_from_llm_response] Response text: {resp_text[:500]}...")
        return None


def create_api_title_to_id_mapping(api_capabilities: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    创建 API title 到 ID 的映射
    
    Args:
        api_capabilities: API 能力描述列表，每个元素包含 'title' 和 'id' 字段
        
    Returns:
        title -> id 的字典映射
    """
    api_title_to_id = {}
    for api_item in api_capabilities:
        title = api_item.get("title", "")
        api_id = api_item.get("id", "")
        if title and api_id:
            api_title_to_id[title] = api_id
    logger.debug(f"[create_api_title_to_id_mapping] Created mapping with {len(api_title_to_id)} entries")
    return api_title_to_id


def format_api_capabilities(api_capabilities: List[Dict[str, Any]]) -> str:
    """
    格式化 API 能力描述为字符串
    
    用于 prompt 模板中展示 API 能力列表
    
    Args:
        api_capabilities: API 能力描述列表
        
    Returns:
        格式化后的字符串，每行一个 API 能力
    """
    return "\n".join([
        f"- {item.get('title', 'N/A')}: {item.get('description', 'N/A')}"
        for item in api_capabilities
    ])
