"""
更新索引的 Node
处理当前 intent：从 intent_list 中取出当前索引的 intent
"""
from typing import TYPE_CHECKING
from utils.logger import get_logger

if TYPE_CHECKING:
    from schemas.state import AgentState

logger = get_logger(__name__)


def update_step_index_node(state: "AgentState") -> dict:
    """
    处理当前 steps_index：从 steps_list 中取出当前索引的 steps
    """
    steps_list = state.get("steps_list", [])
    current_index = state.get("current_step_index", 0)
    
    if current_index < len(steps_list):
        current_step = steps_list[current_index]
        logger.info(f"Processing step {current_index + 1} of {len(steps_list)}: {current_step}")
        
        # 返回 delta：更新当前 steps 和索引
        return {
            "current_step_index": current_index + 1
        }
    else:
        logger.warning(f"No more steps to process (current_index={current_index + 1}, total={len(steps_list)})")
        # 即使没有更多 steps，也要更新索引，确保 should_continue 能正确判断
        return {
            "current_step_index": current_index  # 保持当前索引，确保 >= len(steps_list)
        }
