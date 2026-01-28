"""
AgentState 类型定义
"""
from typing import List, Dict, Set, TypedDict, Optional, Any


class AgentState(TypedDict):
    """LangGraph 的状态类型定义"""
    
    # 循环控制
    intent_list: List[str]
    current_intent_index: int

    steps_list: List[str]
    current_step_index: int

    # 当前候选 API ID 列表
    candidate_api_ids: List[List[str]]

    # 字段信息
    required_input_fields: Set[str]
    available_output_fields: Set[str]


    all_input_fields: List[List[Dict[str, Any]]] # 输入字段列表
    all_output_fields: List[List[Dict[str, Any]]] # 输出字段列表

    # 控制信息
    missing_fields: Set[str]
    step_count: int
    max_steps: int

    # 生成的 testcase
    generated_testcases: List[Dict[str, Any]]

    # 参数推理
    params_reasoning: List[Dict[str, Any]]

    # 最终测试用例
    finalized_testcase: Optional[Dict[str, Any]]
