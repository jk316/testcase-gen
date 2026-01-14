"""
条件函数：判断是否还有更多 intent 需要处理
"""
from typing import TYPE_CHECKING, Literal
from utils.logger import get_logger

if TYPE_CHECKING:
    from schemas.state import AgentState
else:
    # 运行时导入 AgentState 以支持 langgraph 的 get_type_hints
    from schemas.state import AgentState

logger = get_logger(__name__)


def should_continue_intent(state: "AgentState") -> Literal["continue", "end"]:
    """
    条件函数：判断是否还有更多 intent 需要处理
    
    Returns:
        "continue": 还有更多步骤，继续循环
        "end": 所有步骤处理完毕，结束
    """
    intent_list = state.get("intent_list", [])
    current_index = state.get("current_intent_index", 0)
    
    logger.debug(f"Checking continuation: current_index={current_index}, intent_list_length={len(intent_list)}")
    
    # 如果 current_index >= len(intent_list)，说明所有 intent 都已处理完
    if current_index < len(intent_list):
        logger.info(f"Continuing: {current_index}/{len(intent_list)} intents processed")
        return "continue"
    else:
        logger.info(f"All intents processed ({current_index}/{len(intent_list)}), ending")
        return "end"


def should_continue_step(state: "AgentState") -> Literal["continue", "end"]:
    """
    条件函数：判断是否还有更多 step 需要处理
    
    Returns:
        "continue": 还有更多步骤，继续循环
        "end": 所有步骤处理完毕，结束
    """
    steps_list = state.get("steps_list", [])
    current_index = state.get("current_step_index", 0)
    
    logger.debug(f"Checking continuation: current_index={current_index}, steps_list_length={len(steps_list)}")
    if current_index < len(steps_list):
        logger.info(f"Continuing: {current_index}/{len(steps_list)} steps processed")
        return "continue"
    else:
        logger.info(f"All steps processed ({current_index}/{len(steps_list)}), ending")
        return "end"