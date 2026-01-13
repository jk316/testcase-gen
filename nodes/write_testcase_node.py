"""
写入测试用例的 Node
将生成的 testcase 写入到文件
"""
import json
from typing import TYPE_CHECKING
from utils.logger import get_logger
from utils.file_process import write_testcase_jsonl
from config import get_config

if TYPE_CHECKING:
    from state import AgentState

logger = get_logger("WriteTestcaseNode")
config = get_config()


def write_testcase_node(state: "AgentState") -> dict:
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
