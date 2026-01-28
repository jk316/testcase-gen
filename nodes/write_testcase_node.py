"""
写入测试用例的 Node
将生成的 testcase 写入到文件
"""
import json
from typing import TYPE_CHECKING
from utils.logger import get_logger
from utils.file_process import save_json_file
from config import get_config

if TYPE_CHECKING:
    from schemas.state import AgentState

logger = get_logger(__name__)
config = get_config()


def write_testcase_node(state: "AgentState") -> dict:
    """
    LangGraph Node: 将生成的 testcase 写入到文件
    
    Args:
        state: AgentState 对象，必须包含 generated_testcases 字段
        
    Returns:
        空的 delta（不更新状态）
    """
    logger.info("Starting testcase write")
    generated_testcases = state.get("generated_testcases", [])
    
    if not generated_testcases:
        logger.warning("No testcase to write, skipping")
        return {}
    
    # 默认输出路径
    output_path = config.files.generated_testcases_file
    
    try:
        # 写入 testcase 到文件（追加模式）
        save_json_file(generated_testcases, output_path, append=True)
        logger.info(f"Successfully wrote testcase to {output_path}")
        logger.debug(f"Testcase content: {json.dumps(generated_testcases, ensure_ascii=False, indent=2)}")
    except Exception as e:
        logger.error(f"Error writing testcase: {e}", exc_info=True)
    
    # 返回空字典，不更新状态
    return {}
