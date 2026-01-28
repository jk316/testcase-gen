from utils.logger import get_logger
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from config import get_config
from schemas.state import AgentState
from nodes import (
    load_intent_list_node,
    generate_steps_node,
    update_intent_index_node,
    update_step_index_node,
    generate_testcase_node,
    should_continue_intent,
    should_continue_step,
    params_reasoning_node,
    finalize_testcase_node,
)

load_dotenv()

logger = get_logger(__name__)
config = get_config()

builder = StateGraph(AgentState)

builder.add_node("load_intent_list", load_intent_list_node)
builder.add_node("generate_steps", generate_steps_node)
# builder.add_node("get_steps", get_steps_node)
builder.add_node("generate_testcase", generate_testcase_node)
builder.add_node("loop_control_intent", update_intent_index_node)
builder.add_node("loop_control_step", update_step_index_node)
builder.add_node("should_continue_intent", should_continue_intent)
builder.add_node("should_continue_step", should_continue_step)
builder.add_node("params_reasoning", params_reasoning_node)
builder.add_node("finalize_testcase", finalize_testcase_node)
builder.set_entry_point("load_intent_list")

# 从 load_intent_list 到 generate_steps 的边
builder.add_edge("load_intent_list", "generate_steps")

# 从 generate_steps 到 generate_testcase 的边
builder.add_edge("generate_steps", "generate_testcase")

# 从 generate_testcase 到 params_reasoning 的边
builder.add_edge("generate_testcase", "params_reasoning")

# 从 params_reasoning 到 loop_control_step 的边
builder.add_edge("params_reasoning", "loop_control_step")

# 从 loop_control_step 到 finalize_testcase 的边
builder.add_conditional_edges(
    "loop_control_step",
    should_continue_step,
    {
        "continue": "generate_testcase",
        "end": "finalize_testcase",
        # "end": END,
    }
)

# 从 finalize_testcase 到 END 的边
builder.add_edge("finalize_testcase", END)


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