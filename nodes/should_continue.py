"""
条件函数：判断是否还有更多 intent 需要处理
"""
from typing import TYPE_CHECKING, Literal
from utils.logger import get_logger

if TYPE_CHECKING:
    from state import AgentState

logger = get_logger("ShouldContinue")


def should_continue(state: "AgentState") -> Literal["continue", "end"]:
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
