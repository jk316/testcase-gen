"""
Merge Testcase Node
将每一步生成的 finalized testcase 合并成一个 steps 列表
"""
from datetime import datetime
from typing import TYPE_CHECKING

from utils.logger import get_logger
from utils.file_process import save_json_file
from config import get_config

if TYPE_CHECKING:
    from schemas.state import AgentState

logger = get_logger(__name__)
config = get_config()



async def merge_testcase_node(state: "AgentState") -> dict:
    """
    从 state 中取 finalized_testcases，按步序合并为 steps 列表

    Returns:
        更新后的 AgentState delta，包含 merged_testcase: { "name": "Simple testcase", "demand": "testcase v0.0.0", "tester": "XRT Darpeng", "steps": [...] }
    """
    logger.info("Starting merge testcase")
    finalized_testcases = state.get("finalized_testcases", [])

    if not finalized_testcases:
        logger.error("finalized_testcases is empty, skipping merge")
        return {"merged_testcase": None}

    merged = {
        "name": "Simple Testcase",
        "demand": "testcase v0.0.0",
        "tester": "XRT Darpeng",
        "steps": finalized_testcases,
    }

    # 可选：写入合并文件
    out_dir = config.files.merged_testcase_dir
    file_name = f"{out_dir}/merged_testcase_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    save_json_file(merged, file_name)
    logger.info("Merged testcase saved to %s", file_name)

    return {
        "merged_testcase": merged
    }
