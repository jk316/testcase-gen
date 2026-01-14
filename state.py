from utils.logger import get_logger
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from config import get_config
from schemas.state import AgentState
from nodes import (
    load_intent_list_node,
    generate_steps_node,
    update_index_node,
    generate_testcase_node,
    write_testcase_node,
    should_continue,
)

load_dotenv()

logger = get_logger(__name__)
config = get_config()

builder = StateGraph(AgentState)

builder.add_node("load_intent_list", load_intent_list_node)
builder.add_node("generate_steps", generate_steps_node)
# builder.add_node("get_steps", get_steps_node)
builder.add_node("generate_testcase", generate_testcase_node)
builder.add_node("write_testcase", write_testcase_node)
builder.add_node("loop_control", update_index_node)
builder.add_node("should_continue", should_continue)
builder.set_entry_point("load_intent_list")

# 从 load_intent_list 到 generate_intent 的边
builder.add_edge("load_intent_list", "generate_steps")

# 从 generate_steps 到 generate_testcase 的边
builder.add_edge("generate_steps", "generate_testcase")

# 从 generate_testcase 到 write_testcase 的边
builder.add_edge("generate_testcase", "write_testcase")

builder.add_edge("write_testcase", "loop_control")



# 从 generate_testcase 使用条件边：根据是否还有更多步骤决定继续循环或结束
builder.add_conditional_edges(
    "loop_control",
    should_continue,
    {
        "continue": "generate_testcase",  # 还有更多步骤，继续生成 testcase
        "end": END  # 所有步骤处理完毕，结束
    }
)

graph = builder.compile()

# 验证图结构
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

if __name__ == "__main__":
    print_graph_structure()
    
    # 创建初始状态
    initial_state = {
        "intent_list": None,
        "current_intent_index": 0,
        "candidate_api_ids": [],
        "generated_testcase": None
    }
    
    logger.info("Invoking graph with initial state")
    logger.debug("Initial state keys: %s", list(initial_state.keys()))
    
    try:
        logger.info("Starting graph execution")
        # 使用 stream 模式来追踪执行过程并获取最终状态
        # 增加递归限制配置
        graph_config = {"recursion_limit": config.graph.recursion_limit}
        final_state = None
        iteration_count = 0
        for event in graph.stream(initial_state, config=graph_config):
            iteration_count += 1
            logger.info(f"Graph event (iteration {iteration_count})")
            for node_name, node_output in event.items():
                logger.debug("Node '%s' output keys: %s", node_name, list(node_output.keys()) if isinstance(node_output, dict) else type(node_output))
                # 保存最后一个状态作为最终状态
                if node_output is not None:
                    final_state = node_output
        
        logger.info(f"Graph execution completed successfully after {iteration_count} iterations")
        if final_state:
            logger.info("Final generated_testcase: %s", "Present" if final_state.get("generated_testcase") else "None")
        logger.debug("Final state: %s", final_state)
    except Exception as e:
        logger.error("Graph execution failed: %s", e, exc_info=True)