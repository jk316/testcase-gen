"""
加载测试意图的 Node
从 intent.txt 文件中读取测试意图并保存到 state
"""
from typing import TYPE_CHECKING, Optional
from utils.logger import get_logger
from utils.file_process import load_text_file
from config import get_config

if TYPE_CHECKING:
    from state import AgentState

logger = get_logger("LoadTestIntentNode")
config = get_config()


def load_intent_list_node(state: "AgentState") -> dict:
    """
    从 intent.txt 文件中读取测试意图并保存到 state
    
    Args:
        state: AgentState 对象
        
    Returns:
        delta 字典，包含 test_intent 字段
    """
    logger.info("[load_intent_list_node] Starting execution")
    
    intent_list_file = config.files.intent_list_file
    intent_list = load_text_file(intent_list_file)
    
    if intent_list:
        logger.info(f"[load_intent_list_node] Loaded intent list from {intent_list_file}: {intent_list}")
        return {
            "intent_list": intent_list
        }
    else:
        logger.warning(f"[load_intent_list_node] Intent list file {intent_list_file} not found")
        return {
            "intent_list": None
        }
