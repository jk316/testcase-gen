from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
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
    merge_testcase_node,
)

load_dotenv()

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
builder.add_node("merge_testcase", merge_testcase_node)
builder.set_entry_point("load_intent_list")

# 从 load_intent_list 到 generate_steps 的边
builder.add_edge("load_intent_list", "generate_steps")

# 从 generate_steps 到 generate_testcase 的边
builder.add_edge("generate_steps", "generate_testcase")

# 从 generate_testcase 到 params_reasoning 的边
builder.add_edge("generate_testcase", "params_reasoning")

# 从 params_reasoning 到 finalize_testcase 的边
builder.add_edge("params_reasoning", "finalize_testcase")

# 从 finalize_testcase 到 loop_control_step 的边
builder.add_edge("finalize_testcase", "loop_control_step")


# 从 loop_control_step 到 generate_testcase 或 merge_testcase 的边
builder.add_conditional_edges(
    "loop_control_step",
    should_continue_step,
    {
        "continue": "generate_testcase",
        "end": "merge_testcase",
    }
)
# 从 merge_testcase 到 END
builder.add_edge("merge_testcase", END)


graph = builder.compile()