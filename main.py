import asyncio
from utils.logger import get_logger
from config import get_config
from state import graph

logger = get_logger(__name__)
config = get_config()


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
            logger.debug("Graph object exists")
    except Exception as e:
        logger.warning("Could not inspect graph structure: %s", e)
    logger.info("=" * 60)


async def run_graph():
    """异步执行图工作流"""
    # 创建初始状态
    initial_state = {
        "intent_list": None,
        "current_intent_index": 0,
        "candidate_api_ids": [],
        "generated_testcase": None
    }
    logger.info("Invoking graph with initial state")
    logger.debug("Initial state keys: %s", list(initial_state.keys()))
    graph_config = {"recursion_limit": config.graph.recursion_limit}
    final_state = None
    iteration_count = 0
    async for event in graph.astream(initial_state, config=graph_config):
        iteration_count += 1
        logger.info(f"Graph event (iteration {iteration_count})")
        for node_name, node_output in event.items():
            logger.debug("Node '%s' output keys: %s", node_name, list(node_output.keys()) if isinstance(node_output, dict) else type(node_output))
            if node_output is not None:
                final_state = node_output
    logger.info(f"Graph execution completed successfully after {iteration_count} iterations")
    if final_state:
        logger.info("Final generated_testcase: %s", "Present" if final_state.get("generated_testcase") else "None")
    logger.debug("Final state: %s", final_state)
    return final_state


def main():
    """主入口函数"""
    print_graph_structure()
    try:
        logger.info("Starting graph execution (async)")
        asyncio.run(run_graph())
    except Exception as e:
        logger.error("Graph execution failed: %s", e, exc_info=True)


if __name__ == "__main__":
    main()
