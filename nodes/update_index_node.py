"""
更新索引的 Node
处理当前 intent：从 intent_list 中取出当前索引的 intent
"""
from typing import TYPE_CHECKING
from utils.logger import get_logger

if TYPE_CHECKING:
    from state import AgentState

logger = get_logger("UpdateIndexNode")


def update_index_node(state: "AgentState") -> dict:
    """
    处理当前 intent：从 intent_list 中取出当前索引的 intent
    """
    intent_list = state.get("intent_list", [])
    current_index = state.get("current_intent_index", 0)
    
    if current_index < len(intent_list):
        current_intent = intent_list[current_index]
        logger.info(f"[update_index_node] Processing intent [{current_index + 1}/{len(intent_list)}]: {current_intent}")
        
        # 返回 delta：更新当前 intent 和索引
        return {
            "intent": current_intent,
            "current_intent_index": current_index + 1
        }
    else:
        logger.warning(f"[update_index_node] No more intents to process (current_index={current_index}, total={len(intent_list)})")
        # 即使没有更多 intent，也要更新索引，确保 should_continue 能正确判断
        return {
            "intent": "",
            "current_intent_index": current_index  # 保持当前索引，确保 >= len(intent_list)
        }
